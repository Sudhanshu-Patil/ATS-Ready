"""Answers to job-application questions, written as the candidate.

Works with or without a job description. With one, answers are tailored to the role; without, they are written from
the candidate's persona alone. Either way:

  * facts the profile cannot hold (notice period, salary, work authorisation...) are NEVER guessed: the question is
    returned as needs_input, the user fills it in once, and it is remembered;
  * voluntary demographic questions are never answered for the user;
  * nothing is invented: every answer passes the same grounding checker as resumes and cover letters, against the
    profile plus what the user themselves told us (facts) and approved earlier (stories);
  * limits written in the question ("max 500 characters") or set by the user are enforced.
"""
import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ai_agent import ai_agent
from app.config import settings
from app.db.models import AssistantRequest
from app.models.schemas import ParsedJD
from app.services import applications, letter_limit, persona
from app.services.ats_score import jd_terms
from app.services.cache_service import cache_service
from app.services.compaction import compact_profile, head_tail
from app.services.grounding import enforce_letter
from app.services.metabase_service import metabase_service

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 20
SYSTEM_ASSISTANT = """You answer job-application form questions AS the candidate, in the first person.
Use ONLY the candidate material you are given. Tailor to the job when a job description is provided; otherwise write
from the candidate's background alone. Be specific, natural and concise, and match the style of the candidate's own
earlier answers when shown. NEVER invent facts, numbers, results, employers, tools, dates or years of experience; make
real experience impactful through wording only. If the material does not cover what a question needs, answer with
what is true and general, never a made-up specific. Respect each answer's length limit.
Respond with JSON only: {"answers": [{"id": <number>, "answer": "<text>"}]}"""


def prepare_questions(raw: List[str], default_limit: Optional[int] = None,
                      default_unit: str = "words") -> List[Dict[str, Any]]:
    """Clean, de-duplicate and classify the user's questions. A limit stated in the question wins."""
    out, seen = [], set()
    for text in raw:
        q = re.sub(r"\s+", " ", (text or "").strip())[:1200]
        if len(q) < 4 or q.lower() in seen:
            continue
        seen.add(q.lower())
        topic, field, sensitive = persona.classify(q)
        limit, unit = persona.detect_limit(q)
        if limit is None and default_limit:
            limit, unit = default_limit, default_unit
        out.append({"id": len(out) + 1, "question": q, "answer": "", "status": "pending", "topic": topic,
                    "field": field, "sensitive": sensitive, "limit": limit, "limit_unit": unit if limit else None,
                    "needs": None, "approved": False, "warnings": []})
        if len(out) >= MAX_QUESTIONS:
            break
    return out


def _build_prompt(profile: Dict[str, Any], jd: Optional[ParsedJD], jd_text: str, items: List[Dict[str, Any]],
                  facts: Dict[str, str], stories: Dict[int, List[Dict[str, Any]]], style: Dict[str, Any],
                  targets: List[str]) -> str:
    keywords = jd_terms(jd) if jd else []
    compact = compact_profile(profile, [t.term for t in keywords] + [w for it in items for w in it["question"].split()[:6]],
                              3200)
    parts = ["=== CANDIDATE (use only this) ===", json.dumps(compact, default=str, separators=(",", ":"))]
    if facts:
        parts += ["=== FACTS THE CANDIDATE GAVE ===", *[f"{persona.FACT_FIELDS[k]['label']}: {v}" for k, v in facts.items()
                                                       if k in persona.FACT_FIELDS]]
    if targets:
        parts.append("Roles the candidate keeps applying for: " + ", ".join(targets))
    if style.get("avg_words"):
        parts.append(f"The candidate's own answers average about {int(style['avg_words'])} words.")
    if jd:
        parts += ["=== JOB ===", f"Title: {jd.job_title}  Company: {jd.company or 'unknown'}",
                  "Key requirements: " + ", ".join(t.term for t in keywords[:10]), head_tail(jd_text, 1800)]
    elif jd_text.strip():
        parts += ["=== JOB DESCRIPTION ===", head_tail(jd_text, 1800)]
    else:
        parts.append("=== JOB === No job description was provided: answer from the candidate's background in general terms.")
    parts.append("=== QUESTIONS ===")
    for it in items:
        lim = f" (limit: {it['limit']} {'words' if it['limit_unit'] == 'words' else 'characters'})" if it["limit"] else ""
        parts.append(f"{it['id']}. {it['question']}{lim}")
        for ex in stories.get(it["id"], [])[:2]:
            parts.append(f"   Example of how the candidate answered a similar question: \"{ex['answer'][:400]}\"")
    return "\n".join(parts)


def _call_llm(prompt: str, items: List[Dict[str, Any]]) -> Dict[int, str]:
    if settings.LLM_FAKE:
        return {it["id"]: f"Fake answer to: {it['question'][:80]}" for it in items}
    response = ai_agent._call(SYSTEM_ASSISTANT, prompt, max_tokens=min(4000, 450 * len(items) + 400))
    try:
        data = json.loads(response.strip())
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", response, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    return {int(a["id"]): str(a.get("answer") or "") for a in data.get("answers", []) if str(a.get("id", "")).isdigit()}


async def _profile(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    cached = await cache_service.get_profile(str(user_id))
    if cached:
        return cached
    profile = await metabase_service.get_full_profile_async(db, user_id)
    await cache_service.set_profile(str(user_id), profile)
    return profile


async def process_request(db: AsyncSession, req: AssistantRequest, only: Optional[List[int]] = None) -> None:
    """Fill in the answers of one request (worker body). `only` re-runs just those question ids (after the user
    supplied a missing fact)."""
    user_id = req.user_id
    profile = await _profile(db, user_id)
    fact_map = await persona.facts(db, user_id)
    jd_text = (req.jd_text or "").strip()

    jd: Optional[ParsedJD] = None
    if len(jd_text) >= 100:
        cached = await cache_service.get_parsed_jd(jd_text)
        jd = ParsedJD(**cached) if cached else await asyncio.to_thread(ai_agent.parse_jd, jd_text)
        if not cached:
            await cache_service.set_parsed_jd(jd_text, jd.model_dump())
        req.job_title = req.job_title or jd.job_title
        req.company = req.company or (jd.company if not applications.is_unclear_company(jd.company) else None)
        app = await db.get(applications.Application, req.application_id) if req.application_id else None
        if app is not None:                                   # fill gaps from the posting, never overwrite
            await applications.update_application(
                db, app, company=app.company if not applications.is_unclear_company(app.company) else (req.company or ""),
                role=app.role or jd.job_title or "")
        await persona.record_target(db, user_id, jd.job_title, [t.term for t in jd_terms(jd)[:5]])
    jd_names = [t.term for t in jd_terms(jd)] if jd else []

    items = [dict(q) for q in req.questions]
    todo: List[Dict[str, Any]] = []
    for it in items:
        if only is not None and it["id"] not in only:
            continue
        if it["status"] in ("done", "skipped") and only is None:
            continue
        topic, field, sensitive = persona.classify(it["question"])
        it["topic"], it["field"], it["sensitive"], it["needs"] = topic, field, sensitive, None
        if sensitive:
            it.update(status="skipped", answer="",
                      note="This is a voluntary demographic question. Answer it yourself: we never answer it for you.")
        elif field and field not in fact_map:
            spec = persona.FACT_FIELDS[field]
            it.update(status="needs_input", answer="",
                      needs={"field": field, "label": spec["label"], "hint": spec["hint"]})
        elif field:                                            # a fact the user already gave: use their words
            it.update(status="done", answer=fact_map[field])
        else:
            todo.append(it)

    if todo:
        stories = {it["id"]: await persona.retrieve(db, user_id, it["topic"], jd_names) for it in todo}
        prompt = _build_prompt(profile, jd, jd_text, todo, fact_map, stories, await persona.style(db, user_id),
                               await persona.targets(db, user_id))
        try:
            answers = await asyncio.to_thread(_call_llm, prompt, todo)
        except Exception as exc:
            logger.error("Assistant answers failed for %s: %s", req.id, exc, exc_info=True)
            for it in todo:
                it.update(status="failed", answer="")
            req.questions = items
            raise
        grounding_profile = {**profile, **await persona.corpus_extras(db, user_id)}
        for it in todo:
            text = (answers.get(it["id"]) or "").strip()
            cleaned, fixes = enforce_letter(text, grounding_profile, jd_text, jd_names)
            warnings = []
            if fixes:
                warnings.append("A sentence with a figure or claim not in your profile was removed.")
            if len(cleaned.strip()) < 15 <= len(text.strip()):   # everything removed: keep the draft but flag it
                cleaned, warnings = text, ["Check this answer: it contains details we could not match to your profile."]
            if it["limit"]:
                cleaned = letter_limit.fit_to_limit(cleaned, it["limit_unit"], it["limit"])
            it.update(status="done" if cleaned else "failed", answer=cleaned, warnings=warnings)

    req.questions = items
    req.status = "done"
    req.error = None
