"""Scoring is deterministic; suggestions are technical, created once per job description and shrink as the user
applies them; an uploaded resume is scored next to the new one."""
import uuid

import pytest
from sqlalchemy import select

from app.agents.ai_agent import ai_agent
from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import JobApplication, ResumeSuggestion
from app.models.schemas import ParsedJD
from app.services import suggestion_store as store
from app.services.ats_score import build_suggestions, is_technical, jd_terms, score_view, view_from_text
from app.services.cache_service import cache_service
from app.worker import tasks
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register

JD_TEXT = ("We are hiring a Backend Engineer. You will build services in Python and FastAPI on Kubernetes, "
           "store data in PostgreSQL, use Kafka for events and Terraform for infrastructure. Docker is a plus. "
           "Strong communication skills and a fast-paced mindset. Kubernetes experience is essential. " * 2)


def jd() -> ParsedJD:
    return ParsedJD(
        job_title="Backend Engineer", company="Acme", seniority="Mid",
        required_skills=["Python", "FastAPI", "Kubernetes", "PostgreSQL", "Strong communication"],
        preferred_skills=["Kafka", "Terraform", "Docker", "Teamwork"],
        keywords=["microservices", "REST APIs", "fast-paced", "problem solving", "Python"],
        raw_text=JD_TEXT)


# ── Pure scoring ─────────────────────────────────────────────────────────────

def test_soft_skills_and_filler_are_never_suggestions():
    for soft in ("Strong communication", "Teamwork", "fast-paced", "problem solving", "English", "leadership",
                 "excellent written and verbal communication skills in a fast paced team"):
        assert not is_technical(soft), soft
    for tech in ("Kubernetes", "REST APIs", "CI/CD", "C++", "Node.js", "machine learning", "AWS Lambda"):
        assert is_technical(tech), tech
    terms = [t.term for t in jd_terms(jd())]
    assert "Strong communication" not in terms and "Teamwork" not in terms and "fast-paced" not in terms


def test_scores_are_deterministic_and_comparable():
    terms = jd_terms(jd())
    resume = "Asha\nasha@x.com\n+91 98765 43210\nSUMMARY\nBackend developer\nSKILLS\nPython, PostgreSQL, Docker\n" \
             "EXPERIENCE\n- Built APIs\n- Improved latency\nEDUCATION\nB.E."
    first = score_view(view_from_text(resume), terms)
    assert all(score_view(view_from_text(resume), terms) == first for _ in range(5))      # same input, same score
    more = score_view(view_from_text(resume + "\nKubernetes FastAPI Kafka Terraform"), terms)
    assert more["total_score"] > first["total_score"]
    assert set(first["missing_skills"]) >= {"FastAPI", "Kubernetes"} and "Python" in first["matched_skills"]


def test_suggestions_are_the_technical_gaps_ranked_by_importance():
    owned = "Python PostgreSQL Docker developer"
    s = build_suggestions(jd_terms(jd()), owned)
    terms = [i["term"] for i in s]
    assert terms[0] == "Kubernetes"                                  # required and mentioned most
    assert "Python" not in terms and "PostgreSQL" not in terms and "Docker" not in terms
    assert {"FastAPI", "Kafka", "Terraform"} <= set(terms)
    assert all(i["status"] == "open" and i["why"] for i in s) and len(s) <= 12
    assert build_suggestions(jd_terms(jd()), owned) == s             # same inputs, same list


def test_a_term_present_under_an_alias_is_not_suggested():
    owned = "Used Postgres and K8s daily"
    terms = [i["term"] for i in build_suggestions(jd_terms(jd()), owned)]
    assert "PostgreSQL" not in terms and "Kubernetes" not in terms


# ── The three-version scenario, through the real worker task ─────────────────

@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(settings, "LLM_FAKE", True)
    monkeypatch.setattr(ai_agent, "parse_jd", lambda text: jd())
    # Even if the model mangled every JD analysis afterwards, the stored suggestions must not change.
    return monkeypatch


async def _user_with_profile(client):
    h = bearer(await register(client, unique_email()))
    uid = uuid.UUID((await client.get("/api/auth/me", headers=h)).json()["id"])
    await client.post("/api/metabase/personal", headers=h, json={
        "full_name": "Asha Verma", "email": "asha@atsready-tests.dev", "phone": "+91 98765 43210",
        "location": "Pune, India", "professional_summary": "Backend engineer who builds APIs."})
    for name in ("Python", "PostgreSQL"):
        await client.post("/api/metabase/skills", headers=h, json={"name": name, "category": "Languages"})
    await client.post("/api/metabase/experience", headers=h, json={
        "company": "Acme", "role": "Engineer", "start_date": "Jan 2022", "end_date": "Present",
        "bullets": [{"bullet": "Built Python services on PostgreSQL handling 2M requests per day"},
                    {"bullet": "Wrote automated tests for the billing module"}]})
    return h, uid


async def _run(uid, emphasis=None, baseline_id=None) -> dict:
    """Create a job row and run the real worker task; return the saved ats_breakdown."""
    async with AsyncSessionLocal() as db:
        job = JobApplication(user_id=uid, status="pending")
        db.add(job)
        await db.commit()
        job_id = job.id
    await tasks.generate_resume({}, str(job_id), str(uid), None, JD_TEXT, emphasis, baseline_id)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(JobApplication).where(JobApplication.id == job_id))).scalar_one()
        assert row.status == "done", row.error_message
        return {"breakdown": row.ats_breakdown, "data": row.resume_data}


async def test_suggestions_are_created_once_and_only_shrink_across_versions(client, pipeline):
    _, uid = await _user_with_profile(client)

    v1 = (await _run(uid))["breakdown"]
    first = [i["term"] for i in v1["open_suggestions"]]
    assert first[0] == "Kubernetes" and {"FastAPI", "Kafka", "Terraform", "Docker"} <= set(first)
    assert "Strong communication" not in first and "Teamwork" not in first      # nothing non-technical
    assert v1["projected_score"] > v1["total_score"]                           # applying them would help

    # The user ticks two. They are applied; everything else stays open and nothing new appears.
    v2 = (await _run(uid, emphasis=["Kubernetes", "FastAPI"]))["breakdown"]
    second = [i["term"] for i in v2["open_suggestions"]]
    assert second == [t for t in first if t not in ("Kubernetes", "FastAPI")]          # same order, only unselected
    assert set(v2["applied_terms"]) == {"Kubernetes", "FastAPI"}
    assert v2["total_score"] > v1["total_score"]

    # A later version with nothing ticked keeps what was applied and surfaces the same remainder.
    v3 = (await _run(uid))["breakdown"]
    assert [i["term"] for i in v3["open_suggestions"]] == second
    assert set(v3["applied_terms"]) == {"Kubernetes", "FastAPI"}
    assert v3["total_score"] == v2["total_score"]                              # deterministic

    # Applying the rest ends with no suggestions left and a higher score.
    v4 = (await _run(uid, emphasis=second))["breakdown"]
    assert v4["open_suggestions"] == [] and v4["total_score"] > v3["total_score"]
    assert v4["projected_score"] == v4["total_score"]

    async with AsyncSessionLocal() as db:                                       # one row for the whole lineage
        rows = (await db.execute(select(ResumeSuggestion).where(ResumeSuggestion.user_id == uid))).scalars().all()
    assert len(rows) == 1 and all(i["status"] == "applied" for i in rows[0].items)


async def test_confirmed_skills_appear_in_skills_but_never_in_invented_bullets(client, pipeline):
    _, uid = await _user_with_profile(client)
    out = await _run(uid, emphasis=["Kubernetes", "Terraform"])
    data = out["data"]
    skills = " ".join(i for g in data["tailored"]["skills"] for i in g["items"])
    assert "Kubernetes" in skills and "Terraform" in skills
    bullets = " ".join(b for e in data["tailored"]["work_experience"] for b in e["bullets"])
    assert "Kubernetes" not in bullets and "Terraform" not in bullets
    assert all(b in ("Built Python services on PostgreSQL handling 2M requests per day",
                     "Wrote automated tests for the billing module") for e in data["tailored"]["work_experience"]
               for b in e["bullets"])                                           # only the candidate's own bullets


async def test_a_term_the_user_types_is_kept_as_applied(client, pipeline):
    _, uid = await _user_with_profile(client)
    v = (await _run(uid, emphasis=["gRPC"]))["breakdown"]
    assert "gRPC" in v["applied_terms"] and "gRPC" not in [i["term"] for i in v["open_suggestions"]]


async def test_stored_suggestions_ignore_a_changed_jd_analysis(client, pipeline):
    _, uid = await _user_with_profile(client)
    first = [i["term"] for i in (await _run(uid))["breakdown"]["open_suggestions"]]
    pipeline.setattr(ai_agent, "parse_jd", lambda text: ParsedJD(
        job_title="Backend Engineer", required_skills=["Haskell", "Erlang"], raw_text=JD_TEXT))
    again = [i["term"] for i in (await _run(uid))["breakdown"]["open_suggestions"]]
    assert again == first and "Haskell" not in again


async def test_uploaded_resume_is_scored_and_beaten_by_the_new_one(client, pipeline):
    _, uid = await _user_with_profile(client)
    uploaded = ("Asha Verma\nasha@x.com\n+91 98765 43210\nSUMMARY\nDeveloper\nSKILLS\nPython, Kubernetes\n"
                "EXPERIENCE\n- Worked on things\nEDUCATION\nB.E.\n" + "filler text " * 40)
    bid = uuid.uuid4().hex
    await cache_service.set(f"baseline:{uid}:{bid}", {"filename": "my_resume.pdf", "text": uploaded}, ttl=600)

    v = (await _run(uid, baseline_id=bid))["breakdown"]
    base = v["baseline"]
    assert base["filename"] == "my_resume.pdf" and 0 < base["total_score"] < v["total_score"]
    assert v["score_gain"] == round(v["total_score"] - base["total_score"], 1) and v["score_gain"] > 0
    assert "FastAPI" in base["missing_skills"]
    # Kubernetes is in the uploaded resume (the user's own words), so it is not suggested and is kept as a skill.
    assert "Kubernetes" not in [i["term"] for i in v["open_suggestions"]]


async def test_no_baseline_means_no_comparison_fields(client, pipeline):
    _, uid = await _user_with_profile(client)
    v = (await _run(uid))["breakdown"]
    assert "baseline" not in v and "score_gain" not in v


async def test_baseline_upload_endpoint(client, monkeypatch):
    from io import BytesIO

    import docx
    h = bearer(await register(client, unique_email()))
    d = docx.Document()
    d.add_paragraph("Asha Verma\nasha@x.com\n" + "Built backend services in Python and FastAPI. " * 12)
    buf = BytesIO()
    d.save(buf)
    r = await client.post("/api/resume-baseline", headers=h,
                          files={"file": ("my_resume.docx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["filename"] == "my_resume.docx" and r.json()["words"] > 50
    uid = (await client.get("/api/auth/me", headers=h)).json()["id"]
    stored = await cache_service.get(f"baseline:{uid}:{r.json()['id']}")
    assert stored and "Python and FastAPI" in stored["text"]
    assert (await client.post("/api/resume-baseline", headers=h,
                              files={"file": ("a.txt", b"x" * 500, "text/plain")})).status_code == 422
    tiny = BytesIO()
    docx.Document().save(tiny)
    assert (await client.post("/api/resume-baseline", headers=h,
                              files={"file": ("e.docx", tiny.getvalue(), "application/octet-stream")})).status_code == 422
    assert (await client.post("/api/resume-baseline", headers=h,
                              files={"file": ("bad.docx", b"this is not a zip")})).status_code == 422   # corrupt file
    assert store.jd_hash("A  b\nC") == store.jd_hash("a b c")        # same job description, whatever its spacing


async def test_an_older_resume_keeps_its_breakdown_and_shows_todays_suggestions(client, pipeline):
    h, uid = await _user_with_profile(client)
    v1 = (await _run(uid))["breakdown"]
    await _run(uid, emphasis=["Kubernetes", "FastAPI"])              # a later version applies two of them

    jobs = (await client.get("/api/jobs", headers=h)).json()["items"]
    oldest = sorted(jobs, key=lambda j: j["created_at"])[0]
    got = (await client.get(f"/api/jobs/{oldest['id']}", headers=h)).json()

    # what that version scored, stored with it, unchanged
    assert got["ats_breakdown"]["total_score"] == v1["total_score"]
    assert "Kubernetes" in [i["term"] for i in got["ats_breakdown"]["open_suggestions"]]
    assert got["jd_text"].strip() == JD_TEXT.strip()                  # enough to improve it from the same posting
    # what is still open today: the two ticked later are not offered again
    now = got["suggestions_now"]
    open_now = [i["term"] for i in now["open"]]
    assert "Kubernetes" not in open_now and "FastAPI" not in open_now and "Kafka" in open_now
    assert set(now["applied"]) == {"Kubernetes", "FastAPI"}
    assert now["projected_score"] > v1["total_score"]
