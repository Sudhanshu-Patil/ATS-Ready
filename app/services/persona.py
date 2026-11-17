"""The persona graph: what the assistant knows about the user, building up over time.

The profile (skills, experience, projects) is the base and is read directly. On top of it the graph stores what the
user tells and shows us while applying:

  fact    one-off answers the profile cannot hold (notice period, expected salary, work authorisation...). Asked
          once, reused everywhere. The assistant never guesses these: it asks.
  story   an answer the user approved (copied or saved). Used as an example of how they answer, next time a
          similar question appears.
  topic   the kind of question a story answers (why this company, biggest weakness, ...).
  skill   a technology or skill a story mentions.
  target  roles and skills they keep applying for (the trend across applications).
  style   how they write: typical answer length.

Edges: story -about-> topic, story -mentions-> skill. Retrieval walks them: stories on the same topic first, then
stories that mention the skills the job asks for, weighted by use and recency.
"""
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PersonaEdge, PersonaNode
from app.services.ats_score import _norm, term_in

# ── Questions: which kind, and which need a fact the profile does not hold ─────

FACT_FIELDS: Dict[str, Dict[str, Any]] = {
    "notice_period": {"label": "Notice period", "hint": "e.g. 30 days, or immediately available",
                      "pattern": r"notice period|how soon (?:can|could) you (?:start|join)|joining (?:time|date)|"
                                 r"earliest (?:start|joining)|when can you (?:start|join)|availab\w+ to (?:start|join)"},
    "expected_salary": {"label": "Expected salary", "hint": "e.g. 18-22 LPA, or $120k, or negotiable",
                        "pattern": r"expected (?:salary|ctc|compensation|pay)|salary expectations?|desired (?:salary|pay|compensation)|"
                                   r"compensation expectations?|what (?:salary|compensation) are you"},
    "current_salary": {"label": "Current salary", "hint": "e.g. 15 LPA. Leave blank to be asked each time",
                       "pattern": r"current (?:salary|ctc|compensation|pay)|present (?:salary|ctc)|what are you (?:currently )?(?:earning|making)"},
    "work_authorization": {"label": "Work authorisation", "hint": "e.g. Indian citizen, no sponsorship needed",
                           "pattern": r"authori[sz]ed to work|work authori[sz]ation|right to work|(?:require|need).{0,20}(?:visa|sponsorship)|"
                                      r"visa status|sponsorship"},
    "relocation": {"label": "Willing to relocate?", "hint": "e.g. yes, to Bangalore or Pune; or no, remote only",
                   "pattern": r"relocat"},
    "work_mode": {"label": "Remote / hybrid / on-site preference", "hint": "e.g. hybrid, 3 days in office",
                  "pattern": r"work (?:remotely|from home)|remote work|(?:on-?site|in-?office|hybrid)|comfortable commuting"},
}
# Voluntary demographic questions: the assistant never answers these for the user.
SENSITIVE = re.compile(r"\b(gender|sex\b|ethnic\w*|race\b|racial|disabilit\w+|veteran|religio\w+|sexual orientation|"
                       r"date of birth|marital status|pronouns?|caste|nationality)\b", re.I)

TOPICS = [
    ("about_me", r"tell (?:us|me) about yourself|introduce yourself|describe yourself|about you\b|your background"),
    ("why_company", r"why (?:do you want to )?(?:work|join)|why (?:are you )?(?:interested in|applying)|why us\b|"
                    r"why this company|what (?:interests|attracts|excites) you (?:about|to)"),
    ("why_role", r"why this (?:role|position)|why (?:are you )?(?:a good )?fit|what makes you (?:a good|the right)|"
                 r"why should we (?:hire|select|choose)"),
    ("strengths", r"strengths?|what are you (?:best|good) at|what do you bring"),
    ("weakness", r"weakness|area(?:s)? (?:of|for) improvement|what.{0,20}improve"),
    ("achievement", r"proud(?:est)? of|greatest achievement|accomplish\w+|biggest (?:win|success)|achievement"),
    ("challenge", r"challeng\w+|difficult (?:situation|problem)|hardest|toughest|problem you (?:solved|faced)"),
    ("conflict", r"conflict|disagree\w*|difficult (?:coworker|colleague|manager|stakeholder)"),
    ("leadership", r"lead(?:ership)?\b|led a team|mentor\w*|manage(?:d)? (?:a )?team"),
    ("teamwork", r"team ?work|collaborat\w+|work(?:ed)? (?:with|in) a team"),
    ("failure", r"fail\w*|mistake|learn(?:ed)? from"),
    ("career_goals", r"where do you see yourself|career goals?|long[- ]term|five years|5 years|next (?:role|step)"),
    ("why_leaving", r"why (?:are you )?(?:leaving|looking|want to leave|left)|reason for (?:leaving|change)"),
    ("technical", r"experience (?:with|in|using)|how (?:do|would) you (?:design|build|implement|debug)|explain\b|"
                  r"describe (?:your )?(?:experience|approach)|proficien\w+"),
]


def classify(question: str) -> Tuple[str, Optional[str], bool]:
    """(topic, fact field it needs or None, sensitive)"""
    q = question or ""
    if SENSITIVE.search(q):
        return "sensitive", None, True
    for field, spec in FACT_FIELDS.items():
        if re.search(spec["pattern"], q, re.I):
            return field, field, False
    for topic, pattern in TOPICS:
        if re.search(pattern, q, re.I):
            return topic, None, False
    return "other", None, False


_LIMIT = re.compile(r"(?:max(?:imum)?(?:\s+of)?|up to|no more than|limit(?:ed)?(?:\s+(?:of|to))?|within|under|not exceed(?:ing)?)"
                    r"\s*:?\s*(\d{2,5})\s*(words?|characters?|chars?)|(\d{2,5})\s*(words?|characters?|chars?)\s*(?:max|limit|maximum)", re.I)


def detect_limit(question: str) -> Tuple[Optional[int], Optional[str]]:
    """'(max 500 characters)' in the question itself -> (500, 'chars')"""
    m = _LIMIT.search(question or "")
    if not m:
        return None, None
    n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return int(n), ("words" if unit.lower().startswith("word") else "chars")


# ── Graph storage ────────────────────────────────────────────────────────────

def _key(text: str) -> str:
    return _norm(text).strip()[:200]


async def _node(db: AsyncSession, user_id: UUID, kind: str, key: str, label: str,
                data: Optional[Dict[str, Any]] = None, source: str = "system", bump: float = 0.0) -> PersonaNode:
    key = key[:200]
    node = (await db.execute(select(PersonaNode).where(
        PersonaNode.user_id == user_id, PersonaNode.kind == kind, PersonaNode.key == key))).scalar_one_or_none()
    if node is None:
        node = PersonaNode(user_id=user_id, kind=kind, key=key, label=label[:300], data=data or {}, source=source,
                           weight=1.0 + bump)
        db.add(node)
        await db.flush()
    else:
        node.weight = (node.weight or 1.0) + bump
        if data is not None:
            node.data = data
        node.label = label[:300]
    return node


async def _edge(db: AsyncSession, user_id: UUID, src: UUID, dst: UUID, relation: str) -> None:
    edge = (await db.execute(select(PersonaEdge).where(
        PersonaEdge.src == src, PersonaEdge.dst == dst, PersonaEdge.relation == relation))).scalar_one_or_none()
    if edge is None:
        db.add(PersonaEdge(user_id=user_id, src=src, dst=dst, relation=relation))
    else:
        edge.weight = (edge.weight or 1.0) + 0.5


async def set_fact(db: AsyncSession, user_id: UUID, field: str, value: str) -> PersonaNode:
    spec = FACT_FIELDS[field]
    return await _node(db, user_id, "fact", field, spec["label"], {"field": field, "value": value.strip()[:300]},
                       source="user")


async def facts(db: AsyncSession, user_id: UUID) -> Dict[str, str]:
    rows = (await db.execute(select(PersonaNode).where(
        PersonaNode.user_id == user_id, PersonaNode.kind == "fact"))).scalars().all()
    return {r.key: (r.data or {}).get("value", "") for r in rows if (r.data or {}).get("value")}


async def record_story(db: AsyncSession, user_id: UUID, topic: str, question: str, answer: str,
                       skills: Iterable[str] = ()) -> PersonaNode:
    """The user approved this answer: remember it, tie it to its topic and the skills it mentions."""
    story = await _node(db, user_id, "story", _key(question), question[:300],
                        {"topic": topic, "question": question[:600], "answer": answer[:2500]},
                        source="approved_answer", bump=0.5)
    topic_node = await _node(db, user_id, "topic", topic, topic.replace("_", " "))
    await _edge(db, user_id, story.id, topic_node.id, "about")
    for skill in list(dict.fromkeys(skills))[:8]:
        s = await _node(db, user_id, "skill", _key(skill), skill)
        await _edge(db, user_id, story.id, s.id, "mentions")
    await _record_style(db, user_id, answer)
    story.data = {**(story.data or {}), "approved_at": datetime.utcnow().isoformat()}
    return story


async def _record_style(db: AsyncSession, user_id: UUID, answer: str) -> None:
    words = len(answer.split())
    node = await _node(db, user_id, "style", "writing", "How you write")
    d = dict(node.data or {})
    n = int(d.get("n", 0))
    d["avg_words"] = round((float(d.get("avg_words", 0)) * n + words) / (n + 1), 1)
    d["n"] = n + 1
    node.data = d


async def record_target(db: AsyncSession, user_id: UUID, role: Optional[str], terms: Iterable[str]) -> None:
    """Applications build the trend: which roles and skills the user keeps going after."""
    if role:
        await _node(db, user_id, "target", "role:" + _key(role), role, {"type": "role"}, source="application", bump=1.0)
    for t in list(dict.fromkeys(terms))[:8]:
        await _node(db, user_id, "target", "skill:" + _key(t), t, {"type": "skill"}, source="application", bump=0.5)


async def retrieve(db: AsyncSession, user_id: UUID, topic: str, jd_terms: Iterable[str],
                   limit: int = 3) -> List[Dict[str, Any]]:
    """Approved answers most relevant to this question: same topic first, then those mentioning the job's skills."""
    stories = (await db.execute(select(PersonaNode).where(
        PersonaNode.user_id == user_id, PersonaNode.kind == "story"))).scalars().all()
    if not stories:
        return []
    ids = [s.id for s in stories]
    edges = (await db.execute(select(PersonaEdge).where(PersonaEdge.src.in_(ids)))).scalars().all()
    skill_ids = {e.dst for e in edges if e.relation == "mentions"}
    skill_labels = {n.id: n.label for n in (await db.execute(
        select(PersonaNode).where(PersonaNode.id.in_(skill_ids)))).scalars().all()} if skill_ids else {}
    job_norm = _norm(" ".join(jd_terms))
    scored = []
    for s in stories:
        mentioned = [skill_labels[e.dst] for e in edges if e.src == s.id and e.relation == "mentions"
                     and e.dst in skill_labels]
        score = (3.0 if (s.data or {}).get("topic") == topic else 0.0) \
            + sum(1.0 for m in mentioned if job_norm and term_in(m, job_norm)) \
            + 0.3 * (s.weight or 1.0) + 0.1 * (s.uses or 0)
        if score >= 1.0:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, s in scored[:limit]:
        s.uses = (s.uses or 0) + 1
        out.append({"question": (s.data or {}).get("question", s.label), "answer": (s.data or {}).get("answer", "")})
    return out


async def style(db: AsyncSession, user_id: UUID) -> Dict[str, Any]:
    node = (await db.execute(select(PersonaNode).where(
        PersonaNode.user_id == user_id, PersonaNode.kind == "style"))).scalar_one_or_none()
    return dict(node.data or {}) if node else {}


async def targets(db: AsyncSession, user_id: UUID, limit: int = 5) -> List[str]:
    rows = (await db.execute(select(PersonaNode).where(
        PersonaNode.user_id == user_id, PersonaNode.kind == "target").order_by(PersonaNode.weight.desc()).limit(limit * 2))
    ).scalars().all()
    return [r.label for r in rows][:limit]


async def corpus_extras(db: AsyncSession, user_id: UUID) -> Dict[str, Any]:
    """Text the user themselves supplied, so grounding treats it as theirs (facts and approved answers)."""
    return {"_facts": await facts(db, user_id),
            "_stories": [(s.data or {}).get("answer", "") for s in (await db.execute(select(PersonaNode).where(
                PersonaNode.user_id == user_id, PersonaNode.kind == "story"))).scalars().all()]}


# ── What the user can see and control ────────────────────────────────────────

async def overview(db: AsyncSession, user_id: UUID) -> Dict[str, Any]:
    nodes = (await db.execute(select(PersonaNode).where(PersonaNode.user_id == user_id)
                              .order_by(PersonaNode.weight.desc()))).scalars().all()
    by: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        by.setdefault(n.kind, []).append({"id": str(n.id), "label": n.label, "data": n.data, "weight": round(n.weight, 1),
                                           "uses": n.uses})
    return {"facts": by.get("fact", []), "stories": by.get("story", []), "targets": by.get("target", [])[:10],
            "style": (by.get("style") or [{}])[0].get("data", {}), "topics": by.get("topic", []),
            "counts": {k: len(v) for k, v in by.items()}}


async def forget(db: AsyncSession, user_id: UUID, node_id: UUID) -> bool:
    node = await db.get(PersonaNode, node_id)
    if node is None or node.user_id != user_id:
        return False
    await db.delete(node)
    return True


async def forget_all(db: AsyncSession, user_id: UUID) -> int:
    n = len((await db.execute(select(PersonaNode.id).where(PersonaNode.user_id == user_id))).all())
    await db.execute(delete(PersonaNode).where(PersonaNode.user_id == user_id))
    return n
