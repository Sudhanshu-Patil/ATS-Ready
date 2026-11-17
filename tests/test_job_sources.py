"""New job sources against canned responses, and the user's location filter end to end."""
import html
import json

import httpx

from app.config import settings
from app.services import job_sources as src
from app.services.job_recommendations import JobListing, UserProfile, rank_jobs


def client_for(routes: dict) -> httpx.AsyncClient:
    """routes: url-substring -> (status, body). First match wins; anything else is a 404."""
    def handler(request: httpx.Request) -> httpx.Response:
        for needle, spec in routes.items():
            if needle in str(request.url):
                status, body = spec[0], spec[1]
                if isinstance(body, (dict, list)):
                    return httpx.Response(status, json=body)
                return httpx.Response(status, text=body)
        return httpx.Response(404, json={})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


async def test_remoteok_skips_legal_notice_and_keeps_location_fence():
    c = client_for({"remoteok.com": (200, [
        {"legal": "terms"},
        {"position": "Python Dev", "company": "A", "location": "Worldwide", "url": "https://remoteok.com/1",
         "tags": ["python"], "description": "<p>x</p>", "date": "2026-11-10T00:00:00+00:00"},
        {"position": "Go Dev", "company": "B", "location": "", "url": "https://remoteok.com/2"}])})
    jobs = await src.fetch_remoteok(c)
    assert [j.title for j in jobs] == ["Python Dev", "Go Dev"]
    assert jobs[0].location == "Remote - Worldwide" and jobs[1].location == "Remote"


async def test_himalayas_reads_restrictions_in_both_shapes():
    c = client_for({"himalayas.app": (200, {"jobs": [
        {"title": "A", "companyName": "X", "locationRestrictions": ["India"], "applicationLink": "https://h/1",
         "pubDate": "1794893246", "categories": ["Backend"]},
        {"title": "B", "companyName": "Y", "locationRestrictions": "['Canada', 'United States']",
         "applicationLink": "https://h/2"},
        {"title": "C", "companyName": "Z", "locationRestrictions": [], "applicationLink": "https://h/3"}]})})
    jobs = {j.title: j for j in await src.fetch_himalayas(c)}
    assert jobs["A"].location == "Remote - India" and jobs["A"].posted_at.startswith("2026")
    assert jobs["B"].location == "Remote - Canada, United States"
    assert jobs["C"].location == "Remote (worldwide)"


async def test_weworkremotely_rss_with_region():
    rss = """<?xml version="1.0"?><rss><channel>
      <item><title>Acme: Senior Backend Engineer</title><region>USA Only</region>
        <category>Back-End Programming</category><link>https://wwr/1</link>
        <description><![CDATA[<p>Build APIs</p>]]></description><pubDate>Mon, 16 Nov 2026 10:00:00 +0000</pubDate></item>
      <item><title>Globex: DevOps</title><link>https://wwr/2</link></item></channel></rss>"""
    jobs = await src.fetch_weworkremotely(client_for({"weworkremotely.com": (200, rss)}))
    first = next(j for j in jobs if j.url == "https://wwr/1")
    assert (first.title, first.company, first.location) == ("Senior Backend Engineer", "Acme", "Remote - USA Only")
    assert first.posted_at.startswith("2026-11-16")


def _yc_page(postings):
    return f'<html><div data-page="{html.escape(json.dumps({"props": {"jobPostings": postings}}))}"></div></html>'


async def test_yc_jobs_parse_location_skills_and_us_only_visa():
    page = _yc_page([
        {"id": 1, "title": "Backend Engineer", "url": "/companies/acme/jobs/x", "location": "Bangalore, India",
         "skills": ["Python", "Postgres"], "minExperience": "3+ years", "companyName": "Acme",
         "companyBatchName": "W24", "companyOneLiner": "Payments for devs", "visa": "Will sponsor"},
        {"id": 2, "title": "Remote Engineer", "url": "/companies/b/jobs/y", "location": "Remote",
         "visa": "US citizen/visa only", "companyName": "B"},
        {"id": 1, "title": "dup", "url": "/dup", "location": "x"}])
    jobs = await src.fetch_yc_jobs(client_for({"ycombinator.com/jobs/role": (200, page)}), ["Backend Engineer"])
    by = {j.title: j for j in jobs}
    assert len(jobs) == 2 and by["Backend Engineer"].company == "Acme (W24)"
    assert by["Backend Engineer"].tags == ["python", "postgres"] and "3+ years" in by["Backend Engineer"].description
    assert by["Remote Engineer"].location == "Remote (US only)"
    assert by["Backend Engineer"].url == "https://www.ycombinator.com/companies/acme/jobs/x"


def test_yc_role_slugs_follow_the_users_titles():
    assert src.yc_role_slugs(["Senior Backend Engineer"]) == ["software-engineer", "backend-engineer"]
    assert src.yc_role_slugs(["Machine Learning Engineer", "Data Scientist"])[:3] == [
        "software-engineer", "machine-learning-engineer", "data-scientist"]


def test_parse_hn_job_titles():
    p = src.parse_hn_job_title("Acme (YC W23) is hiring a Senior Backend Engineer in Bangalore")
    assert p["company"] == "Acme" and p["location"] == "Bangalore"
    assert src.parse_hn_job_title("Foo (YC S21) Is Hiring Engineers (Remote)")["location"] == "Remote"
    assert src.parse_hn_job_title("Just a title")["company"] == ""


async def test_hn_jobs_uses_the_official_api():
    c = client_for({
        "jobstories.json": (200, [11, 12]),
        "item/11.json": (200, {"id": 11, "title": "Acme (YC W23) is hiring a Backend Engineer in Pune",
                               "url": "https://acme.com/jobs", "time": 1794603671, "type": "job"}),
        "item/12.json": (200, {"id": 12, "title": "Dead one", "dead": True})})
    jobs = await src.fetch_hn_jobs(c)
    assert len(jobs) == 1 and jobs[0].company == "Acme" and jobs[0].location == "Pune"
    assert jobs[0].source == "HN Jobs (YC)" and jobs[0].posted_at.startswith("2026")


def test_hn_hiring_header_is_classified_by_content_not_position():
    h = src.parse_hn_hiring_comment("Acme | Senior Backend Engineer | Bangalore, India | REMOTE | $150k\nWe build...")
    assert h["company"] == "Acme" and h["role"] == "Senior Backend Engineer"
    assert "Bangalore" in h["location"] and "REMOTE" in h["location"]
    h2 = src.parse_hn_hiring_comment("Globex | Onsite in Berlin | Full-stack developer\nText")
    assert h2["role"] == "Full-stack developer" and "Berlin" in h2["location"]
    assert src.parse_hn_hiring_comment("No pipes here, just a rambling comment") is None


async def test_hn_hiring_reads_the_latest_thread():
    long_text = "Acme | Backend Engineer | Bangalore | REMOTE<p>" + "We are hiring engineers. " * 8
    c = client_for({
        "search_by_date": (200, {"hits": [{"objectID": "99", "title": "Ask HN: Who is hiring? (November 2026)"}]}),
        "items/99": (200, {"children": [{"id": 5, "text": long_text, "created_at": "2026-11-02T00:00:00Z"},
                                         {"id": 6, "text": "short"}]})})
    jobs = await src.fetch_hn_hiring(c)
    assert len(jobs) == 1 and jobs[0].title == "Backend Engineer" and "Bangalore" in jobs[0].location
    assert jobs[0].url.endswith("id=5")


async def test_a_failing_source_returns_empty_not_an_exception():
    c = client_for({})                                  # every URL 404s
    assert await src.fetch_remoteok(c) == [] and await src.fetch_himalayas(c) == []
    assert await src.fetch_hn_jobs(c) == [] and await src.fetch_yc_jobs(c, []) == []


# ── Google dork search ────────────────────────────────────────────────────────

def test_dork_queries_target_ats_sites_and_places():
    qs = src.dork_queries(["Backend Engineer"], ["Bangalore", "Pune", "Mumbai"], remote_ok=True)
    assert len(qs) == 3 and '"Backend Engineer" "Bangalore"' in qs[0] and "site:jobs.lever.co" in qs[0]
    assert qs[-1].startswith('"Backend Engineer" "remote"')


async def test_dork_search_is_off_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CSE_KEY", "")
    assert await src.fetch_web_dork(client_for({}), ["Dev"], ["Pune"], True) == []


async def test_dork_search_enriches_greenhouse_jobs(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CSE_KEY", "k")
    monkeypatch.setattr(settings, "GOOGLE_CSE_CX", "cx")

    async def budget(n):
        return True
    monkeypatch.setattr(src, "_dork_budget_ok", budget)
    c = client_for({
        "customsearch/v1": (200, {"items": [
            {"link": "https://boards.greenhouse.io/acme/jobs/123",
             "title": "Job Application for Backend Engineer at Acme", "snippet": "Join us"},
            {"link": "https://jobs.ashbyhq.com/globex/abc", "title": "Data Engineer - Globex",
             "snippet": "Location: Pune, India. Build."}]}),
        "boards-api.greenhouse.io": (200, {"title": "Backend Engineer", "location": {"name": "Bengaluru, India"},
                                           "content": "&lt;p&gt;Python and Postgres&lt;/p&gt;",
                                           "company_name": "Acme"})})
    jobs = {j.url.split("/")[2]: j for j in await src.fetch_web_dork(c, ["Backend Engineer"], ["Bangalore"], False)}
    gh, ashby = jobs["boards.greenhouse.io"], jobs["jobs.ashbyhq.com"]
    assert gh.title == "Backend Engineer" and gh.company == "Acme" and gh.location == "Bengaluru, India"
    assert "Python" in gh.description
    assert ashby.location == "Pune, India" and ashby.source == "Web search"


# ── The user's location filter ────────────────────────────────────────────────

def _job(title, location, source="x"):
    return JobListing(title, f"Co {location}", location, f"https://x.test/{title}-{location}", source, ["python"],
                      "We use Python and FastAPI and PostgreSQL daily.", None)


def test_rank_jobs_only_keeps_places_the_user_will_work():
    profile = UserProfile(skills=["Python", "FastAPI", "PostgreSQL"], titles=["Backend Engineer"], years=4,
                          location="Bangalore, India", preferred_locations=["Bangalore", "Pune"], remote_ok=True)
    jobs = [_job("Backend Engineer", "Bengaluru, KA, IN"), _job("Backend Engineer", "Pune"),
            _job("Backend Engineer", "Remote - Worldwide"), _job("Backend Engineer", "Remote - APAC"),
            _job("Backend Engineer", "Remote - USA Only"), _job("Backend Engineer", "San Francisco, CA, US"),
            _job("Backend Engineer", "London, UK"), _job("Backend Engineer", "Hyderabad, India"),
            _job("Backend Engineer", "")]
    kept = {j.location for j in rank_jobs(jobs, profile)}
    assert kept == {"Bengaluru, KA, IN", "Pune", "Remote - Worldwide", "Remote - APAC"}


def test_remote_toggle_off_drops_remote_roles():
    profile = UserProfile(skills=["Python", "FastAPI"], titles=["Backend Engineer"], preferred_locations=["Pune"],
                          remote_ok=False)
    kept = {j.location for j in rank_jobs([_job("Backend Engineer", "Pune"), _job("Backend Engineer", "Remote")],
                                          profile)}
    assert kept == {"Pune"}


def test_profile_city_is_the_default_preference_so_far_away_jobs_never_show():
    profile = UserProfile(skills=["Python", "FastAPI"], titles=["Backend Engineer"], location="Pune, India")
    assert profile.effective_locations() == ["Pune, India"]
    kept = {j.location for j in rank_jobs([_job("Backend Engineer", "Pune"), _job("Backend Engineer", "Berlin")],
                                          profile)}
    assert kept == {"Pune"}


def test_location_reason_is_shown_on_the_card():
    profile = UserProfile(skills=["Python", "FastAPI"], titles=["Backend Engineer"], preferred_locations=["Pune"])
    job = rank_jobs([_job("Backend Engineer", "Pune")], profile)[0]
    assert job.match_reasons[0] == "In Pune"


def test_changing_location_preferences_changes_the_cache_key():
    a = UserProfile(skills=["Python"], preferred_locations=["Pune"])
    b = UserProfile(skills=["Python"], preferred_locations=["Mumbai"])
    c = UserProfile(skills=["Python"], preferred_locations=["Pune"], remote_ok=False)
    assert len({a.fingerprint(), b.fingerprint(), c.fingerprint()}) == 3


def test_hn_header_never_takes_full_time_or_pay_as_the_role():
    h = src.parse_hn_hiring_comment("Acme | Full-time | $150k | Visa sponsorship | Bangalore\nWe build things for you")
    assert h["role"] == "Software Engineer" and h["location"] == "Bangalore"


def test_thin_pool_is_topped_up_with_labelled_near_matches():
    profile = UserProfile(skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Redis"],
                          titles=["Backend Engineer"], years=4, preferred_locations=["Pune"])
    strong = _job("Backend Engineer", "Pune")
    near = JobListing("Software Developer", "Near Co", "Pune", "https://x.test/near", "x", [],
                      "We use Python, FastAPI, Docker and AWS daily.", None)      # scores ~56: below 60, above the floor
    weak = JobListing("Recruiter", "Weak Co", "Pune", "https://x.test/weak", "x", [], "Hiring people.", None)
    out = rank_jobs([strong, near, weak], profile)
    assert [j.company for j in out][0] == "Co Pune"
    assert near in out and weak not in out                 # near match fills in, a poor one never does
    assert "Partial match" in near.match_reasons and "Partial match" not in strong.match_reasons


async def test_location_preferences_save_load_and_change_the_profile(client):
    from app.db.database import AsyncSessionLocal
    from app.services.job_recommendations import load_user_profile
    from tests.conftest import unique_email
    from tests.test_metabase_experience import bearer, register
    import uuid

    h = bearer(await register(client, unique_email()))
    base = {"full_name": "Pat", "email": "pat@atsready-tests.dev", "location": "Pune, India"}
    r = await client.post("/api/metabase/personal", headers=h,
                          json={**base, "preferred_locations": [" Bangalore ", "", "Pune"], "remote_ok": False})
    assert r.status_code == 200
    saved = (await client.get("/api/metabase/personal", headers=h)).json()
    assert saved["preferred_locations"] == ["Bangalore", "Pune"] and saved["remote_ok"] is False

    uid = uuid.UUID((await client.get("/api/auth/me", headers=h)).json()["id"])
    async with AsyncSessionLocal() as db:
        p = await load_user_profile(uid, db)
    assert p.preferred_locations == ["Bangalore", "Pune"] and p.remote_ok is False

    # A later save that does not mention the preferences (e.g. a resume import) keeps them.
    await client.post("/api/metabase/personal", headers=h, json={**base, "phone": "123"})
    again = (await client.get("/api/metabase/personal", headers=h)).json()
    assert again["preferred_locations"] == ["Bangalore", "Pune"] and again["remote_ok"] is False
    assert (await client.post("/api/metabase/personal", headers=h,
                              json={**base, "preferred_locations": ["x"] * 11})).status_code == 422
