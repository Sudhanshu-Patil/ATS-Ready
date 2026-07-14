"""
app/services/job_recommendations.py
─────────────────────────────────────
Fetches live job listings from multiple sources, scores them against the
user's skills using fast keyword overlap, and caches results in Redis.

SOURCES:
  1. Remotive      — remote tech jobs JSON API (free, no key)
  2. Arbeitnow     — international tech jobs JSON API (free, no key)
  3. The Muse      — curated tech jobs JSON API (free, no key)
  4. HN Who's Hiring — Hacker News monthly thread via Algolia (free, no key)
  5. LinkedIn      — crawled via Apify (see below)
  6. Naukri        — crawled via Apify (see below)
  7. Indeed        — crawled via Apify (see below)

  LinkedIn/Naukri/Indeed all previously used direct HTML scraping via raw
  httpx, which is what actually broke — these sites block naive bot requests
  outright (LinkedIn returned HTTP 999, Naukri 403/blocked). They're now
  crawled through Apify's official, genuinely-free `website-content-crawler`
  actor (apify/website-content-crawler — no pay-per-result/rental fee, only
  Apify's own platform compute, covered by the free plan's $5/month credit),
  which uses a real headless browser + proxy pool to get past that blocking.
  The ORIGINAL CSS selectors for each site still work once the page is
  actually reachable — see _apify_crawl_html() for the two non-obvious
  settings (crawlerType, htmlTransformer) that were required empirically.

  Every purpose-built "LinkedIn/Indeed/Naukri Scraper" actor checked on the
  Apify Store charges a monthly rental or pay-per-result fee — none are
  genuinely free — hence using the generic crawler + custom parsing instead.

  Requires APIFY_API_TOKEN; all three sources degrade to [] gracefully if
  unset, same pattern as every other source in this file.

SCORING (keyword-overlap, no AI cost):
  - Skill match   60% : how many user skills appear in job text
  - Title match   20% : job title words vs user's current role
  - Seniority     20% : junior/mid/senior alignment

CACHING:
  Key  : job_recs:{user_id}
  TTL  : 7200s (2 hours)
  Bust : pass refresh=True to get_recommendations_for_user()
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Skill, WorkExperience
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
CACHE_TTL = 7_200          # 2 hours
MIN_MATCH_SCORE = 35.0     # only show jobs above this threshold
MAX_RESULTS = 60           # cap the returned list — kept generous (vs. the ~20
                           # actually displayed by default) so the frontend's
                           # location/date/source filters have enough matched
                           # jobs to narrow down instead of filtering an
                           # already-tiny top-20 set down to near nothing
# Skill-overlap ratio denominator cap: matching this many skills earns full
# credit on that axis, regardless of how many skills are on the profile.
# Uncapped, the ratio divides by the user's total skill count, so richer
# profiles (more skills) become mathematically harder to match — backwards.
SKILL_MATCH_CAP = 8
REQUEST_TIMEOUT = 10       # seconds per HTTP call
APIFY_TIMEOUT = 180        # Apify actor runs are a live scrape, not a fast JSON
                           # API — needs much more headroom than REQUEST_TIMEOUT.
                           # Apify itself hard-cuts run-sync at 300s.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Seniority keyword buckets for level alignment scoring
SENIOR_WORDS   = {"senior", "sr", "lead", "principal", "staff", "architect", "head", "director"}
JUNIOR_WORDS   = {"junior", "jr", "entry", "associate", "intern", "graduate", "trainee", "fresher"}
MID_WORDS      = {"mid", "intermediate", "engineer", "developer", "analyst", "specialist"}


# ── Data model ────────────────────────────────────────────────────────────────

class JobListing:
    __slots__ = (
        "title", "company", "location", "url", "source",
        "tags", "description", "posted_at",
        "match_score", "matched_skills",
    )

    def __init__(
        self,
        title: str,
        company: str,
        location: str,
        url: str,
        source: str,
        tags: List[str],
        description: str,
        posted_at: Optional[str],
    ):
        self.title = title
        self.company = company
        self.location = location
        self.url = url
        self.source = source
        self.tags = [t.lower().strip() for t in tags if t]
        self.description = description.lower()
        self.posted_at = posted_at
        self.match_score: float = 0.0
        self.matched_skills: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title":          self.title,
            "company":        self.company,
            "location":       self.location,
            "url":            self.url,
            "source":         self.source,
            "tags":           self.tags,
            "posted_at":      self.posted_at,
            "match_score":    round(self.match_score, 1),
            "matched_skills": self.matched_skills,
        }


# ── Scoring ───────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def score_job(job: JobListing, user_skills: List[str], user_titles: List[str]) -> None:
    """
    Compute match_score (0–100) in-place. Three components:
      60% — skill keyword overlap
      20% — job title keyword match
      20% — seniority level alignment
    """
    searchable = f"{job.title} {job.company} {' '.join(job.tags)} {job.description}"
    searchable = _normalise(searchable)

    # 1. Skill overlap (60 pts)
    matched = []
    for skill in user_skills:
        skill_norm = _normalise(skill)
        # check whole-word or tag match
        if re.search(r"\b" + re.escape(skill_norm) + r"\b", searchable):
            matched.append(skill)
    skill_ratio = min(len(matched) / SKILL_MATCH_CAP, 1.0)
    skill_pts = skill_ratio * 60.0

    # 2. Title alignment (20 pts)
    title_norm = _normalise(job.title)
    title_pts = 0.0
    for t in user_titles:
        t_words = _normalise(t).split()
        hits = sum(1 for w in t_words if len(w) > 3 and w in title_norm)
        if hits:
            title_pts = min(20.0, hits * 7.0)
            break

    # 3. Seniority alignment (20 pts)
    # Determine user seniority from their titles
    user_level = _infer_seniority(user_titles)
    job_level  = _infer_seniority([job.title])
    if user_level == job_level:
        seniority_pts = 20.0
    elif user_level == "mid" or job_level == "mid":
        seniority_pts = 12.0   # mid is compatible with either end
    else:
        seniority_pts = 5.0    # senior applying to junior or vice versa

    job.match_score    = min(100.0, skill_pts + title_pts + seniority_pts)
    job.matched_skills = matched


def _infer_seniority(titles: List[str]) -> str:
    combined = " ".join(titles).lower()
    words    = set(combined.split())
    if words & SENIOR_WORDS:
        return "senior"
    if words & JUNIOR_WORDS:
        return "junior"
    return "mid"


# ── Source fetchers ───────────────────────────────────────────────────────────

async def _fetch_remotive(client: httpx.AsyncClient) -> List[JobListing]:
    """Remotive public JSON API — no key needed."""
    try:
        r = await client.get(
            "https://remotive.com/api/remote-jobs",
            params={"limit": 100, "category": "software-dev"},
        )
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        return [
            JobListing(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location="Remote",
                url=j.get("url", ""),
                source="Remotive",
                tags=j.get("tags", []),
                description=j.get("description", ""),
                posted_at=j.get("publication_date"),
            )
            for j in jobs
            if j.get("title") and j.get("url")
        ]
    except Exception as exc:
        logger.warning("Remotive fetch failed: %s", exc)
        return []


async def _fetch_arbeitnow(client: httpx.AsyncClient) -> List[JobListing]:
    """Arbeitnow public JSON API — no key needed."""
    try:
        r = await client.get("https://www.arbeitnow.com/api/job-board-api")
        r.raise_for_status()
        jobs = r.json().get("data", [])
        return [
            JobListing(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("location", "Remote") or "Remote",
                url=j.get("url", ""),
                source="Arbeitnow",
                tags=j.get("tags", []),
                description=j.get("description", ""),
                posted_at=j.get("created_at"),
            )
            for j in jobs
            if j.get("title") and j.get("url")
        ]
    except Exception as exc:
        logger.warning("Arbeitnow fetch failed: %s", exc)
        return []


async def _fetch_themuse(client: httpx.AsyncClient) -> List[JobListing]:
    """The Muse public JSON API — no key needed."""
    try:
        r = await client.get(
            "https://www.themuse.com/api/public/jobs",
            params={"page": 0, "per_page": 100, "category": "Engineering"},
        )
        r.raise_for_status()
        jobs = r.json().get("results", [])
        listings = []
        for j in jobs:
            refs = j.get("refs", {})
            url  = refs.get("landing_page", "")
            if not url:
                continue
            loc_list = j.get("locations", [])
            location = loc_list[0].get("name", "Flexible") if loc_list else "Flexible"
            listings.append(JobListing(
                title=j.get("name", ""),
                company=j.get("company", {}).get("name", ""),
                location=location,
                url=url,
                source="The Muse",
                tags=[],
                description=j.get("contents", ""),
                posted_at=j.get("publication_date"),
            ))
        return listings
    except Exception as exc:
        logger.warning("The Muse fetch failed: %s", exc)
        return []


async def _fetch_hn_hiring(client: httpx.AsyncClient) -> List[JobListing]:
    """
    Hacker News 'Who is Hiring?' monthly thread via Algolia search API.
    Finds the most recent thread, parses top-level comments as job listings.
    """
    try:
        # Find the latest "Ask HN: Who is Hiring?" post
        search = await client.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "tags":       "ask_hn",
                "query":      "Ask HN: Who is hiring",
                "hitsPerPage": 1,
            },
        )
        search.raise_for_status()
        hits = search.json().get("hits", [])
        if not hits:
            return []

        story_id = hits[0].get("objectID")
        if not story_id:
            return []

        # Fetch the story's comments
        story = await client.get(
            f"https://hn.algolia.com/api/v1/items/{story_id}"
        )
        story.raise_for_status()
        children = story.json().get("children", [])[:80]

        listings = []
        for c in children:
            text = c.get("text", "") or ""
            if len(text) < 100:
                continue
            # Strip HTML tags
            clean = BeautifulSoup(text, "html.parser").get_text(separator=" ")
            # First line is usually "Company | Role | Location"
            first_line = clean.strip().split("\n")[0][:200]
            parts = [p.strip() for p in first_line.split("|")]
            title   = parts[1] if len(parts) > 1 else "Software Engineer"
            company = parts[0] if parts else "Unknown"
            location = parts[2] if len(parts) > 2 else "Remote"

            hn_url = f"https://news.ycombinator.com/item?id={c.get('objectID', story_id)}"
            listings.append(JobListing(
                title=title,
                company=company,
                location=location,
                url=hn_url,
                source="HN Hiring",
                tags=[],
                description=clean,
                posted_at=None,
            ))
        return listings
    except Exception as exc:
        logger.warning("HN Hiring fetch failed: %s", exc)
        return []


async def _apify_crawl_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """
    Shared helper: crawl a single URL via Apify's official, genuinely-free
    apify/website-content-crawler actor (no pay-per-result/rental fee — only
    Apify's own platform compute, covered by the free plan's $5/month credit)
    and return the rendered page's raw HTML.

    Two settings matter a lot here, found empirically:
      - crawlerType="playwright:firefox" forces real browser rendering.
        The default "adaptive" mode sometimes falls back to raw HTTP per-site,
        which misses JS-rendered listings (this is what made Naukri/Indeed
        return near-empty HTML during testing).
      - htmlTransformer="none" disables the actor's default "readability"
        content-cleaning, which is tuned for articles/blogs — on a job-listing
        page it was stripping out exactly the elements needed (title links,
        company names), leaving only incidental text like years-of-experience.

    Returns None if APIFY_API_TOKEN is unset, the run times out, or fails —
    callers degrade gracefully, same pattern as every other source here.
    """
    if not settings.APIFY_API_TOKEN:
        return None
    try:
        r = await client.post(
            "https://api.apify.com/v2/actors/apify~website-content-crawler/run-sync-get-dataset-items",
            # memory=4096 caps this run at 4GB (default is 8GB). Two crawler
            # runs + the LinkedIn actor then fit inside the account's 16GB
            # actor-memory ceiling CONCURRENTLY — sequential execution pushed
            # total refresh time past Render's ~100s proxy timeout.
            params={"token": settings.APIFY_API_TOKEN, "memory": 4096},
            json={
                "startUrls": [{"url": url}],
                "maxCrawlPages": 1,
                "crawlerType": "playwright:firefox",
                "htmlTransformer": "none",
                "saveHtml": True,
                "saveMarkdown": False,
            },
            timeout=APIFY_TIMEOUT,
        )
        if r.status_code == 408:
            logger.warning("Apify crawl timed out (>%ds) for %s", APIFY_TIMEOUT, url)
            return None
        r.raise_for_status()
        items = r.json()
        if not items:
            return None
        return items[0].get("html")
    except Exception as exc:
        logger.warning("Apify crawl failed for %s: %s", url, exc)
        return None


async def _fetch_apify_linkedin(client: httpx.AsyncClient, skill_query: str, title_query: str) -> List[JobListing]:
    """
    LinkedIn jobs via the purpose-built forward_dinosaur/linkedin-job-scraper
    actor (free — platform compute only). Unlike the generic HTML crawl used
    for Naukri/Indeed, this returns structured JSON, so no selector fragility
    against LinkedIn's bot-hostile markup.

    Requires a ONE-TIME manual approval in the Apify console (the actor asks
    for full account permissions): if unapproved, the API returns 403 and we
    degrade gracefully like every other source. Approval URL appears in the
    error payload / actor page.

    Input matches the actor's build schema exactly — all fields required
    (verified against build anu3bs1kzhwFd6SgP):
      remote: "1"=on-site "2"=remote "3"=hybrid · contract_type: "F"=full-time
    """
    if not settings.APIFY_API_TOKEN:
        return []
    try:
        r = await client.post(
            "https://api.apify.com/v2/actors/forward_dinosaur~linkedin-job-scraper/run-sync-get-dataset-items",
            params={"token": settings.APIFY_API_TOKEN},
            json={
                "query":         title_query,
                "location":      "India",   # primary market; other sources cover global/remote
                "delay":         200,
                "max_results":   15,        # runtime scales with result count —
                                            # 15 keeps the run well under
                                            # Render's ~100s request ceiling
                "remote":        ["1", "2", "3"],
                "contract_type": ["F"],
                "time_interval": "WEEK",
                "proxyConfiguration": {"useApifyProxy": True},
            },
            timeout=APIFY_TIMEOUT,
        )
        if r.status_code in (403, 408):
            logger.warning("Apify LinkedIn actor unavailable (HTTP %d — %s)",
                           r.status_code,
                           "needs one-time console approval" if r.status_code == 403 else "run timed out")
            return []
        r.raise_for_status()

        listings = []
        for item in r.json():
            title = item.get("title")
            link = item.get("link")
            if not title or not link or title == "N/A":
                continue
            # This actor returns no per-job location, and description is "N/A"
            # in list mode — tag the listing with the skills that FOUND it so
            # keyword scoring has real signal instead of an empty description.
            desc = item.get("description", "") or ""
            company = item.get("company") or ""
            listings.append(JobListing(
                title=title,
                company="" if company == "N/A" else company,
                location="India",
                url=link,
                source="LinkedIn",
                tags=[skill_query],
                description="" if desc == "N/A" else desc,
                # The actor's "date" is the SCRAPE timestamp, not the posting
                # date — passing it through made every LinkedIn job claim
                # "just now" and wrongly pass the "Last 24 hours" filter.
                # None = honest unknown: date-window filters exclude these,
                # "Any time" shows them. Freshness is still bounded by the
                # actor's time_interval=WEEK server-side filter.
                posted_at=None,
            ))
        logger.info("Apify LinkedIn returned %d listings", len(listings))
        return listings
    except Exception as exc:
        # %r not %s — timeout exceptions often stringify to "" and hide the cause
        logger.warning("Apify LinkedIn fetch failed: %r", exc)
        return []


async def _fetch_apify_naukri(client: httpx.AsyncClient, skill_query: str) -> List[JobListing]:
    """Naukri (Indian market jobs), crawled via Apify (see _apify_crawl_html)."""
    # Collapse any run of non-alphanumeric characters to one hyphen — skill
    # names like "CI/CD" or "Node.js" otherwise leak "/" or "." straight into
    # the URL path, silently turning it into a different, invalid nested URL
    # (same bug class as the resume-filename slugify fixed earlier).
    slug = re.sub(r'[^a-z0-9]+', '-', skill_query.lower()).strip('-')[:40]
    url = f"https://www.naukri.com/{slug}-jobs"
    html = await _apify_crawl_html(client, url)
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
        listings = []
        for card in soup.select("div.srp-jobtuple-wrapper")[:30]:
            title_el = card.select_one("a.title")
            comp_el  = card.select_one("a.comp-name")
            loc_el   = card.select_one("span.locWdth")
            if not title_el or not title_el.get("href"):
                continue
            listings.append(JobListing(
                title=title_el.get_text(strip=True),
                company=comp_el.get_text(strip=True) if comp_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "India",
                url=title_el.get("href"),
                source="Naukri",
                tags=[skill_query],
                description=card.get_text(separator=" ", strip=True),
                # Naukri only exposes relative text ("2 days ago"), not a
                # parseable date — left None like other best-effort sources.
                posted_at=None,
            ))
        logger.info("Apify Naukri crawl returned %d listings", len(listings))
        return listings
    except Exception as exc:
        logger.warning("Naukri HTML parse failed: %s", exc)
        return []


async def _fetch_apify_indeed(client: httpx.AsyncClient, skill_query: str) -> List[JobListing]:
    """Indeed jobs, crawled via Apify (see _apify_crawl_html)."""
    url = f"https://www.indeed.com/jobs?q={quote(skill_query, safe='')}&l=remote"
    html = await _apify_crawl_html(client, url)
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
        listings = []
        for card in soup.select("div.job_seen_beacon")[:30]:
            title_el = card.select_one("h2.jobTitle span[title], a.jcs-JobTitle span[title]")
            comp_el  = card.select_one('span[data-testid="company-name"]')
            loc_el   = card.select_one('div[data-testid="text-location"]')
            link_el  = card.select_one("a.jcs-JobTitle")
            href = link_el.get("href") if link_el else None
            if not title_el or not href:
                continue
            listings.append(JobListing(
                title=title_el.get_text(strip=True),
                company=comp_el.get_text(strip=True) if comp_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "Remote",
                url=href if href.startswith("http") else f"https://www.indeed.com{href}",
                source="Indeed",
                tags=[],
                description=card.get_text(separator=" ", strip=True),
                posted_at=None,
            ))
        logger.info("Apify Indeed crawl returned %d listings", len(listings))
        return listings
    except Exception as exc:
        logger.warning("Indeed HTML parse failed: %s", exc)
        return []


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def _fetch_all_jobs(skill_query: str, title_query: str = "Software Engineer") -> List[JobListing]:
    """
    Fetch from all sources CONCURRENTLY — including the 3 Apify-backed ones.
    Concurrency is safe because each website-content-crawler run is capped at
    memory=4096 (2×4GB + the LinkedIn actor fit inside the account's 16GB
    actor-memory ceiling that a 402 "actor-memory-limit-exceeded" enforced
    when three uncapped 8GB runs raced). Total wall time is now max(sources),
    not sum — required to stay under Render's ~100s request timeout on the
    first uncached dashboard load.
    """
    all_jobs: List[JobListing] = []

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        results = await asyncio.gather(
            _fetch_remotive(client),
            _fetch_arbeitnow(client),
            _fetch_themuse(client),
            _fetch_hn_hiring(client),
            _fetch_apify_linkedin(client, skill_query, title_query),
            _fetch_apify_naukri(client, skill_query),
            _fetch_apify_indeed(client, skill_query),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Source fetch raised exception: %r", r)

    # De-duplicate by URL
    seen: set = set()
    unique = []
    for job in all_jobs:
        if job.url and job.url not in seen:
            seen.add(job.url)
            unique.append(job)
    return unique


async def get_recommendations_for_user(
    user_id: UUID,
    db: AsyncSession,
    refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Main entry point. Returns a list of job dicts sorted by match_score desc.
    Results are cached in Redis for CACHE_TTL seconds.
    """
    cache_key = f"job_recs:{user_id}"

    # Cache check
    if not refresh:
        cached = await cache_service.get(cache_key)
        if cached is not None:
            logger.info("job_recs cache HIT for user %s (%d jobs)", user_id, len(cached))
            return cached

    # 1. Load user skills from DB
    skills_result = await db.execute(
        select(Skill).where(Skill.user_id == user_id)
    )
    skills: List[Skill] = skills_result.scalars().all()

    if not skills:
        logger.info("User %s has no skills — returning empty recommendations", user_id)
        return []

    skill_names  = [s.name for s in skills]
    # Build a comma-joined query string for scraping fallbacks
    primary_skills = [s.name for s in skills if s.is_primary][:5]
    skill_query  = ", ".join(primary_skills or skill_names[:5])

    # 2. Load user's work experience titles (for title + seniority scoring)
    exp_result = await db.execute(
        select(WorkExperience).where(WorkExperience.user_id == user_id)
    )
    experiences: List[WorkExperience] = exp_result.scalars().all()
    user_titles = [e.role for e in experiences if e.role] or ["Software Engineer"]

    # LinkedIn's search chokes on the comma-joined skill blob (treats it as
    # one phrase → 0 results) — it gets a title-style query instead. The
    # current/most-recent role reads exactly like a LinkedIn search.
    title_query = user_titles[0]

    # 3. Fetch all jobs concurrently
    logger.info("Fetching jobs for user %s (skills: %s | title: %s)",
                user_id, skill_query, title_query)
    all_jobs = await _fetch_all_jobs(skill_query, title_query)
    logger.info("Total jobs fetched across all sources: %d", len(all_jobs))

    # 4. Score and filter
    for job in all_jobs:
        score_job(job, skill_names, user_titles)

    matched = [j for j in all_jobs if j.match_score >= MIN_MATCH_SCORE]
    matched.sort(key=lambda j: j.match_score, reverse=True)
    top = matched[:MAX_RESULTS]

    result = [j.to_dict() for j in top]
    logger.info(
        "Returning %d recommendations for user %s (≥%.0f%% match)",
        len(result), user_id, MIN_MATCH_SCORE,
    )

    # 5. Cache and return
    await cache_service.set(cache_key, result, ttl=CACHE_TTL)
    return result
