"""Nothing the candidate did not say: numbers, tools, employers, titles."""
from app.services.grounding import (
    add_known_terms,
    allowed_numbers,
    enforce_letter,
    enforce_resume,
    numbers_in,
)

PROFILE = {
    "personal": {"professional_summary": "Backend engineer who builds APIs."},
    "skills": [{"name": "Python", "category": "Languages", "keywords": []},
               {"name": "PostgreSQL", "category": "Data", "keywords": []},
               {"name": "Docker", "category": "Tools", "keywords": []}],
    "experience": [{
        "company": "Northwind Labs", "role": "Backend Engineer", "location": "Pune",
        "start_date": "Jun 2022", "end_date": "Present", "tech_stack": ["Python", "Docker"],
        "bullets": [{"text": "Built FastAPI services handling 2M requests per day on PostgreSQL"},
                    {"text": "Cut p95 latency by 40% by adding Redis caching"},
                    {"text": "Wrote unit tests for the billing module"}]}],
    "projects": [{"title": "Resume Tailor", "tech_stack": ["Python", "FastAPI"], "github_url": "https://x/y",
                  "bullets": [{"text": "Built a tool that tailors resumes to job descriptions"}]}],
    "education": [],
}
JD_TERMS = ["Python", "Kubernetes", "Terraform", "PostgreSQL", "Kafka", "Docker"]


def _tailored(bullets, summary="Backend Engineer with Python and PostgreSQL experience."):
    return {"professional_summary": summary,
            "skills": [{"category": "Languages", "items": ["Python", "PostgreSQL"]}],
            "work_experience": [{"company": "Northwind Labs", "role": "Staff Backend Engineer", "location": "Remote",
                                 "start_date": "2019", "end_date": "2024", "bullets": bullets}],
            "projects": []}


def test_numbers_are_compared_without_formatting():
    assert numbers_in("handled 2,000 requests and 40% faster, 3.5x") == {"2000", "40", "3.5"}
    assert "2" in allowed_numbers(PROFILE) and "40" in allowed_numbers(PROFILE)


def test_honest_rewording_is_kept():
    out, report = enforce_resume(_tailored([
        "Engineered FastAPI services serving 2M requests per day on PostgreSQL",
        "Reduced p95 latency by 40% through Redis caching"]), PROFILE, JD_TERMS)
    bullets = out["work_experience"][0]["bullets"]
    assert bullets[0].startswith("Engineered FastAPI") and bullets[1].startswith("Reduced p95")
    assert not [r for r in report if r.startswith("bullet")]


def test_an_invented_number_is_replaced_by_the_original_bullet():
    out, report = enforce_resume(_tailored([
        "Cut p95 latency by 85% by adding Redis caching, saving $2.1M annually"]), PROFILE, JD_TERMS)
    bullets = out["work_experience"][0]["bullets"]
    assert bullets == ["Cut p95 latency by 40% by adding Redis caching"]
    assert any("not in the candidate's data" in r for r in report)


def test_a_technology_the_candidate_never_used_is_not_added_to_a_bullet():
    out, _ = enforce_resume(_tailored([
        "Built FastAPI services on Kubernetes and Terraform handling 2M requests per day"]), PROFILE, JD_TERMS)
    text = " ".join(out["work_experience"][0]["bullets"])
    assert "Kubernetes" not in text and "Terraform" not in text
    assert "2M requests" in text                       # swapped for the candidate's own bullet


def test_employer_role_dates_and_location_come_from_the_profile_not_the_model():
    out, _ = enforce_resume(_tailored(["Wrote unit tests for the billing module"]), PROFILE, JD_TERMS)
    e = out["work_experience"][0]
    assert (e["company"], e["role"], e["location"], e["start_date"], e["end_date"]) == (
        "Northwind Labs", "Backend Engineer", "Pune", "Jun 2022", "Present")


def test_an_employer_or_project_not_in_the_profile_is_dropped():
    t = _tailored(["Did things"])
    t["work_experience"].append({"company": "Google", "role": "Staff Engineer", "bullets": ["Led search"]})
    t["projects"] = [{"title": "Totally Made Up App", "tech_stack": ["Rust"], "bullets": ["Shipped it"]}]
    out, report = enforce_resume(t, PROFILE, JD_TERMS)
    assert [e["company"] for e in out["work_experience"]] == ["Northwind Labs"] and out["projects"] == []
    assert any("Google" in r for r in report) and any("Totally Made Up App" in r for r in report)


def test_a_role_never_ends_up_with_no_bullets():
    out, _ = enforce_resume(_tailored(["Led a team of 12 engineers across 4 time zones"]), PROFILE, JD_TERMS)
    assert out["work_experience"][0]["bullets"]       # fell back to the candidate's own bullets


def test_summary_sentences_with_unsupported_claims_are_removed():
    out, _ = enforce_resume(_tailored(
        ["Wrote unit tests for the billing module"],
        summary="Backend Engineer with Python experience. Led 15 engineers and cut costs by 60%. "
                "Expert in Kubernetes."), PROFILE, JD_TERMS)
    s = out["professional_summary"]
    assert "Python" in s and "15" not in s and "60" not in s and "Kubernetes" not in s


def test_unsupported_summary_falls_back_to_the_candidates_own():
    out, _ = enforce_resume(_tailored(["Wrote unit tests for the billing module"],
                                      summary="Saved 90% of cloud costs."), PROFILE, JD_TERMS)
    assert out["professional_summary"] == "Backend engineer who builds APIs."


def test_confirmed_skills_are_allowed_in_skills_but_not_in_bullets():
    t = _tailored(["Deployed everything on Kubernetes"])
    t["skills"] = [{"category": "Tools", "items": ["Python", "Kubernetes", "Kafka"]}]
    out, _ = enforce_resume(t, PROFILE, JD_TERMS, confirmed=["Kubernetes"])
    items = out["skills"][0]["items"]
    assert "Kubernetes" in items and "Kafka" not in items            # the user vouched for one, not the other
    assert "Kubernetes" not in " ".join(out["work_experience"][0]["bullets"])


def test_known_terms_are_added_to_skills_once():
    t = {"skills": [{"category": "A", "items": ["Python"]}], "work_experience": [], "projects": [],
         "professional_summary": ""}
    out, added = add_known_terms(t, ["Docker", "python", "PostgreSQL", "Docker"])
    assert added == ["Docker", "PostgreSQL"]                          # Python is already there
    assert out["skills"][-1] == {"category": "Also Relevant", "items": ["Docker", "PostgreSQL"]}
    assert add_known_terms(out, ["Docker"])[1] == []


# ── Cover letter ─────────────────────────────────────────────────────────────

LETTER = ("Dear Hiring Team,\n\n"
          "I was drawn to Acme because of your focus on reliable APIs. "
          "At Northwind Labs I built FastAPI services handling 2M requests per day. "
          "I also reduced latency by 70% and led a team of 9 engineers.\n\n"
          "I have deep Kubernetes experience running clusters in production. "
          "Your platform runs on Kubernetes, which is exactly the scale I enjoy.\n\n"
          "The role asks for 5+ years of backend work, which fits my background.\n\n"
          "Best regards,\nAsha")


def test_letter_keeps_true_claims_and_job_numbers_and_removes_invented_ones():
    out, report = enforce_letter(LETTER, PROFILE, "We need 5+ years of backend experience. Kubernetes is a plus.",
                                 JD_TERMS)
    assert "2M requests per day" in out                         # in the candidate's data
    assert "70%" not in out and "team of 9" not in out         # invented figures: gone
    assert "deep Kubernetes experience" not in out             # a claimed tool the candidate never listed
    assert "Your platform runs on Kubernetes" in out           # the company's tool, not a claim about the candidate
    assert "5+ years" in out                                   # a number from the job posting itself
    assert out.startswith("Dear Hiring Team,") and out.rstrip().endswith("Asha")
    assert len(report) >= 2


def test_letter_allows_a_confirmed_skill_claim():
    out, _ = enforce_letter("I have worked with Kubernetes.", PROFILE, "", JD_TERMS, confirmed=["Kubernetes"])
    assert "Kubernetes" in out
