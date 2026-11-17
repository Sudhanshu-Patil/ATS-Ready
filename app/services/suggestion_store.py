"""Suggestions that stay put across resume versions.

One ResumeSuggestion row per (user, job description). The list is built the first time and never recomputed.
Each time the user regenerates and ticks some suggestions, those become "applied" (and stay applied in every
later version); the rest stay "open" and are the only ones shown next time. Nothing new is ever added by a
regeneration, except a term the user typed in themselves.
"""
import hashlib
import re
from typing import Any, Dict, Iterable, List, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResumeSuggestion
from app.services.ats_score import Term, _norm, build_suggestions


def jd_hash(jd_text: str) -> str:
    """Same job description (ignoring case and whitespace) -> same hash."""
    return hashlib.sha256(re.sub(r"\s+", " ", (jd_text or "").strip().lower())[:12000].encode()).hexdigest()


def _key(term: str) -> str:
    return _norm(term).strip()


async def load(db: AsyncSession, user_id: UUID, jd_text: str) -> ResumeSuggestion | None:
    return (await db.execute(select(ResumeSuggestion).where(
        ResumeSuggestion.user_id == user_id, ResumeSuggestion.jd_hash == jd_hash(jd_text)))).scalar_one_or_none()


async def get_or_create(db: AsyncSession, user_id: UUID, jd_text: str, job_title: str | None,
                        terms: List[Term], owned_text: str) -> ResumeSuggestion:
    row = await load(db, user_id, jd_text)
    if row is None:
        row = ResumeSuggestion(user_id=user_id, jd_hash=jd_hash(jd_text), job_title=(job_title or "")[:300],
                               items=build_suggestions(terms, owned_text))
        db.add(row)
        await db.flush()
    return row


def apply_selected(row: ResumeSuggestion, selected: Iterable[str]) -> List[str]:
    """Mark the ticked terms applied. A term not on the list (typed by the user) is added as applied.
    Returns the terms newly applied this time."""
    items: List[Dict[str, Any]] = [dict(i) for i in row.items or []]
    by_key = {_key(i["term"]): i for i in items}
    newly: List[str] = []
    for term in selected:
        term = (term or "").strip()
        if not term:
            continue
        item = by_key.get(_key(term))
        if item is None:
            item = {"term": term, "kind": "user", "why": "Added by you", "importance": 0, "status": "applied"}
            items.append(item)
            by_key[_key(term)] = item
            newly.append(term)
        elif item.get("status") != "applied":
            item["status"] = "applied"
            newly.append(item["term"])
    row.items = items                      # reassign so SQLAlchemy sees the change
    return newly


def open_items(row: ResumeSuggestion) -> List[Dict[str, Any]]:
    return [i for i in row.items or [] if i.get("status") == "open"]


def applied_terms(row: ResumeSuggestion) -> List[str]:
    return [i["term"] for i in row.items or [] if i.get("status") == "applied"]


def summary(row: ResumeSuggestion) -> Tuple[List[Dict[str, Any]], List[str]]:
    return open_items(row), applied_terms(row)
