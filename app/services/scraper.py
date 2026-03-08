"""
JD Scraper Service
------------------
Fetches and parses job description pages from URLs.
Handles robots.txt, anti-scraping headers, and multiple JD site formats.
"""
import re
import time
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse
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

# Aggressive user agent rotation
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class ScraperError(Exception):
    pass


class RobotsBlocked(ScraperError):
    pass


class ScraperService:
    def __init__(self):
        self._robots_cache: dict = {}

    def _can_fetch(self, url: str) -> bool:
        """Check if scraping is allowed via robots.txt."""
        if not settings.RESPECT_ROBOTS_TXT:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base}/robots.txt"

        if base not in self._robots_cache:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self._robots_cache[base] = rp
            except Exception:
                self._robots_cache[base] = None

        rp = self._robots_cache.get(base)
        if rp is None:
            return True  # can't read robots.txt → assume allowed
        return rp.can_fetch("*", url)

    def _get_domain(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # strip www.
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    def _extract_text(self, soup: BeautifulSoup, domain: str) -> str:
        """Try domain-specific selectors first, then fallback to heuristics."""
        for known_domain, selectors in SITE_SELECTORS.items():
            if known_domain in domain:
                for sel in selectors:
                    el = soup.select_one(sel)
                    if el:
                        return el.get_text(separator="\n", strip=True)

        # Heuristic: look for large text blocks with job-like content
        candidates = []
        for tag in soup.find_all(["div", "section", "article", "main"]):
            text = tag.get_text(separator=" ", strip=True)
            if len(text) > 500 and any(
                kw in text.lower() for kw in
                ["responsibilities", "requirements", "qualifications", "experience", "skills"]
            ):
                candidates.append((len(text), text))

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

        # Last resort: body text
        body = soup.find("body")
        return body.get_text(separator="\n", strip=True) if body else ""

    def _clean_text(self, text: str) -> str:
        """Remove excess whitespace and noise."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        # Remove cookie/navigation noise
        noise_patterns = [
            r"accept (all )?cookies?.*",
            r"privacy policy.*",
            r"sign in.*",
            r"create account.*",
        ]
        for pat in noise_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)
        return text.strip()

    async def scrape(self, url: str) -> Tuple[str, str]:
        """
        Scrape a JD page. Returns (job_text, warning_message).
        Raises ScraperError / RobotsBlocked on failure.
        """
        # robots.txt check
        if not self._can_fetch(url):
            raise RobotsBlocked(
                f"❌ Scraping blocked by robots.txt for {url}. "
                "Please paste the job description text directly instead."
            )

        domain = self._get_domain(url)
        warning = ""

        # Sites known to require JS rendering (can't scrape with httpx)
        js_required_sites = ["linkedin.com", "glassdoor.com", "workday.com"]
        if any(site in domain for site in js_required_sites):
            warning = (
                f"⚠️ {domain} typically requires JavaScript rendering. "
                "Attempting basic scrape — results may be partial. "
                "For best results, paste the JD text directly."
            )

        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=settings.SCRAPE_TIMEOUT,
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    raise ScraperError(
                        f"❌ Access denied (403) for {url}. "
                        "The site is blocking automated requests. "
                        "Please paste the job description text directly."
                    )
                elif e.response.status_code == 404:
                    raise ScraperError(f"❌ Page not found (404): {url}")
                else:
                    raise ScraperError(f"❌ HTTP {e.response.status_code} for {url}")
            except httpx.TimeoutException:
                raise ScraperError(
                    f"❌ Request timed out after {settings.SCRAPE_TIMEOUT}s for {url}. "
                    "Please paste the JD text directly."
                )
            except httpx.ConnectError:
                raise ScraperError(
                    f"❌ Could not connect to {url}. Check the URL and try again."
                )

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove nav, footer, script, style noise
        for tag in soup.find_all(["nav", "footer", "script", "style", "header"]):
            tag.decompose()

        text = self._extract_text(soup, domain)
        text = self._clean_text(text)

        if len(text) < 200:
            raise ScraperError(
                f"⚠️ Could not extract meaningful content from {url}. "
                "The page may require JavaScript or login. "
                "Please paste the JD text directly."
            )

        logger.info(f"Scraped {len(text)} chars from {url}")
        return text, warning


scraper_service = ScraperService()
