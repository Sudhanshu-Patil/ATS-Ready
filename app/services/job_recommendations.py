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

SCORING (keyword-overlap, no AI cost). Earned / possible points, as a 0-100%:
  - Skills     50 : user skills (with aliases) found in the job text. Jobs with
                    no description (LinkedIn list mode) only get 20, from the title.
  - Title      25 : user's role words vs job title (generic words weigh less)
  - Seniority  10 : from title words, else years of experience
  - Location   15 : remote, or the user's city/country appears in the job location
  An axis with no signal (no user location / no titles) is left out of both sides.

CACHING:
  Key  : job_recs:{user_id}:{profile_hash}  (profile edits change the key)
  TTL  : 7200s (2 hours); empty results are never cached
  Bust : refresh=True, rate-limited to one refetch per REFRESH_COOLDOWN
"""
import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from uuid import UUID

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from app.config import settings
from app.db.models import PersonalInfo, Skill, WorkExperience
from app.services.cache_service import cache_service


def _is_transient(exc: BaseException) -> bool:
    """Network blips / 5xx worth one retry — never 4xx (won't succeed on retry)."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


# One extra attempt, short fixed wait — for the 4 fast free JSON APIs only.
# Deliberately NOT applied to the 3 Apify-backed sources below: each actor
# run already takes 20-60s and the full aggregation runs at ~91s against
# Render's ~100s request ceiling (see _fetch_all_jobs) — retrying one of
# those would risk timing out the whole recommendations endpoint.
_retry_transient = retry(
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(2),
    wait=wait_fixed(0.5),
    reraise=True,
)


@_retry_transient
async def _get_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    r = await client.get(url, **kwargs)
    r.raise_for_status()
    return r

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
CACHE_TTL = 7_200          # 2 hours
MIN_MATCH_SCORE = 60.0     # only show jobs above this threshold
MAX_AGE_DAYS = 30          # drop listings with a known posting date older than this
REFRESH_COOLDOWN = 300     # seconds between forced refetches per user
MAX_RESULTS = 60           # cap the returned list — kept generous (vs. the ~20
                           # actually displayed by default) so the frontend's
                           # location/date/source filters have enough matched
                           # jobs to narrow down instead of filtering an
                           # already-tiny top-20 set down to near nothing
# Skill-overlap ratio denominator cap: matching this many skills earns full
# credit on that axis, regardless of how many skills are on the profile.
# Uncapped, the ratio divides by the user's total skill count, so richer
# profiles (more skills) become mathematically harder to match — backwards.
SKILL_MATCH_CAP = 6
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


# ── Data model ────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    if "<" in text:
        text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


_TRACKING_PARAM = re.compile(r"^(utm_|ref$|refid|source$|gh_src|trk|tracking|fbclid|gclid)", re.I)


def _clean_url(url: str) -> str:
    """Drop tracking query params so the same job isn't listed twice."""
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query) if not _TRACKING_PARAM.match(k)]
        return urlunparse(p._replace(query=urlencode(q), fragment=""))
    except ValueError:
        return url


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
        self.url = _clean_url(url)
        self.source = source
        self.tags = [t.lower().strip() for t in tags if t]
        self.description = _strip_html(description or "")   # plain text, original case
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
            # Lets the "Generate Resume" button send the text itself instead of
            # a LinkedIn/Indeed/Naukri URL the scraper cannot fetch.
            "description":    self.description[:6000],
        }


@dataclass
class UserProfile:
    skills: List[str] = field(default_factory=list)   # best first
    titles: List[str] = field(default_factory=list)   # current/most recent first
    years: Optional[float] = None                     # years of experience
    location: str = ""

    def fingerprint(self) -> str:
        raw = "|".join([",".join(self.skills), ",".join(self.titles),
                        str(self.years), self.location])
        return hashlib.sha1(raw.encode()).hexdigest()[:10]


# ── Scoring ───────────────────────────────────────────────────────────────────

# Applied before stripping punctuation, so "C++" stays distinct from "C".
_TOKEN_FIXES = (
    ("c++", "cpp"), ("c#", "csharp"), ("f#", "fsharp"), ("asp.net", "aspdotnet"),
    (".net", "dotnet"), ("node.js", "nodejs"), ("vue.js", "vuejs"),
    ("next.js", "nextjs"), ("react.js", "reactjs"), ("express.js", "expressjs"),
)


def _normalise(text: str) -> str:
    t = text.lower()
    for a, b in _TOKEN_FIXES:
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9\s]", " ", t)


_ALIAS_GROUPS = [
    {"javascript", "js", "ecmascript"}, {"typescript", "ts"},
    {"postgresql", "postgres", "psql"}, {"kubernetes", "k8s"},
    {"nodejs", "node js", "node"}, {"react", "reactjs", "react js"},
    {"vuejs", "vue js", "vue"}, {"nextjs", "next js"}, {"expressjs", "express js"},
    {"go", "golang"}, {"amazon web services", "aws"},
    {"google cloud", "gcp", "google cloud platform"}, {"machine learning", "ml"},
    {"ci cd", "cicd", "continuous integration"}, {"mongodb", "mongo"},
    {"cpp", "c plus plus"}, {"dotnet", "net core", "dotnet core"},
    {"artificial intelligence", "ai"}, {"natural language processing", "nlp"},
]
# Too short/common to trust in free text: only count them in the title or tags.
_AMBIGUOUS = {"go", "r", "c", "d", "j", "ci", "ai", "ml", "ts", "js", "node"}


@lru_cache(maxsize=2048)
def _skill_variants(skill: str) -> tuple:
    n = _normalise(skill).strip()
    if not n:
        return ()
    out = {n}
    for group in _ALIAS_GROUPS:
        if n in group:
            out |= group
    return tuple(sorted(out))


@lru_cache(maxsize=4096)
def _word_re(term: str) -> "re.Pattern[str]":
    return re.compile(r"\b" + re.escape(term) + r"\b")


def _has(term: str, text: str) -> bool:
    return bool(_word_re(term).search(text))


_GENERIC_TITLE = {"engineer", "developer", "software", "manager", "specialist", "analyst"}
_TITLE_SYN = {"developer": "engineer", "programmer": "engineer", "swe": "engineer",
              "dev": "engineer", "sde": "engineer"}
_TITLE_STOP = {"and", "the", "of", "for", "with", "ii", "iii", "iv"}


def _title_words(title: str) -> set:
    words = set()
    for w in _normalise(title).split():
        if len(w) < 2 or w in _TITLE_STOP or w in SENIOR_WORDS or w in JUNIOR_WORDS:
            continue
        words.add(_TITLE_SYN.get(w, w))
    return words


def _title_similarity(user_title: str, job_title: str) -> float:
    """0-1: specific words (backend, data) count double vs generic ones (engineer)."""
    u, j = _title_words(user_title), _title_words(job_title)
    if not u:
        return 0.0
    weight = lambda ws: sum(1 if w in _GENERIC_TITLE else 2 for w in ws)
    return weight(u & j) / weight(u)


def _infer_seniority(titles: List[str]) -> Optional[str]:
    """'senior' / 'junior' from title words, None when the title doesn't say."""
    words = set(re.findall(r"[a-z]+", " ".join(titles).lower()))
    if words & SENIOR_WORDS:
        return "senior"
    if words & JUNIOR_WORDS:
        return "junior"
    return None


def _level_from_years(years: Optional[float]) -> str:
    if years is None:
        return "mid"
    return "junior" if years < 2 else "mid" if years < 6 else "senior"


def score_job(
    job: JobListing,
    user_skills: List[str],
    user_titles: List[str],
    user_years: Optional[float] = None,
    user_location: str = "",
) -> None:
    """Compute match_score (0-100) and matched_skills in place."""
    head = _normalise(f"{job.title} {' '.join(job.tags)}")
    thin = not job.description and not job.tags
    full = head if thin else f"{head} {_normalise(job.description)}"

    # 1. Skills (50, or 20 when the listing has no description)
    matched = []
    for skill in user_skills:
        for v in _skill_variants(skill):
            haystack = head if v in _AMBIGUOUS else full
            if _has(v, haystack):
                matched.append(skill)
                break
    cap = max(3, min(SKILL_MATCH_CAP, len(user_skills)))
    skill_possible = 20.0 if thin else 50.0
    earned = min(len(matched) / cap, 1.0) * skill_possible
    possible = skill_possible

    # 2. Title (25)
    titles = [t for t in user_titles if t]
    if titles:
        earned += 25.0 * max(_title_similarity(t, job.title) for t in titles)
        possible += 25.0

    # 3. Seniority (10): the title wins, years of experience decide otherwise
    user_level = _infer_seniority(titles) or _level_from_years(user_years)
    job_level = _infer_seniority([job.title])
    if job_level is None:
        earned += 6.0                       # listing doesn't say: neutral
    elif job_level == user_level:
        earned += 10.0
    elif "mid" == user_level:
        earned += 6.0
    possible += 10.0

    # 4. Location (15)
    if user_location.strip():
        loc = _normalise(f"{job.location} {job.title}")
        user_tokens = [t for t in _normalise(user_location).split() if len(t) > 2]
        if "remote" in loc or any(_has(t, loc) for t in user_tokens):
            earned += 15.0
        elif not job.location.strip() or "flexible" in loc:
            earned += 7.0
        possible += 15.0

    job.match_score = min(100.0, 100.0 * earned / possible)
    job.matched_skills = matched


def _age_days(posted_at: Any) -> Optional[float]:
    """Days since posting, or None when the date is unknown/unparseable."""
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(str(posted_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def _dedupe(jobs: List[JobListing]) -> List[JobListing]:
    """Keep the best-scored copy of each job (same title + company, or same URL)."""
    seen: set = set()
    out = []
    for job in sorted(jobs, key=lambda j: j.match_score, reverse=True):
        key = (_normalise(job.title).split(), _normalise(job.company).split())
        key = (" ".join(key[0]), " ".join(key[1])) if key[1] else job.url
        if key in seen:
            continue
        seen.add(key)
        out.append(job)
    return out


# ── Source fetchers ───────────────────────────────────────────────────────────

async def _fetch_remotive(client: httpx.AsyncClient, queries: List[str]) -> List[JobListing]:
    """Remotive public JSON API — no key needed. One search per query."""
    try:
        responses = await asyncio.gather(*(
            _get_with_retry(
                client,
                "https://remotive.com/api/remote-jobs",
                params={"limit": 50, "category": "software-dev", "search": q},
            )
            for q in queries
        ), return_exceptions=True)
        jobs = []
        for resp in responses:
            if isinstance(resp, Exception):
                logger.warning("Remotive query failed: %r", resp)
            else:
                jobs.extend(resp.json().get("jobs", []))
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
        pages = await asyncio.gather(*(
            _get_with_retry(client, "https://www.arbeitnow.com/api/job-board-api",
                            params={"page": n})
            for n in (1, 2)
        ), return_exceptions=True)
        jobs = []
        for resp in pages:
            if not isinstance(resp, Exception):
                jobs.extend(resp.json().get("data", []))
        return [
            JobListing(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("location", "Remote") or "Remote",
                url=j.get("url", ""),
                source="Arbeitnow",
                tags=j.get("tags", []),
                description=j.get("description", ""),
                # created_at is a unix epoch; the frontend date filters need ISO.
                posted_at=(datetime.fromtimestamp(j["created_at"], timezone.utc).isoformat()
                           if isinstance(j.get("created_at"), (int, float)) else None),
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
        pages = await asyncio.gather(*(
            _get_with_retry(client, "https://www.themuse.com/api/public/jobs",
                            params={"page": n, "category": "Engineering"})
            for n in (0, 1)
        ), return_exceptions=True)
        jobs = []
        for resp in pages:
            if not isinstance(resp, Exception):
                jobs.extend(resp.json().get("results", []))
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
        # Latest monthly thread, posted by the "whoishiring" account. Sorted by
        # date (plain /search ranks by relevance and can return an old thread
        # or the "Who wants to be hired?" one).
        search = await _get_with_retry(
            client,
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "tags":        "story,author_whoishiring",
                "query":       "Ask HN: Who is hiring?",
                "hitsPerPage": 5,
            },
        )
        hits = [h for h in search.json().get("hits", [])
                if "who is hiring" in (h.get("title") or "").lower()]
        if not hits:
            return []

        story_id = hits[0].get("objectID")
        if not story_id:
            return []

        # Fetch the story's comments
        story = await _get_with_retry(client, f"https://hn.algolia.com/api/v1/items/{story_id}")
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


async def _apify_run_allowed() -> bool:
    """Global daily budget for Apify runs (they spend the free plan's credit)."""
    r = await cache_service.client()
    if not r:
        return True
    key = f"apify_runs:{datetime.now(timezone.utc):%Y%m%d}"
    try:
        n = await r.incr(key)
        if n == 1:
            await r.expire(key, 90_000)
    except Exception as exc:  # Redis down: don't block recommendations
        logger.warning("Apify cap counter failed: %r", exc)
        return True
    if n > settings.APIFY_DAILY_RUN_CAP:
        logger.warning("Apify daily run cap (%d) reached", settings.APIFY_DAILY_RUN_CAP)
        return False
    return True


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
    if not settings.APIFY_API_TOKEN or not await _apify_run_allowed():
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


async def _fetch_apify_linkedin(client: httpx.AsyncClient, title_query: str, location: str) -> List[JobListing]:
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
    if not settings.APIFY_API_TOKEN or not await _apify_run_allowed():
        return []
    try:
        r = await client.post(
            "https://api.apify.com/v2/actors/forward_dinosaur~linkedin-job-scraper/run-sync-get-dataset-items",
            params={"token": settings.APIFY_API_TOKEN},
            json={
                "query":         title_query,
                "location":      location,
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
            # in list mode. Do NOT tag the listing with the query that found it:
            # that made every result "match" the user's own skills. Such thin
            # listings are scored on title/seniority/location only (score_job).
            desc = item.get("description", "") or ""
            company = item.get("company") or ""
            listings.append(JobListing(
                title=title,
                company="" if company == "N/A" else company,
                location=location,
                url=link,
                source="LinkedIn",
                tags=[],
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
    """Naukri (Indian market jobs), crawled via Apify (see _apify_crawl_html).
    `skill_query` is the user's current role title."""
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
                tags=[],
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


async def _fetch_apify_indeed(client: httpx.AsyncClient, title_query: str, location: str) -> List[JobListing]:
    """Indeed jobs, crawled via Apify (see _apify_crawl_html)."""
    url = f"https://www.indeed.com/jobs?q={quote(title_query, safe='')}&l={quote(location, safe='')}"
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

async def _fetch_all_jobs(profile: UserProfile) -> List[JobListing]:
    """
    Fetch from all sources CONCURRENTLY — including the 3 Apify-backed ones.
    Concurrency is safe because each website-content-crawler run is capped at
    memory=4096 (2×4GB + the LinkedIn actor fit inside the account's 16GB
    actor-memory ceiling that a 402 "actor-memory-limit-exceeded" enforced
    when three uncapped 8GB runs raced). Total wall time is now max(sources),
    not sum — required to stay under Render's ~100s request timeout on the
    first uncached dashboard load.
    """
    title_query = profile.titles[0] if profile.titles else "Software Engineer"
    # Remotive searches by text: try the role and the strongest skill.
    queries = [title_query] + profile.skills[:1]
    location = profile.location or "India"   # default market of the first users

    all_jobs: List[JobListing] = []

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        results = await asyncio.gather(
            _fetch_remotive(client, queries),
            _fetch_arbeitnow(client),
            _fetch_themuse(client),
            _fetch_hn_hiring(client),
            _fetch_apify_linkedin(client, title_query, location),
            _fetch_apify_naukri(client, title_query),
            _fetch_apify_indeed(client, title_query, location),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Source fetch raised exception: %r", r)
    return all_jobs


_PROFICIENCY_RANK = {"expert": 3, "advanced": 2, "intermediate": 1, "beginner": 0}
_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _year(s: Optional[str]) -> int:
    m = _YEAR_RE.search(s or "")
    return int(m.group()) if m else 0


async def load_user_profile(user_id: UUID, db: AsyncSession) -> UserProfile:
    """Skills best-first; roles current-first; years of experience; location."""
    skills = (await db.execute(select(Skill).where(Skill.user_id == user_id))).scalars().all()
    skills = sorted(
        skills,
        key=lambda s: (bool(s.is_primary),
                       _PROFICIENCY_RANK.get((s.proficiency or "").lower(), 1),
                       s.years_experience or 0.0),
        reverse=True,
    )
    exps = (await db.execute(
        select(WorkExperience).where(WorkExperience.user_id == user_id)
    )).scalars().all()
    exps = sorted(exps, key=lambda e: (bool(e.is_current), _year(e.end_date), _year(e.start_date)),
                  reverse=True)
    starts = [y for y in (_year(e.start_date) for e in exps) if y]
    info = (await db.execute(
        select(PersonalInfo).where(PersonalInfo.user_id == user_id)
    )).scalar_one_or_none()
    return UserProfile(
        skills=[str(s.name) for s in skills],
        titles=[str(e.role) for e in exps if e.role],
        years=float(datetime.now().year - min(starts)) if starts else None,
        location=str(info.location) if info and info.location else "",
    )


def rank_jobs(jobs: List[JobListing], profile: UserProfile) -> List[JobListing]:
    """Score, drop stale and weak matches, dedupe, best first."""
    for job in jobs:
        score_job(job, profile.skills, profile.titles, profile.years, profile.location)
    def keep(j: JobListing) -> bool:
        age = _age_days(j.posted_at)          # None = unknown date: keep
        return bool(j.url) and j.match_score >= MIN_MATCH_SCORE and (age is None or age <= MAX_AGE_DAYS)

    return _dedupe([j for j in jobs if keep(j)])


# One fetch per user at a time: a double-click or two tabs share the same run
# instead of each spawning Apify jobs.
_inflight: Dict[str, "asyncio.Future[List[Dict[str, Any]]]"] = {}


async def _compute(cache_key: str, last_key: str, profile: UserProfile) -> List[Dict[str, Any]]:
    all_jobs = await _fetch_all_jobs(profile)
    logger.info("Total jobs fetched across all sources: %d", len(all_jobs))
    result = [j.to_dict() for j in rank_jobs(all_jobs, profile)[:MAX_RESULTS]]
    if result:                      # an outage must not pin an empty list for 2h
        await cache_service.set(cache_key, result, ttl=CACHE_TTL)
    await cache_service.set(last_key, 1, ttl=REFRESH_COOLDOWN)
    return result


async def get_recommendations_for_user(
    user_id: UUID,
    db: AsyncSession,
    refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Main entry point. Returns a list of job dicts sorted by match_score desc.
    Cached per profile version, so editing skills/roles/location (or importing
    a resume) is reflected immediately instead of after the 2h TTL.
    """
    profile = await load_user_profile(user_id, db)
    if not profile.skills:
        logger.info("User %s has no skills — returning empty recommendations", user_id)
        return []

    cache_key = f"job_recs:{user_id}:{profile.fingerprint()}"
    last_key = f"job_recs_last:{user_id}"

    cached = await cache_service.get(cache_key)
    if cached is not None:
        # A forced refresh inside the cooldown is served from cache.
        if not refresh or await cache_service.get(last_key) is not None:
            logger.info("job_recs cache HIT for user %s (%d jobs)", user_id, len(cached))
            return cached

    task = _inflight.get(cache_key)
    if task is None:
        logger.info("Fetching jobs for user %s (skills: %s | titles: %s)",
                    user_id, profile.skills[:5], profile.titles[:2])
        task = asyncio.ensure_future(_compute(cache_key, last_key, profile))
        _inflight[cache_key] = task
        task.add_done_callback(lambda _t: _inflight.pop(cache_key, None))
    return await asyncio.shield(task)
