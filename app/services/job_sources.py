"""Job sources beyond the original four, all free and public:

  RemoteOK        remote tech jobs JSON API
  Himalayas       remote jobs JSON API, with per-job country restrictions
  We Work Remotely  RSS feeds (programming categories), with a region per job
  Jobicy          remote jobs JSON API, one search per top skill
  YC Jobs         ycombinator.com/jobs/role/*: the page embeds its postings as JSON (title, location,
                  skills, experience, salary, visa)
  HN Jobs         the official Hacker News API's job stories: YC companies hiring
  HN Who's Hiring the monthly thread: header line "Company | Role | Location | REMOTE" parsed properly
  Web dork search Google Programmable Search (official API, free 100 queries/day, needs GOOGLE_CSE_KEY and
                  GOOGLE_CSE_CX): "<role> <place>" across Greenhouse, Lever, Ashby, Workable, SmartRecruiters

Every fetcher returns [] on any failure and never raises. Location handling stays honest: each source passes
through the board's own location/region text (e.g. "Remote - USA Only") so the user's location filter in
job_recommendations.rank_jobs can reject jobs fenced to other countries.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.cache_service import cache_service
from app.services.job_recommendations import JobListing, _get_with_retry
from app.services.locations import parse_place, search_locations

logger = logging.getLogger(__name__)

SOURCE_UA = {"User-Agent": "Mozilla/5.0 (compatible; ATS-Ready job search; +https://ats-ready.onrender.com)"}


def _iso_from_epoch(value: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _as_list(value: Any) -> List[str]:
    """APIs sometimes send a list, sometimes its string form ("['A', 'B']")."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            return [str(v) for v in json.loads(value.replace("'", '"'))]
        except ValueError:
            return re.findall(r"'([^']+)'", value)
    return [value] if isinstance(value, str) and value else []


# ── Remote boards ────────────────────────────────────────────────────────────

async def fetch_remoteok(client: httpx.AsyncClient) -> List[JobListing]:
    try:
        data = (await _get_with_retry(client, "https://remoteok.com/api", headers=SOURCE_UA)).json()
        out = []
        for j in data:
            if not isinstance(j, dict) or not j.get("position") or not j.get("url"):
                continue                                            # first element is a legal notice
            loc = (j.get("location") or "").strip()
            out.append(JobListing(
                title=j["position"], company=j.get("company", ""),
                location=f"Remote - {loc}" if loc else "Remote", url=j["url"], source="RemoteOK",
                tags=j.get("tags") or [], description=j.get("description", ""), posted_at=j.get("date"),
            ))
        return out
    except Exception as exc:
        logger.warning("RemoteOK fetch failed: %r", exc)
        return []


async def fetch_himalayas(client: httpx.AsyncClient) -> List[JobListing]:
    try:
        pages = await asyncio.gather(*(
            _get_with_retry(client, "https://himalayas.app/jobs/api", params={"limit": 100, "offset": o},
                            headers=SOURCE_UA) for o in (0, 100, 200)), return_exceptions=True)
        out = []
        for resp in pages:
            if isinstance(resp, Exception):
                continue
            for j in resp.json().get("jobs", []):
                restrictions = _as_list(j.get("locationRestrictions"))
                out.append(JobListing(
                    title=j.get("title", ""), company=j.get("companyName", ""),
                    location="Remote - " + ", ".join(restrictions) if restrictions else "Remote (worldwide)",
                    url=j.get("applicationLink") or j.get("guid") or "", source="Himalayas",
                    tags=_as_list(j.get("categories")) + _as_list(j.get("seniority")),
                    description=j.get("description") or j.get("excerpt") or "",
                    posted_at=_iso_from_epoch(j.get("pubDate")),
                ))
        return [j for j in out if j.title and j.url]
    except Exception as exc:
        logger.warning("Himalayas fetch failed: %r", exc)
        return []


WWR_FEEDS = (
    "remote-programming-jobs", "remote-back-end-programming-jobs", "remote-front-end-programming-jobs",
    "remote-full-stack-programming-jobs", "remote-devops-sysadmin-jobs", "remote-data-science-jobs",
)


async def fetch_weworkremotely(client: httpx.AsyncClient) -> List[JobListing]:
    try:
        feeds = await asyncio.gather(*(
            _get_with_retry(client, f"https://weworkremotely.com/categories/{name}.rss", headers=SOURCE_UA)
            for name in WWR_FEEDS), return_exceptions=True)
        out = []
        for resp in feeds:
            if isinstance(resp, Exception):
                continue
            for item in BeautifulSoup(resp.text, "xml").find_all("item"):
                raw_title = (item.title.text if item.title else "").strip()
                company, _, title = raw_title.partition(":")
                if not title:
                    company, title = "", raw_title
                region = (item.find("region").text.strip() if item.find("region") else "")
                out.append(JobListing(
                    title=title.strip(), company=company.strip(),
                    location=f"Remote - {region}" if region else "Remote",
                    url=(item.link.text if item.link else "") or (item.guid.text if item.guid else ""),
                    source="We Work Remotely", tags=[c.text for c in item.find_all("category")],
                    description=item.description.text if item.description else "",
                    posted_at=_rfc822_to_iso(item.pubDate.text if item.pubDate else ""),
                ))
        return [j for j in out if j.title and j.url]
    except Exception as exc:
        logger.warning("We Work Remotely fetch failed: %r", exc)
        return []


def _rfc822_to_iso(text: str) -> Optional[str]:
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


async def fetch_jobicy(client: httpx.AsyncClient, tags: List[str]) -> List[JobListing]:
    try:
        resps = await asyncio.gather(*(
            _get_with_retry(client, "https://jobicy.com/api/v2/remote-jobs", params={"count": 50, "tag": t},
                            headers=SOURCE_UA) for t in (tags[:2] or ["developer"])), return_exceptions=True)
        out = []
        for resp in resps:
            if isinstance(resp, Exception):
                continue
            for j in resp.json().get("jobs", []):
                geo = ", ".join(_as_list(j.get("jobGeo"))) or "Anywhere"
                out.append(JobListing(
                    title=j.get("jobTitle", ""), company=j.get("companyName", ""), location=f"Remote - {geo}",
                    url=j.get("url", ""), source="Jobicy", tags=_as_list(j.get("jobIndustry")) + _as_list(j.get("jobLevel")),
                    description=j.get("jobDescription") or j.get("jobExcerpt") or "", posted_at=j.get("pubDate"),
                ))
        return [j for j in out if j.title and j.url]
    except Exception as exc:
        logger.warning("Jobicy fetch failed: %r", exc)
        return []


# ── YC ───────────────────────────────────────────────────────────────────────

# Words in a user's role -> YC role pages worth reading. software-engineer is always read.
YC_ROLES = {
    "backend": "backend-engineer", "back end": "backend-engineer", "frontend": "frontend-engineer",
    "front end": "frontend-engineer", "full stack": "full-stack-engineer", "fullstack": "full-stack-engineer",
    "machine learning": "machine-learning-engineer", "ml ": "machine-learning-engineer", "data scien": "data-scientist",
    "devops": "devops-engineer", "sre": "devops-engineer", "mobile": "mobile-engineer", "ios": "ios-engineer",
    "android": "android-engineer", "designer": "designer", "product manager": "product-manager",
}


def yc_role_slugs(titles: List[str]) -> List[str]:
    slugs = ["software-engineer"]
    for t in titles[:3]:
        low = f" {t.lower()} "
        for key, slug in YC_ROLES.items():
            if key in low and slug not in slugs:
                slugs.append(slug)
    return slugs[:4]


def _parse_yc_page(html_text: str) -> List[Dict[str, Any]]:
    import html as html_lib
    m = re.search(r'data-page="([^"]+)"', html_text)
    if not m:
        return []
    try:
        return json.loads(html_lib.unescape(m.group(1)))["props"].get("jobPostings") or []
    except (ValueError, KeyError, AttributeError):
        return []


async def fetch_yc_jobs(client: httpx.AsyncClient, titles: List[str]) -> List[JobListing]:
    try:
        pages = await asyncio.gather(*(
            _get_with_retry(client, f"https://www.ycombinator.com/jobs/role/{slug}", headers=SOURCE_UA)
            for slug in yc_role_slugs(titles)), return_exceptions=True)
        seen, out = set(), []
        for resp in pages:
            if isinstance(resp, Exception):
                continue
            for j in _parse_yc_page(resp.text):
                if j.get("id") in seen or not j.get("title") or not j.get("url"):
                    continue
                seen.add(j.get("id"))
                location = j.get("location") or ""
                if "us citizen" in (j.get("visa") or "").lower():      # fenced to US work authorisation
                    location += " (US only)"
                skills = j.get("skills") or []
                facts = [j.get("companyOneLiner"), f"{j.get('roleSpecificType') or j.get('prettyRole') or ''} role",
                         f"Skills: {', '.join(skills)}" if skills else "",
                         f"Experience: {j['minExperience']}" if j.get("minExperience") else "",
                         f"Salary: {j['salaryRange']}" if j.get("salaryRange") else "",
                         f"Equity: {j['equityRange']}" if j.get("equityRange") else ""]
                out.append(JobListing(
                    title=j["title"], company=f"{j.get('companyName', '')} ({j['companyBatchName']})"
                    if j.get("companyBatchName") else j.get("companyName", ""),
                    location=location, url="https://www.ycombinator.com" + j["url"], source="YC Jobs",
                    tags=skills, description=". ".join(f for f in facts if f), posted_at=None,
                ))
        return out
    except Exception as exc:
        logger.warning("YC jobs fetch failed: %r", exc)
        return []


_HN_TITLE = re.compile(r"^(?P<company>.+?)\s*\((?P<batch>YC\s*[A-Z]\d{2}|S\d{2}|W\d{2})\)\s*(?:is\s+)?(?:hiring|looking for)?\s*(?P<role>.*)$",
                       re.I)


def parse_hn_job_title(title: str) -> Dict[str, str]:
    """'Acme (YC W23) is hiring a Senior Backend Engineer in Bangalore' -> company, role, location."""
    m = _HN_TITLE.match(title.strip())
    company, role = (m.group("company").strip(), m.group("role").strip()) if m else ("", title.strip())
    role = re.sub(r"^(an?|to hire|for|our first|founding)\s+", "", role, flags=re.I).strip()
    loc = ""
    lm = re.search(r"\b(?:in|@|based in)\s+([A-Z][\w .,/&-]+?)(?:\s+\(|\s*$|\s+(?:to|who|and)\b)", role)
    paren = re.search(r"\(([^)]*(?:remote|onsite|hybrid|[A-Z]{2,})[^)]*)\)", role, re.I)
    if lm:
        loc = lm.group(1).strip()
    elif paren:
        loc = paren.group(1).strip()
    elif re.search(r"\bremote\b", role, re.I):
        loc = "Remote"
    return {"company": company, "role": role or title.strip(), "location": loc}


async def fetch_hn_jobs(client: httpx.AsyncClient) -> List[JobListing]:
    """Official HN API job stories (YC companies hiring)."""
    base = "https://hacker-news.firebaseio.com/v0"
    try:
        ids = (await _get_with_retry(client, f"{base}/jobstories.json")).json()[:60]
        sem = asyncio.Semaphore(15)

        async def one(i: int):
            async with sem:
                return (await _get_with_retry(client, f"{base}/item/{i}.json")).json()

        items = await asyncio.gather(*(one(i) for i in ids), return_exceptions=True)
        out = []
        for it in items:
            if isinstance(it, Exception) or not isinstance(it, dict) or not it.get("title") or it.get("dead"):
                continue
            parsed = parse_hn_job_title(it["title"])
            out.append(JobListing(
                title=parsed["role"], company=parsed["company"] or "YC startup", location=parsed["location"],
                url=it.get("url") or f"https://news.ycombinator.com/item?id={it['id']}", source="HN Jobs (YC)",
                tags=[], description=f"{it['title']}. {it.get('text') or ''}", posted_at=_iso_from_epoch(it.get("time")),
            ))
        return out
    except Exception as exc:
        logger.warning("HN Jobs fetch failed: %r", exc)
        return []


# ── HN "Who is hiring?" ──────────────────────────────────────────────────────

ROLE_WORDS = re.compile(r"engineer|developer|scientist|designer|manager|analyst|architect|devops|sre|lead|"
                        r"intern|researcher|founder|programmer|full.?stack|back.?end|front.?end", re.I)


def parse_hn_hiring_comment(text: str) -> Optional[Dict[str, str]]:
    """First line is usually 'Company | Role | Location | REMOTE | Salary'. Parts are classified by
    content, not position: a part that parses as a place is the location, one with a role word is the role."""
    first = text.strip().split("\n")[0][:300]
    parts = [p.strip() for p in first.split("|") if p.strip()]
    if len(parts) < 2:
        return None
    company, role, places = parts[0], "", []
    for p in parts[1:]:
        place = parse_place(p)
        if ROLE_WORDS.search(p) and not role and len(p) < 90:
            role = p
        elif not place.empty:
            places.append(p)
        # anything else ("Full-time", "$150k", "Visa sponsorship", "Series A") is neither role nor place
    return {"company": company[:80], "role": role or "Software Engineer", "location": " / ".join(places)}


async def fetch_hn_hiring(client: httpx.AsyncClient) -> List[JobListing]:
    try:
        search = await _get_with_retry(client, "https://hn.algolia.com/api/v1/search_by_date", params={
            "tags": "story,author_whoishiring", "query": "Ask HN: Who is hiring?", "hitsPerPage": 5})
        hits = [h for h in search.json().get("hits", []) if "who is hiring" in (h.get("title") or "").lower()]
        if not hits:
            return []
        story_id = hits[0]["objectID"]
        story = (await _get_with_retry(client, f"https://hn.algolia.com/api/v1/items/{story_id}")).json()
        out = []
        for c in story.get("children", [])[:500]:
            raw = c.get("text") or ""
            if len(raw) < 100:
                continue
            clean = BeautifulSoup(raw, "html.parser").get_text(separator="\n")
            head = parse_hn_hiring_comment(clean)
            if not head:
                continue
            out.append(JobListing(
                title=head["role"], company=head["company"], location=head["location"],
                url=f"https://news.ycombinator.com/item?id={c.get('id') or c.get('objectID') or story_id}",
                source="HN Who's Hiring", tags=[], description=clean, posted_at=c.get("created_at"),
            ))
        return out
    except Exception as exc:
        logger.warning("HN Who's Hiring fetch failed: %r", exc)
        return []


# ── Web dork search (Google Programmable Search) ─────────────────────────────

ATS_SITES = ("boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com",
             "apply.workable.com", "careers.smartrecruiters.com", "jobs.smartrecruiters.com")


def dork_queries(titles: List[str], places: List[str], remote_ok: bool) -> List[str]:
    """Google dorks across the ATS job pages: ("role") ("place") site:a OR site:b ..."""
    sites = " OR ".join(f"site:{s}" for s in ATS_SITES)
    role = (titles[0] if titles else "software engineer").strip()
    where = list(places[:2]) + (["remote"] if remote_ok else [])
    return [f'"{role}" "{w}" ({sites})' for w in where[:3]]


async def _dork_budget_ok(n: int) -> bool:
    """The free tier is 100 queries/day: stop at DORK_DAILY_QUERY_CAP (shared across users)."""
    client = await cache_service.client()
    if client is None:
        return True
    key = f"dork_queries:{datetime.now(timezone.utc):%Y%m%d}"
    try:
        used = await client.incrby(key, n)
        if used == n:
            await client.expire(key, 90_000)
        return used <= settings.DORK_DAILY_QUERY_CAP
    except Exception:
        return True


def _company_from_url(url: str) -> str:
    parts = [p for p in re.sub(r"^https?://[^/]+/", "", url).split("/") if p]
    return parts[0].replace("-", " ").title() if parts else ""


async def fetch_web_dork(client: httpx.AsyncClient, titles: List[str], places: List[str], remote_ok: bool) -> List[JobListing]:
    if not (settings.GOOGLE_CSE_KEY and settings.GOOGLE_CSE_CX):
        return []
    queries = dork_queries(titles, places, remote_ok)
    if not await _dork_budget_ok(len(queries)):
        logger.warning("Dork search daily cap reached")
        return []
    try:
        resps = await asyncio.gather(*(client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": settings.GOOGLE_CSE_KEY, "cx": settings.GOOGLE_CSE_CX, "q": q, "num": 10,
                    "dateRestrict": "m1"}) for q in queries), return_exceptions=True)
        seen, out = set(), []
        for resp in resps:
            if isinstance(resp, Exception) or resp.status_code != 200:
                logger.warning("Dork search failed: %s", resp if isinstance(resp, Exception) else resp.status_code)
                continue
            for r in resp.json().get("items", []):
                url = r.get("link", "")
                if url in seen or not url:
                    continue
                seen.add(url)
                title = re.sub(r"^(Job Application for|Apply for)\s+", "", r.get("title", ""), flags=re.I)
                title, _, company_in_title = title.partition(" at ")
                snippet = r.get("snippet", "")
                out.append(JobListing(
                    title=title.strip(" -|"), company=(company_in_title or _company_from_url(url)).split(" - ")[0].strip(),
                    location=_location_from_snippet(snippet), url=url, source="Web search", tags=[],
                    description=snippet, posted_at=None))
        return await _enrich_board_jobs(client, out[:12]) + out[12:]
    except Exception as exc:
        logger.warning("Dork search failed: %r", exc)
        return []


def _location_from_snippet(snippet: str) -> str:
    m = re.search(r"(?:Location|Based in|Office)[:\s]+([^.|\n]{3,60})", snippet)
    return m.group(1).strip() if m else ""


async def _enrich_board_jobs(client: httpx.AsyncClient, jobs: List[JobListing]) -> List[JobListing]:
    """Greenhouse and Lever pages have public JSON: fill in the real location and description."""
    from app.services.scraper import board_api_url, board_json_to_text

    async def one(job: JobListing) -> JobListing:
        api = board_api_url(job.url)
        if not api:
            return job
        try:
            data = (await _get_with_retry(client, api)).json()
        except Exception:
            return job
        loc = data.get("location")
        loc = loc.get("name") if isinstance(loc, dict) else (data.get("categories") or {}).get("location")
        if loc:
            job.location = loc
        job.description = board_json_to_text(data) or job.description
        return job

    return list(await asyncio.gather(*(one(j) for j in jobs)))


def search_places(prefs: List[str], fallback: str) -> List[str]:
    return search_locations(prefs, fallback)
