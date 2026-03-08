"""
CLI Tool — Generate resume from command line without running the server.

Usage:
    python cli.py generate --url "https://jobs.example.com/role"
    python cli.py generate --text "We are looking for a Python engineer..."
    python cli.py score --job-id 5
    python cli.py skills list
    python cli.py skills add --name "Rust" --category "Languages" --proficiency Expert
"""
import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.db.models import init_db, SessionLocal, Skill, JobApplication
from app.config import settings

app_cli = typer.Typer(name="resume-agent", help="AI Resume Agent CLI")
console = Console()


@app_cli.command()
def generate(
    url: str = typer.Option(None, "--url", "-u", help="Job description URL"),
    text: str = typer.Option(None, "--text", "-t", help="Job description text"),
    emphasis: str = typer.Option(None, "--emphasis", "-e", help="Comma-separated keywords to emphasize"),
):
    """Generate a tailored resume for a job description."""
    if not url and not text:
        console.print("[red]Provide --url or --text[/red]")
        raise typer.Exit(1)

    from app.models.schemas import GenerateResumeRequest
    from app.services.scraper import scraper_service, ScraperError, RobotsBlocked
    from app.services.metabase_service import metabase_service
    from app.services.resume_builder import resume_builder
    from app.agents.ai_agent import ai_agent

    init_db()
    db = SessionLocal()

    async def run():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Step 1: Get JD
            jd_text = text
            if url:
                task = progress.add_task("🌐 Scraping job description...", total=None)
                try:
                    jd_text, warning = await scraper_service.scrape(url)
                    if warning:
                        console.print(f"[yellow]{warning}[/yellow]")
                except (ScraperError, RobotsBlocked) as e:
                    console.print(f"[red]{e}[/red]")
                    raise typer.Exit(1)
                progress.update(task, description="✅ JD scraped")

            # Step 2: Parse JD
            task2 = progress.add_task("🤖 AI analyzing job description...", total=None)
            parsed_jd = ai_agent.parse_jd(jd_text)
            progress.update(task2, description=f"✅ JD parsed: {parsed_jd.job_title}")

            # Step 3: Fetch profile
            task3 = progress.add_task("📦 Fetching your profile from metabase...", total=None)
            profile = metabase_service.get_full_profile(db)
            progress.update(task3, description="✅ Profile fetched")

            # Step 4: Tailor
            task4 = progress.add_task("✍️  AI tailoring resume content...", total=None)
            emphasis_list = [e.strip() for e in emphasis.split(",")] if emphasis else None
            tailored = ai_agent.tailor_resume(parsed_jd, profile, emphasis_list)
            progress.update(task4, description="✅ Resume tailored")

            # Step 5: Score
            task5 = progress.add_task("📊 Scoring resume for ATS...", total=None)
            score_data = ai_agent.score_resume(parsed_jd, tailored)
            progress.update(task5, description=f"✅ ATS Score: {score_data.get('total_score', 0):.1f}/100")

            # Step 6: Build DOCX
            task6 = progress.add_task("📝 Generating .docx file...", total=None)
            company_slug = (parsed_jd.company or "company").lower().replace(" ", "_")[:15]
            title_slug = (parsed_jd.job_title or "role").lower().replace(" ", "_")[:15]
            resume_path = resume_builder.build(
                personal=profile["personal"],
                tailored=tailored,
                education=profile.get("education", []),
                filename=f"resume_{title_slug}_{company_slug}.docx",
            )
            progress.update(task6, description="✅ Resume saved")

            return parsed_jd, score_data, resume_path

    parsed_jd, score_data, resume_path = asyncio.run(run())

    # Print results
    console.print()
    console.print(Panel.fit(
        f"[bold green]✅ Resume Generated![/bold green]\n\n"
        f"[bold]Role:[/bold] {parsed_jd.job_title}\n"
        f"[bold]Company:[/bold] {parsed_jd.company or 'N/A'}\n"
        f"[bold]File:[/bold] {resume_path}\n\n"
        f"[bold yellow]ATS Score: {score_data.get('total_score', 0):.1f}/100[/bold yellow]",
        title="Resume AI Agent",
    ))

    # Score breakdown table
    table = Table(title="ATS Score Breakdown", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Weight")
    table.add_row("Keyword Match",   f"{score_data.get('keyword_score', 0):.1f}/100",    "40%")
    table.add_row("Skills Coverage", f"{score_data.get('skills_score', 0):.1f}/100",     "30%")
    table.add_row("Action Verbs",    f"{score_data.get('action_verb_score', 0):.1f}/100", "15%")
    table.add_row("Format Quality",  f"{score_data.get('format_score', 0):.1f}/100",     "15%")
    console.print(table)

    if score_data.get("missing_keywords"):
        console.print(f"\n[yellow]Missing keywords:[/yellow] {', '.join(score_data['missing_keywords'][:10])}")
    if score_data.get("suggestions"):
        console.print("\n[cyan]Suggestions:[/cyan]")
        for s in score_data["suggestions"]:
            console.print(f"  • {s}")

    db.close()


@app_cli.command()
def skills():
    """List all skills in the metabase."""
    init_db()
    db = SessionLocal()
    all_skills = db.query(Skill).all()
    db.close()

    table = Table(title="Your Skills Metabase")
    table.add_column("ID", style="dim")
    table.add_column("Skill", style="cyan bold")
    table.add_column("Category", style="green")
    table.add_column("Proficiency")
    table.add_column("Years")

    for s in all_skills:
        table.add_row(str(s.id), s.name, s.category, s.proficiency, str(s.years_experience))

    console.print(table)


@app_cli.command()
def history():
    """Show previously generated resumes."""
    init_db()
    db = SessionLocal()
    jobs = db.query(JobApplication).order_by(JobApplication.created_at.desc()).limit(10).all()
    db.close()

    if not jobs:
        console.print("[yellow]No resumes generated yet.[/yellow]")
        return

    table = Table(title="Resume History (Last 10)")
    table.add_column("ID", style="dim")
    table.add_column("Role", style="cyan")
    table.add_column("Company", style="green")
    table.add_column("ATS Score", style="yellow bold")
    table.add_column("Created")

    for j in jobs:
        score = f"{j.ats_score:.1f}/100" if j.ats_score else "N/A"
        table.add_row(str(j.id), j.job_title or "N/A", j.company or "N/A",
                      score, str(j.created_at)[:16])
    console.print(table)


if __name__ == "__main__":
    app_cli()
