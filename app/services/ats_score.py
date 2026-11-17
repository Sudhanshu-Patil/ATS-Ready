"""Deterministic ATS scoring and the technical gap list ("suggestions").

Why no LLM here: the model-judged score and "missing keywords" changed on every run, so scores wobbled and
new suggestions kept appearing. Everything below is a pure function of (job description, resume text): the same
inputs always give the same score and the same list, which also makes the uploaded resume and the generated one
directly comparable.

Score (0-100)  =  45% required skills present  +  25% other JD keywords present
                +  15% bullets starting with an action verb  +  15% structure (sections + contact details)

Suggestions are TECHNICAL terms the job description asks for that appear nowhere in the candidate's own
material (profile, or the resume they uploaded). Soft skills and generic wording are never suggested.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.models.schemas import ParsedJD
from app.services.compaction import _ACTION_VERB, resume_text_for_scoring

# Not technical: never a suggestion, never counted in the score.
SOFT_TERMS = {
    "communication", "communications", "teamwork", "team player", "collaboration", "collaborative", "leadership",
    "problem solving", "problem-solving", "critical thinking", "fast-paced", "fast paced", "passion", "passionate",
    "detail oriented", "detail-oriented", "self-starter", "self starter", "ownership", "proactive", "motivated",
    "interpersonal", "organizational", "organisational", "time management", "adaptability", "creativity",
    "english", "fluent english", "written communication", "verbal communication", "multitasking", "initiative",
    "work ethic", "attention to detail", "strong communication", "team", "teams", "mentoring", "mentorship",
    "stakeholder management", "customer focus", "results driven", "results-driven", "dynamic", "innovative",
    "excellent", "strong", "experience", "skills", "knowledge", "ability", "understanding", "proficiency",
}
_GENERIC_WORDS = {"and", "or", "the", "a", "an", "of", "to", "in", "for", "with", "on", "at", "years", "year",
                  "plus", "good", "great", "excellent", "strong", "solid", "proven", "familiarity"}
_KIND_WEIGHT = {"required": 3, "preferred": 2, "keyword": 1}
_WHY = {"required": "Listed as a required skill in the job description",
        "preferred": "Listed as a preferred skill in the job description",
        "keyword": "A key term in the job description"}


def _norm(text: str) -> str:
    from app.services.job_recommendations import _normalise
    return _normalise(text or "")


def term_in(term: str, norm_text: str) -> bool:
    """Alias-aware whole-word match ("Postgres" finds PostgreSQL, "K8s" finds Kubernetes)."""
    from app.services.job_recommendations import _has, _skill_variants
    return any(_has(v, norm_text) for v in _skill_variants(term))


def is_technical(term: str) -> bool:
    t = (term or "").strip()
    n = t.lower().strip(" .,:;")
    if not n or len(t) > 40 or len(n.split()) > 4:
        return False
    if n in SOFT_TERMS or all(w in _GENERIC_WORDS or w in SOFT_TERMS for w in re.split(r"[\s/-]+", n)):
        return False
    return bool(re.search(r"[a-z0-9]", n))


@dataclass
class Term:
    term: str
    kind: str                     # required | preferred | keyword
    importance: int = 0

    def key(self) -> str:
        return _norm(self.term).strip()


def jd_terms(jd: ParsedJD) -> List[Term]:
    """The technical terms the job asks for, most important first. A term keeps its strongest kind."""
    raw = _norm(jd.raw_text or "")
    seen: Dict[str, Term] = {}
    for kind, items in (("required", jd.required_skills), ("preferred", jd.preferred_skills), ("keyword", jd.keywords)):
        for item in items or []:
            if not is_technical(str(item)):
                continue
            t = Term(str(item).strip(), kind)
            k = t.key()
            if not k or k in seen:
                continue
            mentions = len(re.findall(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", raw)) if raw else 0
            t.importance = _KIND_WEIGHT[kind] * 10 + min(mentions, 5)
            seen[k] = t
    return sorted(seen.values(), key=lambda t: (-t.importance, t.term.lower()))


@dataclass
class ResumeView:
    """What the scorer needs from a resume, whether it is structured (ours) or free text (uploaded)."""
    text: str
    bullets: List[str] = field(default_factory=list)
    sections: int = 0             # of summary / skills / experience / education
    contact: int = 0              # of email / phone-or-location


def view_from_resume(personal: Dict[str, Any], tailored: Dict[str, Any], education: Sequence[Any]) -> ResumeView:
    bullets = [str(b) for key in ("work_experience", "projects") for e in tailored.get(key) or []
               if isinstance(e, dict) for b in e.get("bullets") or []]
    sections = sum([bool(tailored.get("professional_summary")), bool(tailored.get("skills")),
                    bool(tailored.get("work_experience")), bool(education)])
    contact = int(bool(personal.get("email"))) + int(bool(personal.get("phone") or personal.get("location")))
    return ResumeView(resume_text_for_scoring(tailored, limit=30000), bullets, sections, contact)


_HEADINGS = {"summary": r"summary|profile|objective", "skills": r"skills|technologies|tech stack",
             "experience": r"experience|employment|work history", "education": r"education|academics"}


def view_from_text(text: str) -> ResumeView:
    """Free text of an uploaded resume (PDF/DOCX): bullets are lines that start with a bullet mark or a verb."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    bullets = [re.sub(r"^[•●▪\-*–]+\s*", "", ln) for ln in lines
               if re.match(r"^[•●▪\-*–]\s*\S", ln) or _ACTION_VERB.match(ln)]
    low = "\n".join(lines).lower()
    sections = sum(bool(re.search(rf"(?m)^\W*({pat})\W*$", low)) for pat in _HEADINGS.values())
    contact = int(bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text or ""))) + int(
        bool(re.search(r"\+?\d[\d\s().-]{8,}\d", text or "")))
    return ResumeView(text or "", bullets, sections, contact)


def score_view(view: ResumeView, terms: List[Term], extra_terms: Iterable[str] = ()) -> Dict[str, Any]:
    """Breakdown dict (same keys the UI already shows). extra_terms are treated as present: used to project
    the score if the user adds suggestions."""
    norm = _norm(view.text + " " + " ".join(extra_terms))
    req = [t for t in terms if t.kind == "required"]
    other = [t for t in terms if t.kind != "required"]

    def split(group: List[Term]) -> Tuple[List[str], List[str]]:
        hit = [t.term for t in group if term_in(t.term, norm)]
        return hit, [t.term for t in group if t.term not in hit]

    req_hit, req_miss = split(req)
    oth_hit, oth_miss = split(other)
    skills_score = 100.0 * len(req_hit) / len(req) if req else (100.0 * len(oth_hit) / len(other) if other else 0.0)
    keyword_score = 100.0 * len(oth_hit) / len(other) if other else skills_score
    verbs = 100.0 * sum(1 for b in view.bullets if _ACTION_VERB.match(b.strip())) / len(view.bullets) if view.bullets else 0.0
    fmt = 100.0 * (0.6 * view.sections / 4 + 0.4 * view.contact / 2)
    total = 0.45 * skills_score + 0.25 * keyword_score + 0.15 * verbs + 0.15 * fmt
    return {
        "keyword_score": round(keyword_score, 1), "skills_score": round(skills_score, 1),
        "action_verb_score": round(verbs, 1), "format_score": round(fmt, 1), "total_score": round(total, 1),
        "matched_keywords": oth_hit, "missing_keywords": oth_miss,
        "matched_skills": req_hit, "missing_skills": req_miss,
        "suggestions": [], "method": "deterministic",
    }


# ── Suggestions ──────────────────────────────────────────────────────────────

MAX_SUGGESTIONS = 12


def build_suggestions(terms: List[Term], owned_text: str) -> List[Dict[str, Any]]:
    """Technical gaps: JD terms found nowhere in the candidate's own material. Computed ONCE per job
    description and then kept (see resume_suggestions): never regenerated, so they cannot keep changing."""
    norm = _norm(owned_text)
    gaps = [t for t in terms if not term_in(t.term, norm)]
    return [{"term": t.term, "kind": t.kind, "why": _WHY[t.kind], "importance": t.importance, "status": "open"}
            for t in gaps[:MAX_SUGGESTIONS]]


def terms_owned(terms: List[Term], owned_text: str) -> List[str]:
    """JD terms the candidate's own material already contains."""
    norm = _norm(owned_text)
    return [t.term for t in terms if term_in(t.term, norm)]


def parse_term_list(values: Optional[Iterable[str]]) -> List[str]:
    return [v.strip() for v in values or [] if v and v.strip()]
