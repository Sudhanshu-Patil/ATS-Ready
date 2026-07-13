"""Pure unit tests — no DB, no network."""
import pytest

from app.worker.tasks import _slugify
from app.services.job_recommendations import score_job, JobListing


# ── Filename slugify (regression: 'AI/ML Engineer' created an unwritable
#    subdirectory path and broke .docx saving) ────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("AI/ML Engineer", "ai_ml_engineer"),
    ("C++ Developer", "c_developer"),
    ("Node.js Engineer (Remote)", "node_js_engineer_rem"),
    ("", "untitled"),
    ("///", "untitled"),
])
def test_slugify_never_emits_path_separators(raw, expected):
    out = _slugify(raw, 20)
    assert out == expected
    assert "/" not in out and "\\" not in out


# ── Job match scoring (regression: ratio divided by TOTAL skill count, so
#    richer profiles scored WORSE — capped at SKILL_MATCH_CAP now) ────────────

def _listing(description):
    return JobListing(
        title="Senior Backend Engineer",
        company="TestCo",
        location="Remote",
        url="https://example.com/job",
        source="Test",
        tags=[],
        description=description,
        posted_at=None,
    )


def test_rich_profile_not_penalized():
    description = "We need python fastapi postgresql redis docker kubernetes aws linux"
    matched_8_of_8 = _listing(description)
    score_job(matched_8_of_8, ["Python", "FastAPI", "PostgreSQL", "Redis",
                               "Docker", "Kubernetes", "AWS", "Linux"],
              ["Senior Backend Engineer"])

    matched_8_of_24 = _listing(description)
    score_job(matched_8_of_24, ["Python", "FastAPI", "PostgreSQL", "Redis",
                                "Docker", "Kubernetes", "AWS", "Linux"] +
                               [f"Other Skill {i}" for i in range(16)],
              ["Senior Backend Engineer"])

    # 8 matched skills earn full skill credit regardless of profile size
    assert matched_8_of_24.match_score == matched_8_of_8.match_score


def test_no_skills_matched_scores_low():
    job = _listing("we need golang rust elixir")
    score_job(job, ["Python", "FastAPI"], ["Backend Engineer"])
    assert job.match_score < 40
    assert job.matched_skills == []
