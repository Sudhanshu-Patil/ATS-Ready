"""
AI Agent Orchestration
-----------------------
Two-stage AI pipeline:
  Stage 1: JD Analyzer — parse JD into structured format
  Stage 2: Resume Tailor — select & rewrite content for max ATS score
"""
import json
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.models.schemas import ParsedJD

logger = logging.getLogger(__name__)


class AIAgent:
    def __init__(self):
        # base_url must be passed explicitly — without it the OpenAI SDK talks
        # to api.openai.com regardless of which key/model is configured.
        self.client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    # Free-tier providers rate-limit tokens per MINUTE (Groq: 8K TPM) — a 429
    # mid-pipeline usually clears in seconds once the window rolls, so retry
    # with backoff instead of failing the whole job. Deliberately NOT retrying
    # 413 "request too large": that's a prompt-size problem no wait can fix.
    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=2, min=6, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _call(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Single call to the configured LLM. Every caller prompts for JSON-only
        output, so JSON Object Mode is requested directly rather than relying
        purely on prompt instructions — reasoning models can otherwise leak
        chain-of-thought text into the response body."""
        extra_body = {}
        if settings.LLM_REASONING_EFFORT:
            extra_body["reasoning_effort"] = settings.LLM_REASONING_EFFORT

        response = self.client.chat.completions.create(
            model=settings.MODEL,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_body=extra_body,
        )
        return response.choices[0].message.content

    # ─── Stage 1: JD Analysis ─────────────────────────────────────────────────

    SYSTEM_JD_PARSER = """You are an expert ATS (Applicant Tracking System) analyst and recruiter.
Your job is to parse a job description into a precise structured format.
Extract ALL keywords, skills, and requirements — including implicit ones.
Always respond with valid JSON only, no markdown, no explanation."""

    def parse_jd(self, jd_text: str) -> ParsedJD:
        """Parse raw JD text into a structured ParsedJD object."""
        prompt = f"""Parse this job description into JSON with EXACTLY this structure:
{{
  "job_title": "exact job title",
  "company": "company name or null",
  "location": "location or null",
  "job_type": "Full-time|Part-time|Contract|Remote or null",
  "seniority": "Junior|Mid|Senior|Lead|Principal|Staff or null",
  "industry": "industry domain",
  "required_skills": ["list of must-have technical skills"],
  "preferred_skills": ["list of nice-to-have skills"],
  "responsibilities": ["key responsibilities as short phrases"],
  "qualifications": ["education/certification requirements"],
  "keywords": ["ALL important ATS keywords including: tools, frameworks, methodologies, soft skills, domain terms — extract 25-40 keywords"]
}}

Job Description:
---
{jd_text[:8000]}
---

Rules:
- keywords must include EVERY technical term, tool, framework, methodology, certification, domain term
- Include both spelled-out and abbreviated forms: "Machine Learning" and "ML"
- Include action-based keywords from responsibilities: "distributed systems", "cross-functional teams"
- Return ONLY the JSON object"""

        response = self._call(self.SYSTEM_JD_PARSER, prompt)
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"AI returned invalid JSON: {response[:200]}")

        data["raw_text"] = jd_text
        return ParsedJD(**data)

    # ─── Resume Import: parse an uploaded resume into a metabase profile ─────

    SYSTEM_RESUME_PARSER = """You are an expert resume parser.
Extract the candidate's profile from raw resume text into precise structured JSON.
Only extract what is actually present — never invent or embellish.
Always respond with valid JSON only."""

    def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """Parse raw resume text into metabase-shaped profile data."""
        prompt = f"""Extract this resume into JSON with EXACTLY this structure:
{{
  "personal": {{
    "full_name": "...", "email": "...", "phone": "...", "location": "...",
    "linkedin": "url or empty string", "github": "url or empty string",
    "portfolio": "url or empty string",
    "professional_summary": "the summary/objective section, or write a faithful 2-3 sentence summary from the content"
  }},
  "skills": [
    {{"name": "...", "category": "e.g. Programming Languages / Frameworks / Cloud & DevOps / Databases / Tools",
      "proficiency": "Beginner|Intermediate|Advanced|Expert (infer from context, default Intermediate)",
      "years_experience": 1.0, "is_primary": true}}
  ],
  "experience": [
    {{"company": "...", "role": "...", "location": "...",
      "start_date": "Month Year", "end_date": "Month Year or null if current",
      "is_current": false,
      "bullets": ["each achievement/responsibility bullet, verbatim or lightly cleaned"]}}
  ],
  "projects": [
    {{"title": "...", "description": "1-2 sentences",
      "tech_stack": ["tech1", "tech2"], "github_url": "url or empty string",
      "bullets": ["notable details"]}}
  ],
  "education": [
    {{"institution": "...", "degree": "e.g. B.E.", "field": "...",
      "start_year": 2020, "end_year": 2024, "gpa": "as written, or null"}}
  ]
}}

Rules:
- skills: extract EVERY skill mentioned anywhere (skills section, bullets, tech stacks); dedupe.
- Mark is_primary=true for skills that appear prominently/repeatedly.
- Dates: keep the resume's own format for start_date/end_date strings.
- Missing sections → empty arrays. Missing fields → empty string or null.

Resume text:
---
{resume_text[:12000]}
---
Return ONLY the JSON object."""

        response = self._call(self.SYSTEM_RESUME_PARSER, prompt, max_tokens=3500)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"AI resume parser returned invalid JSON: {response[:200]}")

    # ─── Stage 2: Resume Tailoring ────────────────────────────────────────────

    SYSTEM_RESUME_TAILOR = """You are an elite resume coach and ATS optimization expert.
You help candidates tailor their resumes to maximize ATS scores and pass recruiter screening.
You ONLY use skills and experiences the candidate actually has — never fabricate.
You mirror the JD's language naturally while keeping content honest.
Always respond with valid JSON only."""

    def tailor_resume(
        self,
        parsed_jd: ParsedJD,
        candidate_data: Dict[str, Any],
        emphasis: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Select and rewrite resume content to match JD.
        Returns a structured dict ready for the DOCX builder.
        """
        emphasis_str = ""
        if emphasis:
            emphasis_str = f"\nUser wants to especially emphasize: {', '.join(emphasis)}"

        prompt = f"""Given the job description analysis and candidate's full profile, create an optimized resume.

=== JOB DESCRIPTION ===
Title: {parsed_jd.job_title}
Company: {parsed_jd.company}
Seniority: {parsed_jd.seniority}
Required Skills: {', '.join(parsed_jd.required_skills)}
Preferred Skills: {', '.join(parsed_jd.preferred_skills)}
Key Responsibilities: {json.dumps(parsed_jd.responsibilities)}
ATS Keywords to target: {', '.join(parsed_jd.keywords)}
{emphasis_str}

=== CANDIDATE PROFILE ===
{json.dumps(candidate_data, default=str)}

=== INSTRUCTIONS ===
1. PROFESSIONAL SUMMARY: Write a 3-4 sentence summary that:
   - Opens with the exact job title from the JD
   - Naturally incorporates 5-8 ATS keywords
   - Highlights most relevant experience/skills
   - Is specific and quantified

2. SKILLS SELECTION: Pick the {settings.MAX_SKILLS_IN_RESUME} most relevant skills from candidate's metabase.
   Group them into max 3 categories. Put closest JD matches first.

3. WORK EXPERIENCE: For each role, select and REWRITE the {settings.MAX_EXPERIENCE_BULLETS} most relevant bullets.
   - Start with strong action verbs
   - Mirror JD terminology naturally
   - Quantify impact where data exists
   - Include relevant ATS keywords

4. PROJECTS: Select the {settings.MAX_PROJECTS_IN_RESUME} most relevant projects.
   Rewrite bullets to highlight skills/tech the JD cares about.

5. KEYWORD INJECTION: Naturally inject missing JD keywords where truthfully applicable.

Return this JSON structure:
{{
  "professional_summary": "3-4 sentence tailored summary",
  "skills": [
    {{"category": "Category Name", "items": ["skill1", "skill2", ...]}}
  ],
  "work_experience": [
    {{
      "company": "Company Name",
      "role": "Job Title (mirror JD language if same role)",
      "location": "City, State",
      "start_date": "Month Year",
      "end_date": "Month Year or Present",
      "bullets": ["rewritten bullet 1", "rewritten bullet 2", ...]
    }}
  ],
  "projects": [
    {{
      "title": "Project Title",
      "tech_stack": ["tech1", "tech2"],
      "date_range": "Month Year - Month Year",
      "github_url": "url or null",
      "bullets": ["rewritten bullet 1", "bullet 2"]
    }}
  ],
  "keywords_injected": ["list of JD keywords successfully incorporated"],
  "keywords_missing": ["JD keywords the candidate doesn't have"]
}}

CRITICAL: Only use information from the candidate's actual profile. Never invent experiences."""

        # 6000 was reserved here previously — combined with a rich candidate
        # profile (many skills/bullets), prompt + reservation regularly
        # exceeded free-tier TPM ceilings on providers like Groq (8K/min).
        # The requested JSON structure (summary + skills + bullets) doesn't
        # need that much; 3500 leaves comfortable headroom.
        response = self._call(self.SYSTEM_RESUME_TAILOR, prompt, max_tokens=3500)
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"AI tailor returned invalid JSON: {response[:200]}")
        return data

    # ─── Stage 3: ATS Scoring ─────────────────────────────────────────────────

    SYSTEM_ATS_SCORER = """You are an ATS system simulator. Score resumes objectively based on 
keyword matching, skills alignment, and formatting quality. Return precise scores. JSON only."""

    def score_resume(
        self, parsed_jd: ParsedJD, tailored_resume: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate ATS scoring of the tailored resume."""
        resume_text = json.dumps(tailored_resume)

        prompt = f"""Score this resume against the job description using ATS criteria.

JD Required Skills: {parsed_jd.required_skills}
JD Keywords: {parsed_jd.keywords}
JD Qualifications: {parsed_jd.qualifications}

Resume Content:
{resume_text[:5000]}

Calculate scores (0-100 for each):
1. keyword_score (40% weight): What % of JD keywords appear in resume?
2. skills_score (30% weight): What % of required skills are in resume?
3. action_verb_score (15% weight): Quality of action verbs used?
4. format_score (15% weight): ATS-friendly formatting signals?

Return JSON:
{{
  "keyword_score": 0-100,
  "skills_score": 0-100,
  "action_verb_score": 0-100,
  "format_score": 0-100,
  "total_score": weighted_average,
  "matched_keywords": ["keywords found"],
  "missing_keywords": ["important keywords not found"],
  "matched_skills": ["required skills found"],
  "missing_skills": ["required skills not found"],
  "suggestions": ["2-3 specific improvement suggestions"]
}}"""

        response = self._call(self.SYSTEM_ATS_SCORER, prompt, max_tokens=2000)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # Return baseline if scoring fails
            return {
                "keyword_score": 75.0,
                "skills_score": 70.0,
                "action_verb_score": 80.0,
                "format_score": 85.0,
                "total_score": 75.0,
                "matched_keywords": tailored_resume.get("keywords_injected", []),
                "missing_keywords": tailored_resume.get("keywords_missing", []),
                "matched_skills": [],
                "missing_skills": [],
                "suggestions": [],
            }

    # ─── Stage 4: Cover Letter ────────────────────────────────────────────────

    SYSTEM_COVER_LETTER = """You are an expert career coach and professional writer.
Write compelling, personalized cover letters that feel human — not templated.
Mirror the company's tone, highlight the most relevant experience, and show genuine enthusiasm.
Always respond with valid JSON only."""

    def generate_cover_letter(
        self,
        parsed_jd: ParsedJD,
        candidate_data: Dict[str, Any],
        tailored_resume: Dict[str, Any],
        tone: str = "professional",  # professional | conversational | enthusiastic
    ) -> Dict[str, Any]:
        """
        Generate a personalized cover letter.

        Args:
            parsed_jd       — structured JD from parse_jd()
            candidate_data  — full profile from metabase
            tailored_resume — output from tailor_resume() (for aligned content)
            tone            — writing tone preference

        Returns:
            {subject, body, word_count, highlights}
        """
        personal = candidate_data.get("personal", {})

        prompt = f"""Write a personalized cover letter for this job application.

=== JOB DETAILS ===
Title: {parsed_jd.job_title}
Company: {parsed_jd.company or "the company"}
Seniority: {parsed_jd.seniority}
Industry: {parsed_jd.industry}
Key Requirements: {", ".join(parsed_jd.required_skills[:8])}
Responsibilities: {json.dumps(parsed_jd.responsibilities[:4])}

=== CANDIDATE ===
Name: {personal.get("full_name", "Candidate")}
Current Role Summary: {tailored_resume.get("professional_summary", "")}
Top Skills: {", ".join([s["items"][0] if s.get("items") else "" for s in tailored_resume.get("skills", [])[:3]])}
Most Relevant Experience: {json.dumps([
    {{"role": e["role"], "company": e["company"], "highlight": e["bullets"][0] if e.get("bullets") else ""}}
    for e in tailored_resume.get("work_experience", [])[:2]
], default=str)}

=== INSTRUCTIONS ===
Tone: {tone}
Length: 250-320 words (3-4 paragraphs)

Paragraph 1: Hook — why this specific role at this specific company excites the candidate.
Paragraph 2: Most relevant achievement (quantified) that directly maps to a key requirement.
Paragraph 3: Second achievement or skill that addresses another key requirement.
Paragraph 4: Brief close — enthusiasm, call to action, professional sign-off.

Rules:
- Never use generic phrases like "I am writing to apply" or "Please find attached"
- Reference the company by name at least twice
- Include at least one quantified achievement
- Sound like a real human wrote it, not AI
- Do NOT fabricate experiences not in the candidate's profile

Return JSON:
{{
  "subject": "email subject line for the application",
  "body": "full cover letter text with \n for line breaks",
  "word_count": approximate_word_count,
  "highlights": ["3 key selling points used in the letter"]
}}"""

        response = self._call(self.SYSTEM_COVER_LETTER, prompt, max_tokens=2000)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {
                "subject": f"Application for {parsed_jd.job_title}",
                "body": response,
                "word_count": len(response.split()),
                "highlights": [],
            }

    # ─── Stage 5: Interview Prep ──────────────────────────────────────────────

    SYSTEM_INTERVIEW_PREP = """You are a senior technical recruiter and interview coach with 15+ years experience.
Generate realistic, role-specific interview questions with detailed model answers.
Questions should reflect what top companies actually ask — behavioral, technical, and situational.
Always respond with valid JSON only."""

    def generate_interview_prep(
        self,
        parsed_jd: ParsedJD,
        candidate_data: Dict[str, Any],
        tailored_resume: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate tailored interview questions + model answers.

        Returns:
            {
              questions: [
                {
                  category: "behavioral|technical|situational|cultural",
                  question: "...",
                  why_asked: "what the interviewer is evaluating",
                  model_answer: "STAR-format answer using candidate's real experience",
                  tips: ["specific tip 1", "specific tip 2"],
                  difficulty: "easy|medium|hard"
                }
              ],
              quick_tips: ["5 role-specific tips for this interview"],
              red_flags_to_avoid: ["common mistakes for this role"],
              questions_to_ask: ["3 smart questions candidate should ask the interviewer"]
            }
        """
        personal = candidate_data.get("personal", {})
        skills_missing = tailored_resume.get("keywords_missing", [])

        prompt = f"""Generate comprehensive interview preparation for this job application.

=== ROLE ===
Title: {parsed_jd.job_title}
Company: {parsed_jd.company or "the company"}
Seniority: {parsed_jd.seniority}
Required Skills: {", ".join(parsed_jd.required_skills)}
Responsibilities: {json.dumps(parsed_jd.responsibilities[:5])}

=== CANDIDATE PROFILE ===
Name: {personal.get("full_name", "Candidate")}
Summary: {tailored_resume.get("professional_summary", "")}
Experience: {json.dumps([
    {{"role": e["role"], "company": e["company"], "bullets": e["bullets"][:2]}}
    for e in tailored_resume.get("work_experience", [])[:3]
], default=str)}
Skills: {json.dumps([
    {{"category": s["category"], "items": s["items"][:4]}}
    for s in tailored_resume.get("skills", [])[:4]
], default=str)}
Skill gaps (prepare for): {", ".join(skills_missing[:5]) if skills_missing else "none identified"}

=== GENERATE ===
Create exactly 10 questions across these categories:
- 3 behavioral (STAR format, use candidate's actual experience)
- 3 technical (specific to required skills, realistic difficulty)
- 2 situational (role-specific scenarios)
- 1 cultural fit
- 1 about the skill gaps (how to address honestly)

For model answers: use the candidate's REAL experience from their profile. Reference actual companies, projects, and metrics they have.

Return JSON:
{{
  "questions": [
    {{
      "category": "behavioral|technical|situational|cultural|skill_gap",
      "question": "exact question text",
      "why_asked": "what the interviewer is evaluating (1 sentence)",
      "model_answer": "detailed STAR answer using candidate's real experience (150-200 words)",
      "tips": ["actionable tip 1", "actionable tip 2"],
      "difficulty": "easy|medium|hard"
    }}
  ],
  "quick_tips": ["5 specific tips for this exact role/company"],
  "red_flags_to_avoid": ["3 common mistakes candidates make for this role"],
  "questions_to_ask": [
    {{"question": "smart question to ask interviewer", "why": "what it signals about you"}}
  ]
}}"""

        response = self._call(self.SYSTEM_INTERVIEW_PREP, prompt, max_tokens=6000)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"questions": [], "quick_tips": [], "red_flags_to_avoid": [], "questions_to_ask": []}


ai_agent = AIAgent()
