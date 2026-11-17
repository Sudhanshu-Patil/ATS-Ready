"""Never state what the candidate did not say.

The model is told not to invent numbers, tools, employers or titles, but models still do it, so this module
enforces it in code on the way out. A resume or cover letter may only REWORD the candidate's own material:

  * employers, roles, dates and locations come from the profile, not from the model;
  * a number in a bullet, summary or letter must appear in the candidate's own material;
  * a JD technology (Kubernetes, Terraform...) may not appear in a bullet the candidate never wrote about it;
  * skills must be in the profile, or confirmed by the user (ticked "I have this", or present in the resume
    they uploaded). Confirmed terms go in the skills list only, never into invented experience.

A bullet that breaks a rule is replaced by the candidate's own closest original bullet (or dropped); a summary or
letter sentence that breaks one is removed.
"""
import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.services.ats_score import _norm, term_in

logger = logging.getLogger(__name__)

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[a-z0-9+#.]+")


def numbers_in(text: str) -> Set[str]:
    """Numeric tokens, comma-insensitive: '2,000' -> '2000'."""
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text or "")}


def source_text(profile: Dict[str, Any]) -> str:
    """Everything the candidate wrote, flattened."""
    out: List[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(str(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(profile)
    return "\n".join(out)


def _years(profile: Dict[str, Any]) -> Set[str]:
    """Years of experience derived from the dates ("5 years"): a figure the candidate's own data implies."""
    from datetime import datetime
    starts = []
    for e in profile.get("experience", []) or []:
        m = re.search(r"(19|20)\d{2}", str(e.get("start_date") or ""))
        if m:
            starts.append(int(m.group(0)))
    if not starts:
        return set()
    n = datetime.now().year - min(starts)
    return {str(n), str(max(n - 1, 0)), str(n + 1)}


def allowed_numbers(profile: Dict[str, Any], extra_text: str = "") -> Set[str]:
    return numbers_in(source_text(profile) + "\n" + extra_text) | _years(profile)


def _tokens(text: str) -> Set[str]:
    return set(_WORD.findall((text or "").lower()))


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def violation(text: str, allowed_nums: Set[str], corpus_norm: str, jd_terms: Iterable[str]) -> Optional[str]:
    """Why `text` claims something the candidate never said, or None."""
    bad_nums = numbers_in(text) - allowed_nums
    if bad_nums:
        return f"number {sorted(bad_nums)[0]} is not in the candidate's data"
    norm = _norm(text)
    for t in jd_terms:
        if term_in(t, norm) and not term_in(t, corpus_norm):
            return f"'{t}' is not in the candidate's data"
    return None


def _entity_bullets(entity: Dict[str, Any]) -> List[str]:
    return [b.get("text", "") if isinstance(b, dict) else str(b) for b in entity.get("bullets") or []]


def _fix_bullets(bullets: List[str], source_bullets: List[str], other_sources: List[str],
                 allowed: Set[str], corpus_norm: str, jd_terms: List[str], report: List[str]) -> List[str]:
    """Keep honest bullets; swap a dishonest one for the closest original; never leave an entry empty."""
    out: List[str] = []
    used = set()
    for b in bullets:
        why = violation(b, allowed, corpus_norm, jd_terms)
        if why is None:
            out.append(b)
            continue
        pool = [s for s in source_bullets + other_sources if s and s not in out and s not in used]
        best = max(pool, key=lambda s: _overlap(b, s), default=None)
        if best is not None and _overlap(b, best) >= 0.2:
            out.append(best)
            used.add(best)
        report.append(f"bullet replaced ({why})")
    if not out:
        out = [s for s in source_bullets if s][:2]
    return out


def enforce_resume(tailored: Dict[str, Any], profile: Dict[str, Any], jd_terms: List[str],
                   confirmed: Iterable[str] = ()) -> Tuple[Dict[str, Any], List[str]]:
    """Return (tailored limited to the candidate's own facts, report of what was corrected)."""
    from app.services.compaction import ground_skills

    report: List[str] = []
    confirmed = [c for c in confirmed if c]
    corpus = source_text(profile)
    corpus_norm = _norm(corpus)
    allowed = allowed_numbers(profile)
    out = dict(tailored)

    # Experience: employer, role, dates and location are the candidate's, whatever the model wrote.
    exps = {_norm(str(e.get("company"))).strip(): e for e in profile.get("experience", []) or []}
    all_exp_bullets = [b for e in exps.values() for b in _entity_bullets(e)]
    fixed_exp = []
    for e in tailored.get("work_experience") or []:
        src = exps.get(_norm(str(e.get("company"))).strip())
        if src is None:
            report.append(f"dropped an employer not in the profile: {e.get('company')}")
            continue
        fixed_exp.append({
            **e, "company": src.get("company"), "role": src.get("role"), "location": src.get("location") or "",
            "start_date": src.get("start_date"), "end_date": src.get("end_date") or "Present",
            "bullets": _fix_bullets(list(e.get("bullets") or []), _entity_bullets(src), all_exp_bullets,
                                    allowed, corpus_norm, jd_terms, report)})
    out["work_experience"] = fixed_exp

    projs = {_norm(str(p.get("title"))).strip(): p for p in profile.get("projects", []) or []}
    fixed_proj = []
    for p in tailored.get("projects") or []:
        src = projs.get(_norm(str(p.get("title"))).strip())
        if src is None:
            report.append(f"dropped a project not in the profile: {p.get('title')}")
            continue
        fixed_proj.append({
            **p, "title": src.get("title"), "tech_stack": list(src.get("tech_stack") or [])[:6],
            "github_url": src.get("github_url"),
            "bullets": _fix_bullets(list(p.get("bullets") or []), _entity_bullets(src), [], allowed, corpus_norm,
                                    jd_terms, report)})
    out["projects"] = fixed_proj

    out["professional_summary"] = _fix_summary(tailored.get("professional_summary") or "", profile, allowed,
                                               corpus_norm, jd_terms, report)

    # Skills: the profile's, plus what the user confirmed.
    out, dropped = ground_skills(out, {**profile, "_confirmed": confirmed})
    if dropped:
        report.append(f"skills not in the profile removed: {dropped}")
    for line in report:
        logger.info("grounding: %s", line)
    return out, report


def _fix_summary(summary: str, profile: Dict[str, Any], allowed: Set[str], corpus_norm: str,
                 jd_terms: List[str], report: List[str]) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", summary.strip()) if s]
    kept = [s for s in sentences if violation(s, allowed, corpus_norm, jd_terms) is None]
    if len(kept) < len(sentences):
        report.append("summary sentences with unsupported claims removed")
    if kept:
        return " ".join(kept)
    own = ((profile.get("personal") or {}).get("professional_summary") or "").strip()
    return own


def add_known_terms(tailored: Dict[str, Any], terms: Iterable[str], max_new: int = 8) -> Tuple[Dict[str, Any], List[str]]:
    """Put JD terms the candidate owns (profile or confirmed) but the resume left out into the skills list.
    Returns (tailored, terms added). This is what makes the first version already as strong as honest data allows."""
    text = _norm(json.dumps({k: v for k, v in tailored.items() if k in ("skills", "work_experience", "projects",
                                                                           "professional_summary")}, default=str))
    missing = [t for t in dict.fromkeys(terms) if t and not term_in(t, text)][:max_new]
    if not missing:
        return tailored, []
    groups = [dict(g) for g in tailored.get("skills") or []]
    groups.append({"category": "Also Relevant", "items": missing})
    return {**tailored, "skills": groups}, missing


# ── Cover letter ─────────────────────────────────────────────────────────────

# A sentence that CLAIMS experience ("I have used X", "my experience with X", "hands-on X"), as opposed to one
# that merely mentions the company's stack ("your platform runs on X").
_FIRST_PERSON = re.compile(
    r"\b(I've|I have|I had|I am (?:an? )?(?:experienced|expert|skilled|proficient)|"
    r"I (?:built|led|worked|used|managed|developed|designed|deployed|ran|wrote|shipped|implemented|created|"
    r"delivered|owned|maintained|operated|scaled|migrated)|my (?:experience|work|background|expertise)|"
    r"experience (?:with|in|using)|worked (?:with|on)|hands-on|years of|expertise|proficient)\b", re.I)


def enforce_letter(body: str, profile: Dict[str, Any], jd_text: str, jd_terms: List[str],
                   confirmed: Iterable[str] = ()) -> Tuple[str, List[str]]:
    """Remove sentences that state a figure the candidate never gave, or claim a technology they do not have.
    Numbers from the job posting itself are fine to mention (they describe the job, not the candidate)."""
    report: List[str] = []
    corpus_norm = _norm(source_text(profile) + "\n" + "\n".join(confirmed))
    allowed = allowed_numbers(profile, extra_text=jd_text)
    out_paras: List[str] = []
    for para in body.replace("\r\n", "\n").split("\n\n"):
        lines_out = []
        for line in para.split("\n"):
            kept = []
            for sent in [s for s in re.split(r"(?<=[.!?])\s+", line) if s]:
                bad_num = numbers_in(sent) - allowed
                claim = _FIRST_PERSON.search(sent) is not None
                bad_term = [t for t in jd_terms if term_in(t, _norm(sent)) and not term_in(t, corpus_norm)] if claim else []
                if bad_num or bad_term:
                    report.append(f"letter sentence removed ({sorted(bad_num) or bad_term})")
                    continue
                kept.append(sent)
            if kept:
                lines_out.append(" ".join(kept))
        if lines_out:
            out_paras.append("\n".join(lines_out))
    return "\n\n".join(out_paras), report
