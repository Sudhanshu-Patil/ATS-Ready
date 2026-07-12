# 🤖 AI Resume Agent

Automatically tailors your resume to any job description using GPT-4, maximizing ATS scores. Paste a JD URL or text — get an optimized `.docx` in seconds.

---

## 🏗️ Project Structure

```
resume_agent/
├── app/
│   ├── agents/
│   │   └── ai_agent.py          # 3-stage AI pipeline (parse → tailor → score)
│   ├── api/
│   │   └── routes.py            # FastAPI endpoints
│   ├── db/
│   │   └── models.py            # SQLAlchemy ORM (SQLite metabase)
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response schemas
│   ├── services/
│   │   ├── metabase_service.py  # Fetches candidate profile from DB
│   │   ├── resume_builder.py    # Generates ATS-optimized .docx
│   │   └── scraper.py           # JD URL scraper (robots.txt aware)
|   ├── static/
│   │   ├── css
│   │   │   └──app.css    
│   │   ├── js
│   │   │   └──app.js   
│   └── config.py                # Settings from .env
├── scripts/
│   └── seed_metabase.py         # One-time: populate YOUR data
├── outputs/                     # Generated .docx files land here
├── main.py                      # FastAPI app entry point
├── cli.py                       # CLI tool (no server needed)
├── requirements.txt
├── .env.example
└── .env                         # Your secrets (gitignored)
└── .gitignore
└── README.md
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your LLM_API_KEY
```

### 3. Seed Your Personal Data

```bash
# Edit scripts/seed_metabase.py with YOUR actual info:
#   - Personal info (name, email, phone, LinkedIn, GitHub)
#   - Skills (name, category, proficiency, years)
#   - Work experience + bullet points
#   - Projects + bullet points
#   - Education

python scripts/seed_metabase.py
```

### 4. Run

**Option A — API Server:**
```bash
uvicorn main:app --reload
# Docs at http://localhost:8000/docs
```

**Option B — CLI (no server needed):**
```bash
python cli.py generate --url "https://jobs.lever.co/company/role-id"
python cli.py generate --text "We're looking for a Python engineer..."
python cli.py generate --url "https://..." --emphasis "FastAPI, AWS, distributed systems"
python cli.py skills      # list all skills in metabase
python cli.py history     # show past generated resumes
```

---

## 🔄 AI Pipeline

```
JD URL / Text
     │
     ▼
[1] Scraper          → fetches URL, checks robots.txt, extracts text
     │
     ▼
[2] JD Analyzer      → GPT-4 parses: title, skills, keywords (25-40), seniority
     │
     ▼
[3] Metabase Query   → pulls your skills, experience, projects from SQLite
     │
     ▼
[4] Resume Tailor    → GPT-4 selects + rewrites content to mirror JD language
     │
     ▼
[5] ATS Scorer       → simulates ATS: keyword match (40%) + skills (30%) + verbs (15%) + format (15%)
     │
     ▼
[6] DOCX Builder     → ATS-friendly .docx: single column, Calibri, no tables/graphics
     │
     ▼
resume_role_company.docx  +  ATS score report
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate-resume` | Main: generate tailored resume |
| `GET`  | `/api/download/{job_id}` | Download the .docx file |
| `GET`  | `/api/ats-score/{job_id}` | Get detailed ATS breakdown |
| `GET`  | `/api/jobs` | List all past generated resumes |
| `GET`  | `/api/metabase/personal` | Get personal info |
| `POST` | `/api/metabase/personal` | Update personal info |
| `GET`  | `/api/metabase/skills` | List all skills |
| `POST` | `/api/metabase/skills` | Add a skill |
| `DELETE` | `/api/metabase/skills/{id}` | Delete a skill |
| `GET`  | `/api/metabase/projects` | List projects |
| `POST` | `/api/metabase/projects` | Add a project |
| `GET`  | `/api/metabase/experience` | List work experience |
| `POST` | `/api/metabase/experience` | Add work experience |

### Example Request

```bash
curl -X POST http://localhost:8000/api/generate-resume \
  -H "Content-Type: application/json" \
  -d '{
    "jd_url": "https://boards.greenhouse.io/company/jobs/12345",
    "emphasis": ["FastAPI", "distributed systems", "AWS"]
  }'
```

Or with raw text:
```bash
curl -X POST http://localhost:8000/api/generate-resume \
  -H "Content-Type: application/json" \
  -d '{
    "jd_text": "We are looking for a Senior Python Engineer...(full JD text)"
  }'
```

---

## 🌐 Supported Job Boards (URL scraping)

| Site | Scraping Support |
|------|-----------------|
| Greenhouse.io | ✅ Full |
| Lever.co | ✅ Full |
| Indeed | ✅ Full |
| Naukri | ✅ Full |
| Wellfound (AngelList) | ✅ Full |
| Workday | ⚠️ Partial (JS-heavy) |
| LinkedIn | ⚠️ Partial (JS-heavy) |
| Glassdoor | ⚠️ Partial (JS-heavy) |
| Any other URL | 🔄 Heuristic fallback |

For JS-heavy sites, paste the JD text directly for best results.

---

## 📊 ATS Scoring

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Keyword Match | 40% | % of JD keywords found in resume |
| Skills Coverage | 30% | % of required skills present |
| Action Verbs | 15% | Quality of bullet point action verbs |
| Format Quality | 15% | ATS-parseable formatting signals |

---

## 💡 Tips for Maximum ATS Score

1. **Keep your metabase rich** — more bullet points = more for AI to select from
2. **Add keyword aliases** — e.g. skill "Kubernetes" with keywords `["k8s", "helm", "kubectl"]`
3. **Quantify everything** — bullets with numbers score higher
4. **Use `--emphasis`** — tell the AI which skills to prioritize for a specific role
5. **Use `gpt-4o`** over `gpt-4o-mini` for best tailoring quality

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | required | API key for your LLM provider |
| `MODEL` | `openai/gpt-oss-120b` | Model ID (any OpenAI-compatible provider) |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | LLM provider's OpenAI-compatible endpoint |
| `DATABASE_URL` | `sqlite:///./metabase.db` | Database connection string |
| `MAX_SKILLS_IN_RESUME` | `12` | Max skills shown in resume |
| `MAX_PROJECTS_IN_RESUME` | `4` | Max projects shown |
| `MAX_EXPERIENCE_BULLETS` | `5` | Max bullets per work role |
| `RESPECT_ROBOTS_TXT` | `true` | Honor robots.txt |
| `SCRAPE_TIMEOUT` | `15` | URL fetch timeout in seconds |
