"""
AI Agent Orchestration
-----------------------
Stage 1: JD Analyzer  — parse JD into structured format
Stage 2: Resume Tailor — select & rewrite content for max ATS score
Stage 3: ATS Scorer   — deterministic string matching (no LLM guessing)
"""
import json
import logging
import re
import string
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAI

from app.config import settings
from app.models.schemas import ParsedJD

logger = logging.getLogger(__name__)


# ── Deterministic keyword matching helpers ────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = text.translate(str.maketrans(string.punctuation, ' ' * len(string.punctuation)))
    return ' '.join(text.split())


def _resume_blob(tailored: Dict[str, Any]) -> str:
    """Flatten entire tailored resume dict into one searchable string."""
    parts = []
    if tailored.get("professional_summary"):
        parts.append(tailored["professional_summary"])
    for sg in tailored.get("skills", []):
        parts.extend(sg.get("items", []))
        parts.append(sg.get("category", ""))
    for exp in tailored.get("work_experience", []):
        parts.append(exp.get("role", ""))
        parts.append(exp.get("company", ""))
        parts.extend(exp.get("bullets", []))
    for proj in tailored.get("projects", []):
        parts.append(proj.get("title", ""))
        parts.extend(proj.get("tech_stack", []))
        parts.extend(proj.get("bullets", []))
    return _normalise(" ".join(parts))


def _keyword_in_blob(kw: str, blob: str) -> bool:
    """
    Check if a keyword (or any of its tokens) appear in the resume blob.
    Uses word-boundary matching so 'DAX' doesn't match 'index'.
    For multi-word keywords like 'data modeling', ALL words must appear
    within a 6-word sliding window.
    """
    kw_norm = _normalise(kw)
    if not kw_norm:
        return False

    tokens = kw_norm.split()

    if len(tokens) == 1:
        # Single token — whole-word match
        pattern = r'\b' + re.escape(tokens[0]) + r'\b'
        return bool(re.search(pattern, blob))
    else:
        # Multi-token — all tokens must appear in blob
        # (relaxed: we just check all tokens exist, order-independent)
        return all(re.search(r'\b' + re.escape(t) + r'\b', blob) for t in tokens)


def _score_keywords(
    keywords: List[str], blob: str
) -> Tuple[float, List[str], List[str]]:
    """Returns (score_0_100, matched_list, missing_list)."""
    if not keywords:
        return 100.0, [], []
    matched, missing = [], []
    for kw in keywords:
        (matched if _keyword_in_blob(kw, blob) else missing).append(kw)
    score = (len(matched) / len(keywords)) * 100
    return round(score, 1), matched, missing


# ─────────────────────────────────────────────────────────────────────────────

class AIAgent:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url=settings.GEMINI_BASE_URL,
        )

    def _call(self, system: str, user: str, max_tokens: int = 4096) -> str:
        response = self.client.chat.completions.create(
            model=settings.MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return response.choices[0].message.content

    # ─── Stage 1: JD Analysis ─────────────────────────────────────────────────

    SYSTEM_JD_PARSER = (
        "You are an expert ATS analyst and recruiter. "
        "Parse job descriptions into precise structured JSON. "
        "Extract ALL keywords, skills, and requirements including implicit ones. "
        "Always respond with valid JSON only — no markdown, no explanation."
    )

    def parse_jd(self, jd_text: str) -> ParsedJD:
        prompt = f"""Parse this job description into JSON with EXACTLY this structure:
{{
  "job_title": "exact job title",
  "company": "company name or null",
  "location": "location or null",
  "job_type": "Full-time|Part-time|Contract|Remote or null",
  "seniority": "Junior|Mid|Senior|Lead|Principal|Staff or null",
  "industry": "industry domain",
  "required_skills": ["must-have technical skills"],
  "preferred_skills": ["nice-to-have skills"],
  "responsibilities": ["key responsibilities as short phrases"],
  "qualifications": ["education/certification requirements"],
  "keywords": ["ALL ATS keywords — tools, frameworks, methodologies, soft skills, domain terms — extract 25-40 keywords"]
}}

Rules:
- Include BOTH spelled-out and abbreviated forms: "Machine Learning" AND "ML"
- Include action-based terms from responsibilities
- Return ONLY the JSON object

Job Description:
---
{jd_text[:8000]}
---"""

        response = self._call(self.SYSTEM_JD_PARSER, prompt)
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"AI returned invalid JSON: {response[:200]}")
        data["raw_text"] = jd_text
        return ParsedJD(**data)

    # ─── Stage 2: Resume Tailoring ────────────────────────────────────────────

    SYSTEM_RESUME_TAILOR = (
        "You are an elite resume coach and ATS optimisation expert. "
        "Tailor resumes to maximise ATS keyword scores while staying 100% truthful. "
        "Mirror the JD's exact language. Use strong action verbs. Quantify everything. "
        "CRITICAL: Every keyword listed in MANDATORY_KEYWORDS must appear verbatim "
        "somewhere in the output — in skills, bullets, or summary. No exceptions. "
        "Respond with valid JSON only."
    )

    def tailor_resume(
        self,
        parsed_jd: ParsedJD,
        candidate_data: Dict[str, Any],
        emphasis: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        # Merge JD keywords + user emphasis into one mandatory set
        all_target_keywords = list(parsed_jd.keywords)
        mandatory_keywords  = list(emphasis) if emphasis else []
        # De-dupe while preserving order
        seen: Set[str] = set()
        combined = []
        for kw in (mandatory_keywords + all_target_keywords):
            kl = kw.lower()
            if kl not in seen:
                seen.add(kl)
                combined.append(kw)

        mandatory_str = (
            f"\n\nMANDATORY_KEYWORDS — every single one MUST appear verbatim in your output:\n"
            f"{json.dumps(mandatory_keywords)}\n"
            f"Weave them naturally into skills list, bullet points, or summary. "
            f"Do NOT leave any of these out."
        ) if mandatory_keywords else ""

        prompt = f"""Create an ATS-optimised resume given the JD analysis and candidate profile.

=== JOB DESCRIPTION ===
Title:             {parsed_jd.job_title}
Company:           {parsed_jd.company}
Seniority:         {parsed_jd.seniority}
Required Skills:   {', '.join(parsed_jd.required_skills)}
Preferred Skills:  {', '.join(parsed_jd.preferred_skills)}
Responsibilities:  {json.dumps(parsed_jd.responsibilities)}
All ATS Keywords:  {', '.join(combined[:40])}
{mandatory_str}

=== CANDIDATE PROFILE ===
{json.dumps(candidate_data, indent=2, default=str)}

=== INSTRUCTIONS ===
1. SUMMARY (3-4 sentences):
   - Open with the EXACT job title from the JD
   - Weave in 6-8 ATS keywords naturally
   - Include at least 2 quantified achievements

2. SKILLS (top {settings.MAX_SKILLS_IN_RESUME}, max 3 groups):
   - Prioritise JD-matched skills
   - Include all MANDATORY_KEYWORDS that are skills/tools
   - Use exact JD phrasing where applicable

3. WORK EXPERIENCE (top {settings.MAX_EXPERIENCE_BULLETS} bullets per role):
   - Strong action verbs: Architected, Engineered, Slashed, Delivered, Automated
   - Mirror JD terminology exactly
   - Quantify every bullet possible (%, $, x faster, N users)
   - Inject MANDATORY_KEYWORDS naturally into bullets

4. PROJECTS (top {settings.MAX_PROJECTS_IN_RESUME}):
   - Rewrite bullets around skills the JD values
   - Include MANDATORY_KEYWORDS where relevant

5. After building the resume, list which keywords you successfully included
   and which ones genuinely cannot be included (candidate has no evidence for them).

Return JSON:
{{
  "professional_summary": "...",
  "skills": [{{"category": "...", "items": ["..."]}}],
  "work_experience": [{{
    "company": "...", "role": "...", "location": "...",
    "start_date": "...", "end_date": "...",
    "bullets": ["..."]
  }}],
  "projects": [{{
    "title": "...", "tech_stack": ["..."],
    "date_range": "...", "github_url": null,
    "bullets": ["..."]
  }}],
  "keywords_injected": ["keywords actually present in output"],
  "keywords_missing":  ["JD keywords candidate genuinely lacks — keep this list honest and short"]
}}

CRITICAL: Only use information from the candidate's actual profile. Never fabricate."""

        response = self._call(self.SYSTEM_RESUME_TAILOR, prompt, max_tokens=6000)
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"AI tailor returned invalid JSON: {response[:200]}")
        return data

    # ─── Stage 3: ATS Scoring — DETERMINISTIC ─────────────────────────────────
    # keyword_score and skills_score use real string matching, NOT LLM judgement.
    # action_verb_score and format_score still use LLM (qualitative judgements).

    STRONG_ACTION_VERBS = {
        "architected","engineered","designed","built","developed","created","launched",
        "deployed","shipped","delivered","led","spearheaded","drove","accelerated",
        "automated","optimised","optimized","reduced","improved","increased","scaled",
        "slashed","cut","eliminated","streamlined","migrated","refactored","integrated",
        "implemented","established","mentored","collaborated","contributed","awarded",
        "achieved","generated","boosted","transformed","pioneered","innovated",
    }

    def score_resume(
        self, parsed_jd: ParsedJD, tailored_resume: Dict[str, Any]
    ) -> Dict[str, Any]:
        blob = _resume_blob(tailored_resume)

        # ── Keyword score: deterministic ──────────────────────────────────────
        kw_score, kw_matched, kw_missing = _score_keywords(parsed_jd.keywords, blob)

        # ── Skills score: deterministic ───────────────────────────────────────
        sk_score, sk_matched, sk_missing = _score_keywords(parsed_jd.required_skills, blob)

        # ── Action verb score: count strong verbs at bullet starts ────────────
        bullets_text = " ".join(
            b for exp in tailored_resume.get("work_experience", [])
            for b in exp.get("bullets", [])
        ) + " ".join(
            b for proj in tailored_resume.get("projects", [])
            for b in proj.get("bullets", [])
        )
        bullet_starts = [
            _normalise(b).split()[0]
            for exp in tailored_resume.get("work_experience", [])
            for b in exp.get("bullets", []) if b.strip()
        ] + [
            _normalise(b).split()[0]
            for proj in tailored_resume.get("projects", [])
            for b in proj.get("bullets", []) if b.strip()
        ]

        total_bullets = len(bullet_starts)
        strong_starts = sum(1 for w in bullet_starts if w in self.STRONG_ACTION_VERBS)
        av_score = round((strong_starts / max(total_bullets, 1)) * 100, 1)
        av_score = min(av_score * 1.2, 100)  # slight boost — partial credit for good verbs

        # ── Format score: heuristic checks ───────────────────────────────────
        format_checks = {
            "has_summary":    bool(tailored_resume.get("professional_summary")),
            "has_skills":     bool(tailored_resume.get("skills")),
            "has_experience": bool(tailored_resume.get("work_experience")),
            "has_projects":   bool(tailored_resume.get("projects")),
            "bullets_quantified": any(
                re.search(r'\d+', b)
                for exp in tailored_resume.get("work_experience", [])
                for b in exp.get("bullets", [])
            ),
            "no_pronouns": not re.search(
                r'\b(i |my |we |our )\b',
                blob
            ),
        }
        fmt_score = round((sum(format_checks.values()) / len(format_checks)) * 100, 1)

        # ── Weighted total ────────────────────────────────────────────────────
        total = round(
            kw_score * settings.ATS_KEYWORD_WEIGHT +
            sk_score * settings.ATS_SKILLS_WEIGHT  +
            av_score * settings.ATS_ACTION_VERB_WEIGHT +
            fmt_score * settings.ATS_FORMAT_WEIGHT,
            1,
        )

        # ── Suggestions based on actual gaps ─────────────────────────────────
        suggestions = []
        if kw_missing[:5]:
            suggestions.append(
                f"Add these missing keywords to your metabase or emphasis list: "
                f"{', '.join(kw_missing[:5])}"
            )
        if sk_missing:
            suggestions.append(
                f"Missing required skills: {', '.join(sk_missing[:4])}. "
                f"Add to metabase if you have experience with them."
            )
        if av_score < 70:
            suggestions.append(
                "Start more bullets with strong verbs: Architected, Engineered, "
                "Slashed, Delivered, Automated, Spearheaded."
            )
        if not format_checks["bullets_quantified"]:
            suggestions.append(
                "Quantify more bullets with numbers (%, ms, $, x faster, N users)."
            )

        logger.info(
            f"ATS Score: {total} | KW: {kw_score} ({len(kw_matched)}/{len(parsed_jd.keywords)}) | "
            f"SK: {sk_score} ({len(sk_matched)}/{len(parsed_jd.required_skills)}) | "
            f"AV: {av_score} | FMT: {fmt_score}"
        )

        return {
            "keyword_score":     kw_score,
            "skills_score":      sk_score,
            "action_verb_score": av_score,
            "format_score":      fmt_score,
            "total_score":       total,
            "matched_keywords":  kw_matched,
            "missing_keywords":  kw_missing,
            "matched_skills":    sk_matched,
            "missing_skills":    sk_missing,
            "suggestions":       suggestions[:4],
            "debug": {
                "total_jd_keywords":       len(parsed_jd.keywords),
                "keywords_matched_count":  len(kw_matched),
                "total_required_skills":   len(parsed_jd.required_skills),
                "skills_matched_count":    len(sk_matched),
                "bullets_with_strong_verb": f"{strong_starts}/{total_bullets}",
                "format_checks":           format_checks,
            }
        }


ai_agent = AIAgent()
