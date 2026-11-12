"""
JD Scraper Service
------------------
Fetches job description pages from user-supplied URLs.

Because the URL comes from the user, every request goes through an SSRF guard:
http/https on ports 80/443 only, and the host must resolve to PUBLIC addresses
only (no loopback, private, link-local/cloud-metadata ranges). Redirects are
followed manually so each hop is checked again.

Extraction order (most reliable first):
  1. schema.org JobPosting JSON-LD   (most job pages embed it for Google Jobs)
  2. public Greenhouse / Lever JSON APIs
  3. __NEXT_DATA__ blobs
  4. per-site CSS selectors
  5. densest text block heuristic, then body text
"""
import asyncio
import html as html_lib
import ipaddress
import json
import logging
import re
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

# Common ATS / job board domains and their content selectors
SITE_SELECTORS = {
    "linkedin.com":      ["div.jobs-description__content", "div.description__text"],
    "greenhouse.io":     ["div#content", "div.job-post"],
    "lever.co":          ["div.posting-page", "div.section-wrapper"],
    "workday.com":       ["div[data-automation-id='jobPostingDescription']"],
    "jobvite.com":       ["div.jv-job-detail-description"],
    "icims.com":         ["div#jobDescriptionText", "div.jd-desc"],
    "indeed.com":        ["div#jobDescriptionText", "div.jobsearch-jobDescriptionText"],
    "glassdoor.com":     ["div.jobDescriptionContent", "div[class*='JobDetails']"],
    "wellfound.com":     ["div.job-description", "section.description"],
    "naukri.com":        ["section.styles_job-desc-container", "div.job-description"],
    "monster.com":       ["div.job-description", "section#JobDescription"],
}

# brotli isn't installed, so don't advertise "br" (servers would send bytes
# httpx can't decode).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

MAX_REDIRECTS = 5
ATTEMPTS = 3                       # 1 try + 2 retries on transient failures
ROBOTS_TTL = 3600
ALLOWED_PORTS = {None, 80, 443}
OK_CONTENT_TYPES = ("text/html", "application/xhtml", "application/json", "text/plain")


class ScraperError(Exception):
    pass


class RobotsBlocked(ScraperError):
    pass


# ── SSRF guard ────────────────────────────────────────────────────────────────

async def validate_public_url(url: str) -> str:
    """Return the URL if it is safe to fetch, else raise ScraperError.

    shortcut: DNS is resolved here and again by httpx when it connects, so a
    hostile DNS server could answer differently the second time (rebinding).
    Upgrade to connecting to the validated IP (custom transport) if this
    service ever fetches on behalf of untrusted *and* high-value tenants.
    """
    try:
        p = urlparse(url.strip())
        port = p.port
    except ValueError:
        raise ScraperError("❌ That doesn't look like a valid URL.")
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ScraperError("❌ Only http(s) job URLs are supported.")
    if p.username or p.password:
        raise ScraperError("❌ URLs with embedded credentials are not allowed.")
    if port not in ALLOWED_PORTS:
        raise ScraperError("❌ Only standard web ports (80/443) are allowed.")

    host = p.hostname
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, port or (443 if p.scheme == "https" else 80),
                                        type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ScraperError(f"❌ Could not find the site {host}. Check the URL and try again.")
    addrs = {ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos}
    if not addrs or any(not a.is_global for a in addrs):
        logger.warning("Blocked non-public scrape target: %s -> %s", host, sorted(map(str, addrs)))
        raise ScraperError("❌ That address isn't a public website, so it can't be fetched.")
    return url.strip()


# ── Text helpers ──────────────────────────────────────────────────────────────

_NOISE_LINE = re.compile(
    r"^(accept( all)? cookies?|cookie (settings|preferences)|privacy policy|"
    r"sign in|log in|create (an )?account|skip to (main )?content|share this job)\b",
    re.I,
)


def _html_to_text(fragment: str) -> str:
    return BeautifulSoup(html_lib.unescape(fragment) if "&lt;" in fragment else fragment, "lxml") \
        .get_text(separator="\n", strip=True)


def _clean_text(text: str) -> str:
    """Collapse whitespace; drop SHORT boilerplate lines only (a long line that
    merely mentions 'sign in' is real content and must stay)."""
    lines = [ln.strip() for ln in text.splitlines()]
    kept = [ln for ln in lines if not (len(ln) < 80 and _NOISE_LINE.match(ln))]
    text = "\n".join(kept)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── Extractors (each returns text or "") ──────────────────────────────────────

def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                stack.extend(v for v in node.values() if isinstance(v, (list, dict)))


def extract_jsonld(soup: BeautifulSoup) -> str:
    for node in _iter_jsonld(soup):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "JobPosting" not in types:
            continue
        parts: List[str] = []
        if node.get("title"):
            parts.append(str(node["title"]))
        org = node.get("hiringOrganization")
        if isinstance(org, dict) and org.get("name"):
            parts.append(f"Company: {org['name']}")
        if node.get("employmentType"):
            parts.append(f"Employment type: {node['employmentType']}")
        loc = node.get("jobLocation")
        loc = loc[0] if isinstance(loc, list) and loc else loc
        addr = loc.get("address") if isinstance(loc, dict) else None
        if isinstance(addr, dict):
            parts.append("Location: " + ", ".join(
                str(addr[k]) for k in ("addressLocality", "addressRegion", "addressCountry") if addr.get(k)))
        for key in ("description", "responsibilities", "qualifications", "skills",
                    "experienceRequirements", "educationRequirements"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(_html_to_text(val))
            elif isinstance(val, list):
                parts.extend(_html_to_text(v) for v in val if isinstance(v, str))
        text = "\n\n".join(p for p in parts if p)
        if len(text) >= 200:
            return text
    return ""


def extract_next_data(soup: BeautifulSoup) -> str:
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        return ""
    try:
        data = json.loads(tag.string or "")
    except (ValueError, TypeError):
        return ""
    best, stack = "", [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and "description" in k.lower() and len(v) > len(best):
                    best = v
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)
    text = _html_to_text(best) if best else ""
    return text if len(text) >= 300 else ""


def extract_selectors(soup: BeautifulSoup, domain: str) -> str:
    for known, selectors in SITE_SELECTORS.items():
        if known in domain:
            for sel in selectors:
                el = soup.select_one(sel)
                if el:
                    return el.get_text(separator="\n", strip=True)
    return ""


_JD_WORDS = ("responsibilities", "requirements", "qualifications", "experience", "skills")


def extract_densest_block(soup: BeautifulSoup) -> str:
    """The block with the most text per markup element. Picking the LONGEST
    block just returned the outermost wrapper (with all the page chrome)."""
    best_score, best = 0.0, ""
    for tag in soup.find_all(["div", "section", "article", "main"]):
        text = tag.get_text(separator="\n", strip=True)
        if len(text) < 500 or not any(w in text.lower() for w in _JD_WORDS):
            continue
        score = len(text) / (1 + len(tag.find_all(True)))
        if score > best_score:
            best_score, best = score, text
    return best


# Public job-board APIs: structured JSON, no HTML scraping, no bot blocking.
_GREENHOUSE = re.compile(r"^(?:job-)?boards\.greenhouse\.io$|^boards\.eu\.greenhouse\.io$")


def board_api_url(url: str) -> Optional[str]:
    p = urlparse(url)
    parts = [s for s in p.path.split("/") if s]
    slug = r"[A-Za-z0-9_.-]+"
    if _GREENHOUSE.match(p.hostname or "") and len(parts) >= 3 and parts[1] == "jobs" \
            and re.fullmatch(slug, parts[0]) and parts[2].isdigit():
        return f"https://boards-api.greenhouse.io/v1/boards/{parts[0]}/jobs/{parts[2]}"
    if p.hostname == "jobs.lever.co" and len(parts) >= 2 \
            and re.fullmatch(slug, parts[0]) and re.fullmatch(r"[0-9a-f-]{36}", parts[1]):
        return f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}"
    return None


def board_json_to_text(data: Dict[str, Any]) -> str:
    parts = [str(data.get("title") or data.get("text") or "")]
    if isinstance(data.get("company_name"), str):
        parts.append(f"Company: {data['company_name']}")
    loc = data.get("location")
    loc = loc.get("name") if isinstance(loc, dict) else data.get("categories", {}).get("location")
    if loc:
        parts.append(f"Location: {loc}")
    if data.get("content"):                                   # Greenhouse (escaped HTML)
        parts.append(_html_to_text(data["content"]))
    if data.get("descriptionPlain"):                          # Lever
        parts.append(data["descriptionPlain"])
    for lst in data.get("lists", []) or []:                   # Lever sections
        parts.append(f"{lst.get('text', '')}\n" + _html_to_text(lst.get("content", "")))
    if data.get("additionalPlain"):
        parts.append(data["additionalPlain"])
    return "\n\n".join(p for p in parts if p)


# ── Service ───────────────────────────────────────────────────────────────────

class ScraperService:
    def __init__(self):
        self._robots_cache: Dict[str, Tuple[float, Optional[RobotFileParser]]] = {}

    @staticmethod
    def _get_domain(url: str) -> str:
        domain = (urlparse(url).hostname or "").lower()
        return domain[4:] if domain.startswith("www.") else domain

    async def _can_fetch(self, client: httpx.AsyncClient, url: str) -> bool:
        """robots.txt via the async client (the old urllib read blocked the event
        loop with no timeout), cached for an hour."""
        if not settings.RESPECT_ROBOTS_TXT:
            return True
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        cached = self._robots_cache.get(base)
        if cached and time.monotonic() - cached[0] < ROBOTS_TTL:
            rp = cached[1]
        else:
            rp = None
            try:
                r = await client.get(f"{base}/robots.txt", timeout=5)
                if r.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                pass                      # unreadable robots.txt -> assume allowed
            self._robots_cache[base] = (time.monotonic(), rp)
        return True if rp is None else rp.can_fetch("*", url)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> Tuple[str, str, str]:
        """GET with SSRF-checked manual redirects, size cap and transient retries.
        Returns (final_url, content_type, body_text)."""
        last_exc: Optional[Exception] = None
        for attempt in range(ATTEMPTS):
            try:
                return await self._fetch_once(client, url)
            except ScraperError as e:
                if not getattr(e, "transient", False) or attempt == ATTEMPTS - 1:
                    raise
                last_exc = e
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                if attempt == ATTEMPTS - 1:
                    break
            await asyncio.sleep(0.5 * (3 ** attempt))
        if isinstance(last_exc, httpx.TimeoutException):
            raise ScraperError(
                f"❌ Request timed out after {settings.SCRAPE_TIMEOUT}s for {url}. "
                "Please paste the JD text directly.")
        raise ScraperError(f"❌ Could not fetch {url}. Check the URL, or paste the JD text directly.")

    async def _fetch_once(self, client: httpx.AsyncClient, url: str) -> Tuple[str, str, str]:
        for _ in range(MAX_REDIRECTS + 1):
            await validate_public_url(url)
            async with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise ScraperError(f"❌ Bad redirect from {url}")
                    url = urljoin(url, loc)
                    continue
                code = resp.status_code
                if code == 403:
                    raise ScraperError(
                        f"❌ Access denied (403) for {url}. The site is blocking automated requests. "
                        "Please paste the job description text directly.")
                if code == 404:
                    raise ScraperError(f"❌ Page not found (404): {url}")
                if code == 429 or code >= 500:
                    err = ScraperError(f"❌ The site returned HTTP {code} for {url}")
                    err.transient = True          # type: ignore[attr-defined]
                    raise err
                if code >= 400:
                    raise ScraperError(f"❌ HTTP {code} for {url}")

                ctype = resp.headers.get("content-type", "").lower()
                if ctype and not ctype.startswith(OK_CONTENT_TYPES):
                    raise ScraperError(f"❌ {url} is not a web page ({ctype.split(';')[0]}).")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > settings.SCRAPE_MAX_BYTES:
                        break                     # enough for any JD; don't buffer a huge page
                text = bytes(body[: settings.SCRAPE_MAX_BYTES]).decode(resp.encoding or "utf-8", errors="replace")
                return url, ctype, text
        raise ScraperError(f"❌ Too many redirects for {url}")

    async def scrape(self, url: str) -> Tuple[str, str]:
        """
        Scrape a JD page. Returns (job_text, warning_message).
        Raises ScraperError / RobotsBlocked on failure.
        """
        url = await validate_public_url(url)
        warning = ""
        domain = self._get_domain(url)
        if any(s in domain for s in ("linkedin.com", "glassdoor.com", "workday.com")):
            warning = (f"⚠️ {domain} often blocks automated access or needs JavaScript, so results may "
                       "be partial. For best results, paste the JD text directly.")

        async with httpx.AsyncClient(
            headers=HEADERS, timeout=settings.SCRAPE_TIMEOUT, follow_redirects=False,
        ) as client:
            # 1. Public board APIs (no HTML, no robots issue: they are official APIs)
            api = board_api_url(url)
            if api:
                try:
                    _, _, raw = await self._fetch(client, api)
                    text = _clean_text(board_json_to_text(json.loads(raw)))
                    if len(text) >= 200:
                        logger.info("Fetched %d chars from board API for %s", len(text), url)
                        return text, warning
                except (ScraperError, ValueError):
                    logger.info("Board API fetch failed for %s; falling back to the page", url)

            if not await self._can_fetch(client, url):
                raise RobotsBlocked(
                    f"❌ Scraping blocked by robots.txt for {url}. "
                    "Please paste the job description text directly instead.")
            final_url, _, page = await self._fetch(client, url)
            domain = self._get_domain(final_url)

        soup = BeautifulSoup(page, "lxml")
        text = extract_jsonld(soup) or extract_next_data(soup)      # before scripts are dropped
        if not text:
            for tag in soup.find_all(["nav", "footer", "script", "style", "header", "noscript"]):
                tag.decompose()
            text = extract_selectors(soup, domain) or extract_densest_block(soup)
            if not text:
                body = soup.find("body")
                text = body.get_text(separator="\n", strip=True) if body else ""
        text = _clean_text(text)

        if len(text) < 200:
            raise ScraperError(
                f"⚠️ Could not extract meaningful content from {url}. "
                "The page may require JavaScript or login. "
                "Please paste the JD text directly.")

        logger.info("Scraped %d chars from %s", len(text), final_url)
        return text, warning


scraper_service = ScraperService()
