"""
app/services/compaction.py
──────────────────────────
Local (no LLM) shrinking of prompts so they fit free-tier token limits
without dropping what matters. Everything here is deterministic Python.

Rule of thumb used throughout: what the JD asks for is never dropped before
what it doesn't. Roles, skill names, education and contact links are never
removed at all; only low-relevance bullets and long free text are.
"""
import copy
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


def estimate_tokens(text: str) -> int:
    """Rough, provider-agnostic (~4 chars per token for English)."""
    return len(text) // 4 + 1


def _compact_json(obj: Any) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))


# ── helpers ───────────────────────────────────────────────────────────────────

_FIXES = (("c++", "cpp"), ("c#", "csharp"), (".net", "dotnet"), ("node.js", "nodejs"))


def _norm(text: str) -> str:
    t = (text or "").lower()
    for a, b in _FIXES:
        t = t.replace(a, b)
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", t)).strip() + " "


def _keyword_norms(keywords: Iterable[str]) -> List[str]:
    out, seen = [], set()
    for k in keywords:
        n = _norm(k)
        if n.strip() and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def relevance(text: str, kw_norms: List[str]) -> int:
    """How many distinct JD keywords appear (as whole words) in the text."""
    n = _norm(text)
    return sum(1 for k in kw_norms if k in n)


def head_tail(text: str, limit: int, tail_ratio: float = 0.25) -> str:
    """Keep the start AND the end of long text (education/links sit at the end)."""
    if len(text) <= limit:
        return text
    tail = int(limit * tail_ratio)
    head = limit - tail
    return f"{text[:head]}\n[... middle omitted ...]\n{text[-tail:]}"


# ── JD ────────────────────────────────────────────────────────────────────────

_KEEP_HEADING = re.compile(
    r"respons|require|qualif|skill|experience|what you|you will|you.ll|you have|"
    r"you bring|about the role|the role|must|nice to have|preferred|tech|stack|"
    r"looking for|duties|day to day|who you are|minimum|bonus", re.I)
_DROP_HEADING = re.compile(
    r"benefit|perk|equal opportunity|eeo|diversity|about us|who we are|our (story|mission|values)|"
    r"compensation|salary|how to apply|privacy|culture|why join|what we offer|covid|accommodation", re.I)


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 70:
        return False
    return s.endswith(":") or s.startswith("#") or (s.isupper() and len(s) > 3) or (
        len(s.split()) <= 6 and not s.endswith((".", ",", ";")) and s[0].isupper() and
        bool(_KEEP_HEADING.search(s) or _DROP_HEADING.search(s)))


def compact_jd(text: str, limit: int = 8000) -> str:
    """Shrink a job description to `limit` chars. Short JDs are returned as is.
    Otherwise drop boilerplate sections (benefits, EEO, about-us) first, and only
    then fall back to head+tail."""
    text = text.strip()
    if len(text) <= limit:
        return text

    blocks: List[Tuple[str, List[str]]] = [("", [])]       # (heading, lines)
    for line in text.splitlines():
        if _is_heading(line):
            blocks.append((line.strip(), []))
        else:
            blocks[-1][1].append(line)

    kept = []
    for i, (heading, lines) in enumerate(blocks):
        body = "\n".join(l for l in lines if l.strip())
        if i == 0 or not heading:                          # intro/title: always keep
            kept.append(body)
        elif _DROP_HEADING.search(heading) and not _KEEP_HEADING.search(heading):
            continue
        else:
            kept.append(f"{heading}\n{body}")
    out = "\n\n".join(k for k in kept if k.strip())
    return head_tail(out, limit)


# ── Profile ───────────────────────────────────────────────────────────────────

def _prune_empty(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def compact_profile(
    profile: Dict[str, Any],
    jd_keywords: Iterable[str],
    max_chars: int = 9000,
) -> Dict[str, Any]:
    """
    Fit a candidate profile into `max_chars` of compact JSON.

    Never removed: personal info/links, every role (title, company, dates),
    every skill NAME, education institution/degree. Removed in this order,
    lowest JD-relevance first: extra bullets (keeping 2 per role / 1 per
    project), long free text and skill keyword lists, then bullets down to 1
    per role, then the least relevant projects beyond the top 2.
    """
    kws = _keyword_norms(jd_keywords)
    p = copy.deepcopy(profile)
    p["personal"] = _prune_empty(p.get("personal") or {})
    p["education"] = [_prune_empty(e) for e in p.get("education", [])]
    p["skills"] = [_prune_empty(s) for s in p.get("skills", [])]
    p["experience"] = [_prune_empty(e) for e in p.get("experience", [])]
    p["projects"] = [_prune_empty(e) for e in p.get("projects", [])]

    def size() -> int:
        return len(_compact_json(p))

    def bullet_score(b: Dict[str, Any]) -> float:
        text = f"{b.get('text', '')} {' '.join(b.get('keywords') or [])}"
        return relevance(text, kws) * 10 + float(b.get("impact_score") or 0)

    def trim_bullets(min_keep_exp: int, min_keep_proj: int) -> None:
        cands = []                                         # (score, section, idx, bullet)
        for section, floor in (("experience", min_keep_exp), ("projects", min_keep_proj)):
            for i, item in enumerate(p[section]):
                bullets = item.get("bullets", [])
                for b in sorted(bullets, key=bullet_score, reverse=True)[floor:]:
                    cands.append((bullet_score(b), section, i, b))
        for _, section, i, b in sorted(cands, key=lambda c: c[0]):
            if size() <= max_chars:
                return
            p[section][i]["bullets"].remove(b)

    if size() <= max_chars:
        return p

    trim_bullets(min_keep_exp=2, min_keep_proj=1)
    if size() > max_chars:                                 # long free text / keyword lists
        for s in p["skills"]:
            s.pop("keywords", None)
        for e in p["education"]:
            e.pop("relevant_coursework", None)
        for pr in p["projects"]:
            pr.pop("description", None)
    if size() > max_chars:
        trim_bullets(min_keep_exp=1, min_keep_proj=0)
    if size() > max_chars:                                 # least relevant projects go
        def proj_score(pr: Dict[str, Any]) -> int:
            blob = f"{pr.get('title', '')} {' '.join(pr.get('tech_stack') or [])}"
            blob += " ".join(b.get("text", "") for b in pr.get("bullets", []))
            return relevance(blob, kws)
        p["projects"].sort(key=proj_score, reverse=True)
        while len(p["projects"]) > 2 and size() > max_chars:
            p["projects"].pop()
    return p


def profile_as_tailored(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Cheap stand-in for the LLM-tailored resume, used as context by cover
    letter and interview prep (replaces an extra LLM call)."""
    by_cat: Dict[str, List[str]] = {}
    for s in profile.get("skills", []):
        by_cat.setdefault(s.get("category") or "Skills", []).append(s.get("name", ""))
    return {
        "professional_summary": (profile.get("personal") or {}).get("professional_summary") or "",
        "skills": [{"category": c, "items": items} for c, items in by_cat.items()],
        "work_experience": [
            {"company": e.get("company", ""), "role": e.get("role", ""),
             "bullets": [b.get("text", "") for b in e.get("bullets", [])]}
            for e in profile.get("experience", [])
        ],
        "projects": [
            {"title": pr.get("title", ""), "tech_stack": pr.get("tech_stack", []),
             "bullets": [b.get("text", "") for b in pr.get("bullets", [])]}
            for pr in profile.get("projects", [])
        ],
    }


# ── Resume text for scoring ───────────────────────────────────────────────────

def resume_text_for_scoring(tailored: Dict[str, Any], limit: int = 5000) -> str:
    """Flatten a tailored resume to plain text field by field, instead of
    slicing its JSON mid-object (which dropped whole later sections)."""
    parts: List[str] = [tailored.get("professional_summary") or ""]
    for s in tailored.get("skills", []) or []:
        if isinstance(s, dict):
            parts.append(f"{s.get('category', '')}: {', '.join(map(str, s.get('items') or []))}")
    for key in ("work_experience", "projects"):
        for e in tailored.get(key, []) or []:
            if isinstance(e, dict):
                parts.append(f"{e.get('role') or e.get('title') or ''} {e.get('company') or ''}")
                parts.extend(map(str, e.get("bullets") or []))
    return head_tail("\n".join(p for p in parts if p.strip()), limit)


# ── Local ATS score (used when the model's scoring JSON is unusable) ──────────

_ACTION_VERB = re.compile(
    r"^(built|led|designed|developed|implemented|created|improved|reduced|increased|"
    r"launched|migrated|optimized|optimised|automated|delivered|architected|managed|"
    r"owned|shipped|integrated|deployed|analy[sz]ed|streamlined|mentored|drove|"
    r"scaled|refactored|established|spearheaded|engineered|collaborated)\b", re.I)


def local_ats_score(jd_keywords: List[str], required_skills: List[str],
                    tailored: Dict[str, Any]) -> Dict[str, Any]:
    """Keyword/skill overlap scoring done locally. Same keys as the LLM scorer,
    plus estimated=True so the UI/API can tell it apart."""
    text = _norm(resume_text_for_scoring(tailored, limit=20000))
    split = lambda terms: ([t for t in dict.fromkeys(terms) if _norm(t).strip() and _norm(t) in text],
                           [t for t in dict.fromkeys(terms) if _norm(t).strip() and _norm(t) not in text])
    kw_hit, kw_miss = split(jd_keywords)
    sk_hit, sk_miss = split(required_skills)
    kw, sk = kw_hit + kw_miss, sk_hit + sk_miss
    pct = lambda hit, total: 100.0 * len(hit) / len(total) if total else 0.0

    bullets = [str(b) for key in ("work_experience", "projects")
               for e in tailored.get(key, []) or [] if isinstance(e, dict)
               for b in e.get("bullets") or []]
    verbs = 100.0 * sum(1 for b in bullets if _ACTION_VERB.match(b.strip())) / len(bullets) if bullets else 0.0

    keyword_score, skills_score = pct(kw_hit, kw), pct(sk_hit, sk)
    format_score = 85.0       # the .docx builder emits a single-column, ATS-safe layout
    total = 0.40 * keyword_score + 0.30 * skills_score + 0.15 * verbs + 0.15 * format_score
    return {
        "keyword_score": round(keyword_score, 1), "skills_score": round(skills_score, 1),
        "action_verb_score": round(verbs, 1), "format_score": format_score,
        "total_score": round(total, 1),
        "matched_keywords": kw_hit, "missing_keywords": kw_miss,
        "matched_skills": sk_hit, "missing_skills": sk_miss,
        "suggestions": [], "estimated": True,
    }
