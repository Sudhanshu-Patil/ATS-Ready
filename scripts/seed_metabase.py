"""
scripts/seed_metabase.py
─────────────────────────
One-time script: populates the metabase with YOUR personal data.

Edit the data sections below with your actual information, then run:

  # With docker-compose:
  docker compose exec api python scripts/seed_metabase.py

  # Or locally (with DATABASE_URL set):
  python scripts/seed_metabase.py

The script is IDEMPOTENT — safe to run multiple times.
Existing skills/projects/experience are NOT duplicated (checked by name/company).

IMPORTANT: Replace all placeholder data below with your real information.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path so we can import app.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal, init_db
from app.db.models import (
    Education, ExperienceBullet, PersonalInfo, Project,
    ProjectBullet, Skill, User, WorkExperience,
)


# ─────────────────────────────────────────────────────────────────────────────
# ✏️  EDIT THIS SECTION WITH YOUR REAL DATA
# ─────────────────────────────────────────────────────────────────────────────

PERSONAL = {
    "full_name":            "Sudhanshu Patil",
    "email":                "sudhanshupatil588@gmail.com",
    "phone":                "+91-7248913660",
    "location":             "Nagpur, Maharashtra - 440022",
    "linkedin":             "",  # not extractable from the source PDF's text layer — fill in manually
    "github":               "",  # same — fill in manually
    "portfolio":            "",
    "professional_summary": (
        "AI Engineer with 1+ year of experience specializing in Python, Agentic AI and "
        "Retrieval-Augmented Generation (RAG). Proven track record building and deploying "
        "production-grade automation tools and LLM-driven applications for enterprise clients. "
        "Skilled at translating emerging technologies into user-centric solutions across cloud "
        "platforms to streamline enterprise operations and data aggregation."
    ),
}

SKILLS = [
    # (name, category, proficiency, years, keywords, is_primary)
    ("Python",             "Engineering & Automation", "Advanced",     1.5, ["py", "python3"],                          True),
    ("FastAPI",            "Engineering & Automation", "Advanced",     1.5, ["fast-api", "async python"],               True),
    ("SQL",                "Engineering & Automation", "Intermediate", 1.5, ["structured query language"],              False),
    ("MySQL",               "Engineering & Automation", "Intermediate", 1.0, ["mysql db"],                               False),
    ("PostgreSQL",         "Engineering & Automation", "Intermediate", 1.0, ["postgres", "psql"],                       True),
    ("Redis",              "Engineering & Automation", "Intermediate", 1.0, ["redis cache", "redis/arq"],               True),
    ("ChromaDB",           "Engineering & Automation", "Intermediate", 1.0, ["vector store", "chroma"],                 True),
    ("REST APIs",          "Engineering & Automation", "Advanced",     1.5, ["restful", "rest", "http apis"],           True),
    ("VBA",                "Engineering & Automation", "Intermediate", 0.5, ["visual basic for applications"],          False),

    ("RAG",                    "AI & Machine Learning", "Advanced",     1.5, ["retrieval-augmented generation", "agentic rag"], True),
    ("Agentic AI",              "AI & Machine Learning", "Advanced",     1.0, ["ai agents", "agentic workflows"],        True),
    ("LLMs",                   "AI & Machine Learning", "Advanced",     1.5, ["large language models", "llm apis", "llm pipelines"], True),
    ("BERT",                   "AI & Machine Learning", "Intermediate", 1.0, ["bert-based models", "transformers"],     True),
    ("Applied NLP",            "AI & Machine Learning", "Intermediate", 1.0, ["natural language processing", "nlp"],    True),
    ("Vector Databases",       "AI & Machine Learning", "Advanced",     1.0, ["vector db", "embeddings", "similarity search"], True),
    ("LangChain",              "AI & Machine Learning", "Advanced",     1.0, ["langchain framework"],                   True),
    ("LlamaIndex",             "AI & Machine Learning", "Advanced",     1.0, ["llama index"],                           True),
    ("CrewAI",                 "AI & Machine Learning", "Intermediate", 0.5, ["crew ai", "multi-agent"],                False),
    ("PyTorch",                "AI & Machine Learning", "Intermediate", 1.0, ["torch"],                                 False),
    ("TensorFlow",             "AI & Machine Learning", "Intermediate", 1.0, ["tf"],                                    False),
    ("Keras",                  "AI & Machine Learning", "Intermediate", 1.0, [],                                        False),
    ("NumPy",                  "AI & Machine Learning", "Intermediate", 1.5, ["numerical python"],                      False),
    ("Pandas",                 "AI & Machine Learning", "Intermediate", 1.5, ["dataframes"],                            False),
    ("CNNs",                   "AI & Machine Learning", "Intermediate", 0.5, ["convolutional neural networks"],         False),
    ("Reinforcement Learning", "AI & Machine Learning", "Intermediate", 0.5, ["rl"],                                    False),
    ("Hugging Face",           "AI & Machine Learning", "Intermediate", 1.0, ["huggingface", "transformers hub"],       False),
    ("MCP",                    "AI & Machine Learning", "Advanced",     0.5, ["model context protocol", "mcp servers"], True),

    ("AWS",             "Cloud & Platforms", "Intermediate", 1.0, ["amazon web services", "ec2", "aws ec2"], True),
    ("Google Cloud Platform", "Cloud & Platforms", "Intermediate", 1.0, ["gcp"],                             True),
    ("Docker",          "Cloud & Platforms", "Advanced",     1.0, ["containerization", "containers"],        True),
    ("CI/CD",           "Cloud & Platforms", "Intermediate", 1.0, ["continuous integration", "continuous deployment"], True),
    ("Git",             "Cloud & Platforms", "Advanced",     2.0, ["github", "version control"],             True),
    ("Linux",           "Cloud & Platforms", "Advanced",     2.0, ["ubuntu", "bash", "shell scripting"],     True),
    ("Nginx",           "Cloud & Platforms", "Intermediate", 0.5, ["reverse proxy", "web server"],           False),
    ("LangFuse",        "Cloud & Platforms", "Intermediate", 0.5, ["llm tracing", "observability"],          True),
    ("Ollama",          "Cloud & Platforms", "Intermediate", 0.5, ["local llm inference"],                   False),
    ("VLLM",            "Cloud & Platforms", "Intermediate", 0.5, ["vllm inference server"],                 False),

    ("Enterprise BFSI Solutions",       "Applied Domains", "Advanced",     1.0, ["banking", "financial services", "bfsi"], True),
    ("Data Aggregation",                "Applied Domains", "Advanced",     1.0, ["data pipelines", "etl"],               True),
    ("Human-in-the-Loop (HITL)",        "Applied Domains", "Intermediate", 0.5, ["hitl systems"],                        False),
    ("PII Redaction & Guardrails",      "Applied Domains", "Intermediate", 1.0, ["pii redaction", "guardrails", "data privacy"], True),
]

EXPERIENCE = [
    {
        "company":    "SimpleWorks",
        "role":       "AI Solutions Developer",
        "location":   "Nagpur, India",
        "start_date": "Aug 2025",
        "end_date":   None,
        "is_current": True,
        "tech_stack": ["Python", "FastAPI", "MCP", "RAG", "LlamaIndex", "BERT", "Vector Databases", "LangFuse"],
        "bullets": [
            ("Architect high-performance MCP servers across cloud platforms to manage sub-second retrieval across 1M+ records via FastAPI async endpoints and vector databases.", ["MCP", "FastAPI", "vector databases", "cloud", "async"], 9.0),
            ("Design and implement an Agentic RAG framework featuring intent recognition, dynamic library switching, and BERT-based guardrails to optimize data analysis for enterprise banking operations.", ["Agentic RAG", "BERT", "guardrails", "BFSI", "enterprise"], 9.3),
            ("Deploy critical infrastructure upgrades and manage LlamaIndex integration to support advanced LLM APIs, maintaining zero downtime across all live production environments.", ["LlamaIndex", "LLM APIs", "production", "zero downtime"], 8.5),
            ("Translate complex stakeholder requirements into an MVP architecture for an internal AI platform, incorporating multi-DB connectors, LangFuse-based tracing, and robust audit logging.", ["MVP architecture", "LangFuse", "multi-DB", "audit logging"], 8.2),
        ],
    },
    {
        "company":    "Novartis",
        "role":       "Associate Data Scientist Intern",
        "location":   "Hyderabad, India",
        "start_date": "Jan 2025",
        "end_date":   "Jul 2025",
        "is_current": False,
        "tech_stack": ["Python", "VBA", "RShiny", "LLM"],
        "bullets": [
            ("Developed an interactive RShiny dashboard for automated clinical data visualization and aggregation, modernizing reporting for non-technical stakeholders.", ["RShiny", "dashboard", "data visualization", "clinical data"], 8.0),
            ("Trained and implemented an LLM-powered coding assistant and automated clinical onboarding workflows using Python and VBA, cutting manual turnaround time by over 120% for 60+ Data Managers.", ["LLM", "Python", "VBA", "automation", "clinical onboarding"], 8.7),
        ],
    },
]

PROJECTS = [
    {
        "title":       "Smart Resume — AI Resume Tailoring Platform",
        "description": "Built an async FastAPI platform that parses job descriptions and generates ATS-optimized .docx resumes via LLM pipelines, with Redis/ARQ workers, PostgreSQL/SQLAlchemy models, and weighted ATS scoring.",
        "short_description": "Async FastAPI platform generating ATS-optimized resumes via LLM pipelines.",
        "tech_stack":  ["Python", "FastAPI", "Gemini", "OpenAI", "PostgreSQL", "Redis", "ARQ", "Docker"],
        "impact":      "",
        "github_url":  "",
        "start_date":  "",
        "end_date":    "",
        "is_featured": True,
        "bullets": [],
    },
    {
        "title":       "Git-Msg — AI Commit Message Generator",
        "description": "Built and published a VS Code extension analysing staged diffs to generate Conventional Commit messages, live on the VS Code Marketplace with support for 5+ LLM providers.",
        "short_description": "VS Code extension generating Conventional Commit messages from staged diffs.",
        "tech_stack":  ["VS Code Extension API", "LLM Providers", "Conventional Commits"],
        "impact":      "Published and live on the VS Code Marketplace with support for 5+ LLM providers.",
        "github_url":  "",
        "start_date":  "",
        "end_date":    "",
        "is_featured": True,
        "bullets": [],
    },
]

EDUCATION = [
    {
        "institution":         "BITS Pilani, Hyderabad Campus",
        "degree":              "B.E. (Hons.)",
        "field":               "Electronics & Communication Engineering",
        "start_year":          2021,
        "end_year":            2025,
        "gpa":                 None,
        "honors":              None,
        "relevant_coursework": [],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Seed logic
# ─────────────────────────────────────────────────────────────────────────────

async def seed(db: AsyncSession) -> None:
    # ── Get or create the dev user ────────────────────────────────────────────
    result = await db.execute(select(User).where(User.email == PERSONAL["email"]))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            email=PERSONAL["email"],
            full_name=PERSONAL["full_name"],
            is_active=True,
            is_verified=True,
            plan="pro",
        )
        db.add(user)
        await db.flush()
        print(f"✓ Created user id={user.id}")
    else:
        print(f"✓ Using existing user id={user.id}")

    # ── Personal Info ─────────────────────────────────────────────────────────
    result = await db.execute(
        select(PersonalInfo).where(PersonalInfo.user_id == user.id)
    )
    info = result.scalar_one_or_none()
    if not info:
        info = PersonalInfo(user_id=user.id, **PERSONAL)
        db.add(info)
        print("✓ Personal info created")
    else:
        for k, v in PERSONAL.items():
            setattr(info, k, v)
        print("✓ Personal info updated")

    # ── Skills ────────────────────────────────────────────────────────────────
    skill_count = 0
    for name, category, proficiency, years, keywords, is_primary in SKILLS:
        result = await db.execute(
            select(Skill).where(Skill.user_id == user.id, Skill.name == name)
        )
        if not result.scalar_one_or_none():
            db.add(Skill(
                user_id=user.id, name=name, category=category,
                proficiency=proficiency, years_experience=years,
                keywords=keywords, is_primary=is_primary,
            ))
            skill_count += 1
    print(f"✓ Added {skill_count} new skills")

    # ── Work Experience ───────────────────────────────────────────────────────
    exp_count = 0
    for exp_data in EXPERIENCE:
        result = await db.execute(
            select(WorkExperience).where(
                WorkExperience.user_id == user.id,
                WorkExperience.company == exp_data["company"],
                WorkExperience.role == exp_data["role"],
            )
        )
        if result.scalar_one_or_none():
            continue
        bullets = exp_data.pop("bullets")
        exp = WorkExperience(user_id=user.id, **exp_data)
        db.add(exp)
        await db.flush()
        for text, keywords, impact in bullets:
            db.add(ExperienceBullet(
                experience_id=exp.id, bullet=text,
                keywords=keywords, impact_score=impact,
            ))
        exp_count += 1
        exp_data["bullets"] = bullets  # restore for idempotent runs
    print(f"✓ Added {exp_count} new work experience roles")

    # ── Projects ──────────────────────────────────────────────────────────────
    proj_count = 0
    for proj_data in PROJECTS:
        result = await db.execute(
            select(Project).where(
                Project.user_id == user.id,
                Project.title == proj_data["title"],
            )
        )
        if result.scalar_one_or_none():
            continue
        bullets = proj_data.pop("bullets")
        proj = Project(user_id=user.id, **proj_data)
        db.add(proj)
        await db.flush()
        for text, keywords in bullets:
            db.add(ProjectBullet(project_id=proj.id, bullet=text, keywords=keywords))
        proj_count += 1
        proj_data["bullets"] = bullets
    print(f"✓ Added {proj_count} new projects")

    # ── Education ─────────────────────────────────────────────────────────────
    edu_count = 0
    for edu_data in EDUCATION:
        result = await db.execute(
            select(Education).where(
                Education.user_id == user.id,
                Education.institution == edu_data["institution"],
            )
        )
        if not result.scalar_one_or_none():
            db.add(Education(user_id=user.id, **edu_data))
            edu_count += 1
    print(f"✓ Added {edu_count} new education records")

    await db.commit()
    print("\n🎉 Seed complete! Your metabase is ready.")


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
