"""Job recommendation scoring: the failure modes that made suggestions bad."""
from datetime import datetime, timedelta, timezone

from app.services.job_recommendations import (
    MIN_MATCH_SCORE, JobListing, UserProfile, _clean_url, rank_jobs, score_job,
)

SKILLS = ["Python", "FastAPI", "PostgreSQL", "Docker"]
TITLES = ["Backend Engineer"]


def job(title="Backend Engineer", desc="", company="Acme", location="Remote",
        tags=None, url="https://x.test/1", posted_at=None, source="Remotive"):
    return JobListing(title, company, location, url, source, tags or [], desc, posted_at)


def scored(j, skills=SKILLS, titles=TITLES, years=4, location=""):
    score_job(j, skills, titles, years, location)
    return j


def test_good_match_passes():
    j = scored(job(desc="We use Python, FastAPI and Postgres on Docker."))
    assert j.match_score >= MIN_MATCH_SCORE
    assert set(j.matched_skills) == set(SKILLS)   # Postgres alias -> PostgreSQL


def test_unrelated_job_fails():
    j = scored(job(title="Marketing Manager", desc="Run campaigns and brand strategy."))
    assert j.match_score < MIN_MATCH_SCORE


def test_cpp_job_does_not_match_c_skill():
    j = scored(job(title="C++ Developer", desc="Modern C++ systems"), skills=["C"], titles=[])
    assert j.matched_skills == []


def test_go_skill_ignores_plain_english():
    j = scored(job(desc="Go to market with our team. Python experience."), skills=["Go"], titles=[])
    assert j.matched_skills == []
    j = scored(job(desc="We write Golang services."), skills=["Go"], titles=[])
    assert j.matched_skills == ["Go"]


def test_aliases_js_and_k8s():
    j = scored(job(desc="JS and k8s required"), skills=["JavaScript", "Kubernetes"], titles=[])
    # "js" is ambiguous (title/tags only) but "javascript" alias is not in text; k8s is
    assert "Kubernetes" in j.matched_skills


def test_company_name_is_not_searched():
    j = scored(job(company="Python Labs", desc="Sell insurance."), skills=["Python"], titles=[])
    assert j.matched_skills == []


def test_html_description_is_stripped():
    j = scored(job(desc="<p>Needs <b>Docker</b></p>"), skills=["Docker"], titles=[])
    assert j.matched_skills == ["Docker"]
    assert "<" not in j.description


def test_thin_listing_not_boosted_by_query():
    # LinkedIn list mode: no description, no tags. An unrelated title must fail.
    j = scored(job(title="Sales Executive", source="LinkedIn", location="Pune"),
               location="Pune, India")
    assert j.match_score < MIN_MATCH_SCORE


def test_thin_listing_with_right_title_can_pass():
    j = scored(job(title="Python Backend Engineer", source="LinkedIn"))
    assert j.match_score >= MIN_MATCH_SCORE


def test_seniority_mismatch_lowers_score():
    base = dict(desc="Python FastAPI PostgreSQL Docker")
    senior = scored(job(title="Senior Backend Engineer", **base), years=1)
    same = scored(job(title="Backend Engineer", **base), years=1)
    assert same.match_score > senior.match_score


def test_location_axis():
    far = scored(job(location="Berlin, Germany", desc="Python"), location="Pune, India")
    near = scored(job(location="Pune, India", desc="Python"), location="Pune, India")
    assert near.match_score > far.match_score


def test_rank_drops_stale_and_dedupes():
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    desc = "Python FastAPI PostgreSQL Docker"
    jobs = [
        job(desc=desc, url="https://x.test/a?utm_source=feed"),
        job(desc=desc, url="https://x.test/b"),                 # same title+company
        job(desc=desc, company="Other", url="https://x.test/c", posted_at=old),
    ]
    out = rank_jobs(jobs, UserProfile(skills=SKILLS, titles=TITLES, years=4))
    assert len(out) == 1
    assert "utm_source" not in out[0].url


def test_clean_url_keeps_real_params():
    assert _clean_url("https://x.test/j?id=7&utm_medium=a&ref=b") == "https://x.test/j?id=7"


def test_profile_fingerprint_changes_with_skills():
    a = UserProfile(skills=["Python"], titles=["Dev"]).fingerprint()
    b = UserProfile(skills=["Python", "Go"], titles=["Dev"]).fingerprint()
    assert a != b
