"""Scraper: SSRF guard, redirect handling, caps, and extraction."""
import httpx
import pytest
from bs4 import BeautifulSoup

from app.config import settings
from app.services import scraper as sc
from app.services.scraper import ScraperError, ScraperService, validate_public_url

PUBLIC = "http://93.184.216.34/jobs/1"      # public IP literal: no DNS needed


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/admin", "http://[::1]/", "http://10.1.2.3/",
    "http://192.168.0.10/", "http://169.254.169.254/latest/meta-data/",   # cloud metadata
    "http://100.64.0.1/", "http://0.0.0.0/", "http://127.0.0.1:6379/",
    "ftp://93.184.216.34/", "file:///etc/passwd", "http://user:pw@93.184.216.34/",
    "http://93.184.216.34:8080/", "not a url", "http:///nohost",
])
async def test_blocks_unsafe_urls(url):
    with pytest.raises(ScraperError):
        await validate_public_url(url)


async def test_allows_public_url():
    assert await validate_public_url(PUBLIC) == PUBLIC


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


async def test_redirect_to_private_address_is_blocked():
    def handler(req):
        if req.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        pytest.fail("the private address must never be requested")
    async with client_for(handler) as c:
        with pytest.raises(ScraperError):
            await ScraperService()._fetch(c, PUBLIC)


async def test_follows_safe_redirect():
    def handler(req):
        if req.url.path == "/jobs/1":
            return httpx.Response(301, headers={"location": "/jobs/2"})
        return httpx.Response(200, text="<p>ok</p>", headers={"content-type": "text/html"})
    async with client_for(handler) as c:
        final, _, body = await ScraperService()._fetch(c, PUBLIC)
    assert final.endswith("/jobs/2") and "ok" in body


async def test_redirect_loop_gives_up():
    async with client_for(lambda r: httpx.Response(302, headers={"location": PUBLIC})) as c:
        with pytest.raises(ScraperError, match="redirects"):
            await ScraperService()._fetch(c, PUBLIC)


async def test_non_html_content_type_rejected():
    async with client_for(lambda r: httpx.Response(200, content=b"x", headers={"content-type": "application/pdf"})) as c:
        with pytest.raises(ScraperError, match="not a web page"):
            await ScraperService()._fetch(c, PUBLIC)


async def test_body_is_capped(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_MAX_BYTES", 1000)
    async with client_for(lambda r: httpx.Response(200, content=b"a" * 50_000, headers={"content-type": "text/html"})) as c:
        _, _, body = await ScraperService()._fetch(c, PUBLIC)
    assert len(body) == 1000


async def test_retries_5xx_then_succeeds(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(sc.asyncio, "sleep", no_sleep)
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, text="ok", headers={"content-type": "text/html"})
    async with client_for(handler) as c:
        _, _, body = await ScraperService()._fetch(c, PUBLIC)
    assert body == "ok" and len(calls) == 3


async def test_404_is_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)
    async with client_for(handler) as c:
        with pytest.raises(ScraperError, match="404"):
            await ScraperService()._fetch(c, PUBLIC)
    assert len(calls) == 1


# ── extraction ────────────────────────────────────────────────────────────────

JOB = "Build APIs in Python. " * 20


def soup(html):
    return BeautifulSoup(html, "lxml")


def test_jsonld_jobposting():
    html = ('<html><head><script type="application/ld+json">{"@context":"https://schema.org",'
            '"@type":"JobPosting","title":"Backend Engineer","hiringOrganization":{"name":"Acme"},'
            f'"description":"&lt;p&gt;{JOB}&lt;/p&gt;","jobLocation":{{"address":{{"addressLocality":"Pune"}}}}}}'
            '</script></head><body>nav</body></html>')
    out = sc.extract_jsonld(soup(html))
    assert "Backend Engineer" in out and "Company: Acme" in out and "Location: Pune" in out
    assert "<p>" not in out and "Build APIs in Python." in out


def test_jsonld_in_graph_and_ignores_other_types():
    html = ('<script type="application/ld+json">{"@graph":[{"@type":"Organization","name":"x"},'
            f'{{"@type":"JobPosting","title":"T","description":"{JOB}"}}]}}</script>')
    assert "Build APIs" in sc.extract_jsonld(soup(html))
    assert sc.extract_jsonld(soup('<script type="application/ld+json">{"@type":"Organization"}</script>')) == ""


def test_densest_block_beats_wrapper():
    jd = "<div id='jd'><p>Requirements: " + "Python and SQL experience. " * 30 + "</p></div>"
    chrome = "".join(f"<div><a href='/{i}'>menu item {i}</a><span>x</span></div>" for i in range(60))
    out = sc.extract_densest_block(soup(f"<body><div id='wrap'>{chrome}{jd}</div></body>"))
    assert "Python and SQL" in out and "menu item" not in out


def test_clean_text_keeps_long_lines_mentioning_sign_in():
    real = "Candidates must sign in to the internal portal to complete the onboarding paperwork before day one."
    out = sc._clean_text(f"Sign in\nPrivacy policy\n{real}\nAccept all cookies")
    assert real in out and "Accept all cookies" not in out and not out.startswith("Sign in")


def test_board_api_urls():
    assert sc.board_api_url("https://boards.greenhouse.io/acme/jobs/12345") == \
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs/12345"
    assert sc.board_api_url("https://job-boards.greenhouse.io/acme/jobs/777") == \
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs/777"
    assert sc.board_api_url("https://jobs.lever.co/acme/6d0a6d0a-0000-4000-8000-000000000000") == \
        "https://api.lever.co/v0/postings/acme/6d0a6d0a-0000-4000-8000-000000000000"
    assert sc.board_api_url("https://jobs.lever.co/acme/../../evil") is None
    assert sc.board_api_url("https://example.com/acme/jobs/1") is None


def test_board_json_to_text():
    gh = {"title": "SRE", "company_name": "Acme", "location": {"name": "Remote"},
          "content": "&lt;p&gt;Run &lt;b&gt;Kubernetes&lt;/b&gt;&lt;/p&gt;"}
    out = sc.board_json_to_text(gh)
    assert "SRE" in out and "Run" in out and "Kubernetes" in out and "<" not in out
    lever = {"text": "Dev", "categories": {"location": "Pune"}, "descriptionPlain": "Plain desc",
             "lists": [{"text": "Requirements", "content": "<li>Python</li>"}]}
    out = sc.board_json_to_text(lever)
    assert "Plain desc" in out and "Python" in out and "Location: Pune" in out
