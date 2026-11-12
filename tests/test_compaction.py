"""Local prompt shrinking must never drop what the job asks for."""
import json

from app.services.compaction import (
    compact_jd, compact_profile, head_tail, local_ats_score, profile_as_tailored,
    resume_text_for_scoring,
)


def big_profile(n_roles=4, n_bullets=12):
    exp = []
    for r in range(n_roles):
        bullets = [{"text": f"Did generic task number {i} in role {r} " + "x" * 60,
                    "keywords": ["misc"], "impact_score": 3} for i in range(n_bullets)]
        exp.append({"company": f"Co{r}", "role": f"Engineer {r}", "start_date": "2020",
                    "end_date": "Present", "bullets": bullets, "tech_stack": []})
    # one buried bullet that matches the JD
    exp[-1]["bullets"][-1] = {"text": "Ran production Kubernetes clusters on AWS",
                              "keywords": ["kubernetes", "aws"], "impact_score": 1}
    return {
        "personal": {"full_name": "A", "linkedin": "https://linkedin.com/in/a", "phone": ""},
        "skills": [{"name": f"Skill{i}", "category": "Tools", "keywords": ["k"] * 20}
                   for i in range(40)] + [{"name": "Kubernetes", "category": "Cloud"}],
        "experience": exp,
        "projects": [{"title": f"P{i}", "description": "d" * 500, "bullets": [{"text": "b" * 80}]}
                     for i in range(6)],
        "education": [{"institution": "Uni", "degree": "BSc", "relevant_coursework": ["c"] * 30}],
    }


def test_small_profile_untouched_apart_from_empty_fields():
    p = {"personal": {"full_name": "A", "phone": None}, "skills": [{"name": "Py"}],
         "experience": [], "projects": [], "education": []}
    out = compact_profile(p, ["py"], max_chars=5000)
    assert out["personal"] == {"full_name": "A"}
    assert out["skills"] == [{"name": "Py"}]


def test_fits_budget_and_keeps_relevant_bullet():
    prof = big_profile()
    full = len(json.dumps(prof))
    out = compact_profile(prof, ["Kubernetes", "AWS"], max_chars=full // 4)
    assert len(json.dumps(out, separators=(",", ":"))) <= full // 4
    bullets = [b["text"] for e in out["experience"] for b in e["bullets"]]
    assert "Ran production Kubernetes clusters on AWS" in bullets


def test_structure_never_dropped():
    prof = big_profile()
    out = compact_profile(prof, ["Kubernetes"], max_chars=1500)
    assert [e["role"] for e in out["experience"]] == [e["role"] for e in prof["experience"]]
    assert {s["name"] for s in out["skills"]} == {s["name"] for s in prof["skills"]}
    assert out["personal"]["linkedin"] == "https://linkedin.com/in/a"
    assert out["education"][0]["institution"] == "Uni"
    assert all(e["bullets"] for e in out["experience"])          # at least one each


def test_input_not_mutated():
    prof = big_profile()
    before = json.dumps(prof)
    compact_profile(prof, ["x"], max_chars=1000)
    assert json.dumps(prof) == before


def test_compact_jd_drops_boilerplate_keeps_requirements():
    jd = ("Backend Engineer at Acme\n\nAbout us:\n" + "We love dogs. " * 400 +
          "\n\nRequirements:\nPython, FastAPI, Kubernetes experience.\n\n"
          "Benefits:\n" + "Free snacks. " * 400 + "\n\nResponsibilities:\nBuild APIs.")
    out = compact_jd(jd, limit=1000)
    assert "Kubernetes" in out and "Build APIs" in out and "Backend Engineer" in out
    assert "dogs" not in out and "snacks" not in out
    assert len(out) <= 1000 + 40


def test_compact_jd_short_text_unchanged():
    assert compact_jd("short jd", 8000) == "short jd"


def test_head_tail_keeps_both_ends():
    t = "START" + "m" * 5000 + "END"
    out = head_tail(t, 1000)
    assert out.startswith("START") and out.endswith("END")


def test_profile_as_tailored_shape():
    t = profile_as_tailored(big_profile(1, 2))
    assert t["work_experience"][0]["bullets"] and t["skills"]


def test_local_score_flags_estimated_and_counts_overlap():
    tailored = {"professional_summary": "Python engineer", "skills": [{"category": "x", "items": ["FastAPI"]}],
                "work_experience": [{"role": "Dev", "company": "Co", "bullets": ["Built APIs with FastAPI"]}]}
    s = local_ats_score(["Python", "FastAPI", "Rust"], ["Python", "Rust"], tailored)
    assert s["estimated"] is True
    assert s["matched_keywords"] == ["Python", "FastAPI"] and s["missing_keywords"] == ["Rust"]
    assert s["skills_score"] == 50.0
    assert "Python engineer" in resume_text_for_scoring(tailored)


def test_ground_skills_drops_padding_but_keeps_aliases():
    from app.services.compaction import ground_skills
    profile = {"skills": [{"category": "DB", "items": ["PostgreSQL", "Docker"]}],
               "work_experience": [{"bullets": ["Deployed to Kubernetes on AWS"]}]}
    tailored = {"skills": [{"category": "Backend", "items": ["Postgres", "Docker", "Agile", "Git", "K8s", "Amazon Web Services"]},
                           {"category": "Process", "items": ["Scrum"]}]}
    out, dropped = ground_skills(tailored, profile)
    assert out["skills"] == [{"category": "Backend", "items": ["Postgres", "Docker", "K8s", "Amazon Web Services"]}]
    assert sorted(dropped) == ["Agile", "Git", "Scrum"]


def test_ground_skills_never_returns_an_empty_skill_section():
    from app.services.compaction import ground_skills
    tailored = {"skills": [{"category": "X", "items": ["Fortran"]}]}
    out, dropped = ground_skills(tailored, {"skills": []})
    assert out is tailored and dropped == []
