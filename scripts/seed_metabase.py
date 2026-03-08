#!/usr/bin/env python3
"""
Seed Metabase — Sudhanshu Patil
Run once (or re-run to refresh):
    python scripts/seed_metabase.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models import (
    init_db, SessionLocal, PersonalInfo, Skill, Project,
    ProjectBullet, WorkExperience, ExperienceBullet, Education
)
from rich.console import Console
from rich.panel import Panel

console = Console()


def seed():
    init_db()
    db = SessionLocal()

    try:
        console.print("[yellow]Clearing existing data...[/yellow]")
        for model in [ProjectBullet, ExperienceBullet, Project,
                      WorkExperience, Skill, Education, PersonalInfo]:
            db.query(model).delete()
        db.commit()

        # ── PERSONAL ──────────────────────────────────────────────────────
        personal = PersonalInfo(
            full_name="Sudhanshu Patil",
            email="sudhanshupatil588@gmail.com",
            phone="+91 7248913660",
            location="Nagpur, Maharashtra, India",
            linkedin="https://linkedin.com/in/sudhpatil",
            github="https://github.com/Sudhanshu-Patil",
            portfolio="https://portfolio-831cd.web.app",
            professional_summary=(
                "AI/ML Engineer specializing in Agentic AI systems and LLM infrastructure. "
                "Built production MCP servers handling 1M+ records/query for BFSI clients, "
                "cut PII redaction time by 94% using BERT, and shipped 8,000+ lines of "
                "enterprise-grade AI code at SimpleWorks. Ex-Novartis Data Scientist (PPO). "
                "BITS Pilani ECE + Minor in Computing & Intelligence."
            ),
        )
        db.add(personal)

        # ── SKILLS ────────────────────────────────────────────────────────
        skills_data = [
            dict(name="Agentic AI", category="AI & LLM", proficiency="Expert",
                 years_experience=1.5, keywords=["ai agents","multi-agent","agentic workflows","autonomous agents"]),
            dict(name="LLM Integration", category="AI & LLM", proficiency="Expert",
                 years_experience=1.5, keywords=["llm","openai","claude","gemini","gpt-4o","large language models"]),
            dict(name="MCP (Model Context Protocol)", category="AI & LLM", proficiency="Expert",
                 years_experience=0.7, keywords=["mcp","model context protocol","fastmcp","mcp server","tool use"]),
            dict(name="LangGraph", category="AI & LLM", proficiency="Advanced",
                 years_experience=1.0, keywords=["langgraph","langchain","stateful agents","graph agents"]),
            dict(name="CrewAI", category="AI & LLM", proficiency="Advanced",
                 years_experience=1.0, keywords=["crewai","multi-agent systems"]),
            dict(name="BERT / Transformers", category="AI & LLM", proficiency="Advanced",
                 years_experience=1.0, keywords=["bert","transformers","huggingface","nlp","ner"]),
            dict(name="LangFuse", category="AI & LLM", proficiency="Intermediate",
                 years_experience=0.7, keywords=["langfuse","llm observability","tracing","monitoring"]),
            dict(name="Python", category="Engineering", proficiency="Expert",
                 years_experience=3.0, keywords=["python3","asyncio","scripting","automation"]),
            dict(name="FastAPI", category="Engineering", proficiency="Expert",
                 years_experience=2.0, keywords=["fastapi","rest api","async api","pydantic","uvicorn"]),
            dict(name="Redis", category="Engineering", proficiency="Advanced",
                 years_experience=1.5, keywords=["redis","caching","pub/sub","in-memory"]),
            dict(name="SQL / PostgreSQL", category="Engineering", proficiency="Advanced",
                 years_experience=2.5, keywords=["sql","postgresql","postgres","database"]),
            dict(name="AWS", category="Engineering", proficiency="Intermediate",
                 years_experience=1.0, keywords=["aws","cloud","amazon web services","ec2","s3"]),
            dict(name="R / RShiny", category="Data Science", proficiency="Advanced",
                 years_experience=1.0, keywords=["r","rshiny","ggplot2","tidyverse","sas alternative"]),
            dict(name="Data Visualisation", category="Data Science", proficiency="Advanced",
                 years_experience=2.0, keywords=["plotly","dashboards","data viz","clinical visualisation"]),
            dict(name="ETL / Data Pipelines", category="Data Science", proficiency="Intermediate",
                 years_experience=1.0, keywords=["etl","data pipeline","data engineering","workflow automation"]),
            dict(name="JavaScript / React", category="Frontend", proficiency="Advanced",
                 years_experience=2.0, keywords=["javascript","react","reactjs","frontend","ui/ux"]),
        ]
        for s in skills_data:
            db.add(Skill(**s))

        # ── EXPERIENCE: SimpleWorks ────────────────────────────────────────
        sw = WorkExperience(
            company="SimpleWorks Solutions",
            role="AI Solutions Developer",
            location="Nagpur, Maharashtra (Remote)",
            start_date="Aug 2025",
            end_date=None,
            is_current=True,
            tech_stack=["Python","MCP","FastMCP","FastAPI","LangGraph","CrewAI","BERT","LangFuse","AWS","Redis","Plotly"],
        )
        db.add(sw)
        db.flush()

        for b in [
            dict(bullet="Architected and deployed a cloud-hosted MCP server (FastMCP) from scratch, exposing 15+ tools across Claude, Gemini CLI, and internal apps — enabling unified multi-model AI orchestration for BFSI clients.",
                 keywords=["mcp","fastmcp","multi-model","agentic","bfsi","cloud","orchestration"], impact_score=10.0),
            dict(bullet="Engineered high-throughput CRM integration via MCP, retrieving and analysing 1M+ records per query within seconds using FastAPI async endpoints and Redis caching — replacing entire manual analyst workflows.",
                 keywords=["crm","fastapi","redis","async","scalability","1m records","performance"], impact_score=9.8),
            dict(bullet="Slashed PII redaction latency by 94% (8s → 0.5s) for a banking client by designing a multi-step BERT-powered NLP pipeline — directly reducing compliance processing overhead at scale.",
                 keywords=["bert","pii","nlp","latency","banking","compliance","bfsi"], impact_score=9.8),
            dict(bullet="Shipped 8,000+ lines of production-grade AI code across agentic pipelines, MCP tooling, and chatbot integrations within 7 months.",
                 keywords=["production","agentic","chatbot","code","delivery"], impact_score=9.0),
            dict(bullet="Built an in-house agentic response layer that converts raw JSON-RPC MCP outputs into structured, human-readable insights using LLM post-processing chains.",
                 keywords=["agentic","json-rpc","llm","response generation","mcp"], impact_score=8.8),
            dict(bullet="Accelerated marketing CRM account creation from minutes to a single click by integrating Apollo API into the chatbot, eliminating manual contact enrichment.",
                 keywords=["apollo api","crm","automation","chatbot","marketing automation"], impact_score=8.2),
            dict(bullet="Delivered automated audit logging and conversation-history reporting for the chatbot platform, improving observability and reducing incident debug time.",
                 keywords=["audit logging","reporting","observability","chatbot"], impact_score=7.5),
        ]:
            db.add(ExperienceBullet(experience_id=sw.id, **b))

        # ── EXPERIENCE: Novartis ───────────────────────────────────────────
        nov = WorkExperience(
            company="Novartis",
            role="Associate Data Scientist",
            location="Hyderabad, Telangana",
            start_date="Jan 2025",
            end_date="Jul 2025",
            is_current=False,
            tech_stack=["Python","R","RShiny","VBA","Office Scripts","SQL"],
        )
        db.add(nov)
        db.flush()

        for b in [
            dict(bullet="Awarded Pre-Placement Offer (PPO) — among select interns recognised for high-impact delivery on global clinical data systems at Novartis.",
                 keywords=["ppo","pre-placement offer","recognition","clinical data","global"], impact_score=9.5),
            dict(bullet="Developed an interactive RShiny dashboard as a SAS alternative for the clinical data visualisation team, eliminating dependency on licensed SAS tooling for reporting workflows.",
                 keywords=["rshiny","r","sas alternative","clinical visualisation","dashboard"], impact_score=8.8),
            dict(bullet="Trained and deployed an internal LLM-powered coding assistant for R programmers, reducing query-resolution time across the clinical data team.",
                 keywords=["llm","chatbot","nlp","internal tool","r programming","assistant"], impact_score=8.5),
            dict(bullet="Automated clinical onboarding workflows using Python, Office Scripts, and VBA — eliminating repetitive manual steps across cross-functional data pipelines.",
                 keywords=["automation","python","vba","office scripts","workflow","clinical onboarding"], impact_score=8.2),
            dict(bullet="Contributed to an enterprise-scale ETL evolution project supporting Novartis's next-generation clinical data infrastructure migration.",
                 keywords=["etl","data engineering","pipeline","enterprise","data infrastructure"], impact_score=7.8),
        ]:
            db.add(ExperienceBullet(experience_id=nov.id, **b))

        # ── PROJECTS ──────────────────────────────────────────────────────
        proj1 = Project(
            title="BFSI MCP Server — Multi-Model AI Orchestration",
            description="Production MCP server on AWS enabling Claude, Gemini CLI, and internal apps to query live CRM data, run DB analytics, and render Plotly dashboards via a unified tool-calling interface.",
            short_description="Cloud MCP server: 1M+ record queries, 94% PII latency cut, BFSI production",
            tech_stack=["Python","FastMCP","FastAPI","AWS","Plotly","Claude API","Gemini CLI","Redis","BERT"],
            impact="1M+ records/query in seconds; PII redaction 8s→0.5s (94% faster); live in BFSI production",
            github_url=None,
            start_date="Aug 2025",
            end_date="Present",
            is_featured=True,
        )
        db.add(proj1)
        db.flush()
        for b in [
            dict(bullet="Designed 15+ MCP tools spanning CRM queries, DB analytics, and real-time Plotly chart generation — consumed by Claude and Gemini CLI via JSON-RPC over cloud-hosted FastMCP.",
                 keywords=["mcp","tool use","json-rpc","multi-model","claude","gemini","cloud"]),
            dict(bullet="Achieved sub-second retrieval of 1M+ CRM records by combining FastAPI async endpoints with Redis caching, replacing full analyst workflows end-to-end.",
                 keywords=["fastapi","redis","async","scalability","crm","1m records","performance"]),
            dict(bullet="Reduced PII redaction from 8s to 0.5s (94% faster) via a multi-step BERT NLP pipeline meeting BFSI compliance SLAs at production scale.",
                 keywords=["bert","pii","compliance","bfsi","nlp","latency","production"]),
        ]:
            db.add(ProjectBullet(project_id=proj1.id, **b))

        proj2 = Project(
            title="AI Resume Agent — GPT-4o ATS Optimiser",
            description="End-to-end FastAPI system running a 3-stage GPT-4o pipeline (JD parsing → resume tailoring → ATS scoring) that generates ATS-optimised .docx resumes with a full Jinja2 UI and CLI.",
            short_description="GPT-4o agent auto-tailoring resumes; targets 85%+ ATS scores",
            tech_stack=["Python","FastAPI","GPT-4o","SQLite","SQLAlchemy","python-docx","BeautifulSoup","Jinja2"],
            impact="85%+ ATS scores; supports 10+ job boards; full UI + CLI; production-ready",
            github_url="https://github.com/Sudhanshu-Patil",
            start_date="Feb 2026",
            end_date="Feb 2026",
            is_featured=True,
        )
        db.add(proj2)
        db.flush()
        for b in [
            dict(bullet="Built a 3-stage GPT-4o pipeline (JD analyzer → resume tailor → ATS scorer) achieving 85%+ keyword match on any job description via structured JSON LLM calls.",
                 keywords=["gpt-4o","llm","ats","pipeline","openai","resume","keyword match"]),
            dict(bullet="Engineered ATS-safe DOCX generation with python-docx and a multi-selector web scraper supporting 10+ job boards including Greenhouse, Lever, Indeed, and Naukri.",
                 keywords=["python-docx","web scraping","ats","beautifulsoup","job boards"]),
            dict(bullet="Delivered a full Jinja2 + FastAPI UI (dashboard, generator, metabase editor, history) with zero separate frontend build — pure Python backend serving HTML.",
                 keywords=["fastapi","jinja2","full stack","ui","dashboard","python"]),
        ]:
            db.add(ProjectBullet(project_id=proj2.id, **b))

        # ── EDUCATION ─────────────────────────────────────────────────────
        db.add(Education(
            institution="BITS Pilani, Hyderabad Campus",
            degree="B.E. (Hons.)",
            field="Electronics & Communication Engineering",
            start_year=2021, end_year=2025,
            honors="INSPIRE-SHE Scholar | District Merit | Regional Merit",
            relevant_coursework=["Machine Learning","Data Structures & Algorithms",
                                  "Neural Networks","Database Systems","Computer Networks"],
        ))
        db.add(Education(
            institution="BITS Pilani — Minor Programme",
            degree="Minor",
            field="Computing & Intelligence",
            start_year=2023, end_year=2024,
            relevant_coursework=["Foundations of AI","Statistical Learning",
                                  "NLP","Deep Learning"],
        ))

        db.commit()

        console.print(Panel.fit(
            "[bold green]✅ Seeded — Sudhanshu Patil[/bold green]\n\n"
            "  • 1 personal profile\n"
            f"  • {len(skills_data)} skills\n"
            "  • 2 roles: SimpleWorks (MCP) + Novartis\n"
            "  • 2 projects: BFSI MCP Server + AI Resume Agent\n"
            "  • 2 education: BITS ECE + Minor CI\n\n"
            "[cyan]Run: uvicorn main:app --reload → localhost:8000[/cyan]",
            title="Resume AI Agent",
        ))

    except Exception as e:
        db.rollback()
        console.print(f"[red]Seed failed: {e}[/red]")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    COVER LETTER — Sudhanshu Patil                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Dear Hiring Manager,

I build AI systems that go to production — not demos.

In the past 7 months at SimpleWorks Solutions, I architected a cloud-hosted
MCP server from scratch that connects Claude, Gemini CLI, and internal BFSI
apps to live CRM data — retrieving 1M+ records per query in seconds. I cut a
banking client's PII processing time by 94% (8s → 0.5s) using a custom BERT
pipeline, and shipped 8,000+ lines of enterprise agentic AI code across MCP
tooling, LLM orchestration layers, and chatbot integrations.

Before that, at Novartis (Hyderabad), I earned a Pre-Placement Offer by
delivering an RShiny clinical dashboard, training an internal LLM coding
assistant for the clinical data team, and automating onboarding workflows
that eliminated manual steps across cross-functional pipelines.

I hold a B.E. (Hons.) in ECE from BITS Pilani with a Minor in Computing &
Intelligence — and I've sharpened my fundamentals through 800+ DSA problems.
I work across the full AI stack: LLM pipelines, agentic frameworks (LangGraph,
CrewAI), MCP tooling, FastAPI backends, and cloud deployments.

I'm looking to bring this Agentic AI + LLM engineering depth to a product
company where I can own AI systems from architecture to production. If you're
building something ambitious, I'd love to talk.

Sudhanshu Patil
+91 7248913660 | sudhanshupatil588@gmail.com
linkedin.com/in/sudhpatil | portfolio-831cd.web.app
""")
