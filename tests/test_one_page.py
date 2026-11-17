"""Every generated resume is ONE page, however much content the profile has."""
from io import BytesIO

from docx import Document
from pypdf import PdfReader

from app.config import settings
from app.services.documents import fit_resume, resume_pdf
from app.services.resume_builder import ResumeBuilder

BULLET = "Designed and shipped a distributed service handling millions of requests per day with strict latency goals"


def _resume(roles: int, bullets: int, projects: int, project_bullets: int):
    return {
        "personal": {"full_name": "Asha Verma", "email": "asha@example.com", "phone": "+91 98765 43210",
                     "location": "Pune, India", "linkedin": "linkedin.com/in/asha", "github": "github.com/asha"},
        "tailored": {
            "professional_summary": "Backend engineer with deep experience in Python and distributed systems. "
                                    "Led teams. Mentored juniors. Shipped many products.",
            "skills": [{"category": "Languages", "items": ["Python", "SQL", "Go", "TypeScript", "Bash"]},
                       {"category": "Backend", "items": ["FastAPI", "Django", "PostgreSQL", "Redis", "Kafka"]}],
            "work_experience": [{"role": f"Engineer {i}", "company": f"Company {i}", "start_date": "2020",
                                 "end_date": "Present", "location": "Pune",
                                 "bullets": [f"{BULLET} (#{n})" for n in range(bullets)]} for i in range(roles)],
            "projects": [{"title": f"Project {i}", "tech_stack": ["Python", "React"], "date_range": "2023",
                          "bullets": [f"{BULLET} (#{n})" for n in range(project_bullets)]}
                         for i in range(projects)],
        },
        "education": [{"degree": "B.E.", "field": "Computer Engineering", "institution": "SPPU", "end_year": "2018"}],
    }


def _pages(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages)


def test_a_short_resume_is_left_alone():
    fitted = fit_resume(_resume(roles=2, bullets=3, projects=1, project_bullets=2))
    assert fitted["scale"] == 1.0 and fitted["trim_level"] == 0
    assert len(fitted["tailored"]["work_experience"][0]["bullets"]) == 3


def test_long_resumes_always_come_out_on_one_page():
    for roles, bullets, projects, pb in [(3, 5, 2, 3), (4, 6, 3, 4), (6, 8, 5, 5), (10, 10, 8, 6)]:
        data = _resume(roles, bullets, projects, pb)
        fitted = fit_resume(data)
        assert _pages(resume_pdf(fitted)) == 1, (roles, bullets, projects, pb)
        assert _pages(resume_pdf(data)) == 1                      # rows saved without a plan are fitted on the fly


def test_fit_shrinks_then_trims_lowest_value_content_first_and_keeps_order():
    data = _resume(roles=4, bullets=6, projects=3, project_bullets=4)
    fitted = fit_resume(data)
    assert fitted["scale"] >= 0.9                                  # text never gets unreadably small
    roles = fitted["tailored"]["work_experience"]
    assert [r["role"] for r in roles] == [f"Engineer {i}" for i in range(len(roles))]    # recent roles first, kept
    assert roles[0]["bullets"][0].endswith("(#0)")                 # the first (most relevant) bullets survive
    assert fitted["education"] and fitted["personal"]["full_name"] == "Asha Verma"
    # projects are trimmed before experience: with anything cut, the latest role still has bullets
    assert len(roles[0]["bullets"]) >= 2


def test_docx_uses_the_same_plan():
    from docx.shared import Mm

    data = _resume(roles=5, bullets=6, projects=3, project_bullets=3)
    fitted = fit_resume(data)
    assert fitted["scale"] < 1.0 or fitted["trim_level"] > 0
    builder = ResumeBuilder()
    path = builder.build(fitted["personal"], fitted["tailored"], fitted["education"],
                         filename="test_one_page_resume.docx", scale=fitted["scale"])
    try:
        doc = Document(BytesIO(path.read_bytes()))
        section = doc.sections[0]
        assert abs(section.page_width - Mm(210)) < 2000 and abs(section.page_height - Mm(297)) < 2000   # A4
        sizes = {r.font.size.pt for p in doc.paragraphs for r in p.runs if r.font.size}
        full = ResumeBuilder()
        full_path = full.build(fitted["personal"], fitted["tailored"], fitted["education"],
                               filename="test_one_page_resume_full.docx", scale=1.0)
        full_sizes = {r.font.size.pt for p in Document(BytesIO(full_path.read_bytes())).paragraphs
                      for r in p.runs if r.font.size}
        full_path.unlink()
        if fitted["scale"] < 1.0:
            assert max(sizes) < max(full_sizes)                    # fonts really were shrunk in the file
    finally:
        path.unlink()


def test_worker_stores_the_fitted_plan(monkeypatch):
    """resume_data keeps the plan (scale + trimmed content) so the later PDF matches the DOCX."""
    fitted = fit_resume(_resume(roles=6, bullets=8, projects=5, project_bullets=5))
    assert {"personal", "tailored", "education", "scale", "trim_level"} <= set(fitted)
    assert _pages(resume_pdf(fitted)) == 1
    assert settings.OUTPUT_DIR.exists()
