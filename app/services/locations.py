"""Location matching for job listings: "is this job somewhere the user is willing to work?"

Job boards write locations in dozens of ways ("Remote (US; CA)", "Bengaluru, KA, IN", "New York, NY, US /
Remote", "EMEA", "Anywhere"). parse_place() reduces a string to cities, countries, regions and a remote flag;
location_ok() applies the user's preferences:

  * Preferences are cities and/or countries the user typed ("Bangalore, Pune, India"), plus remote_ok.
  * An on-site/hybrid job matches when its city is a preferred city, or its country is a preferred country
    (or the listing names only the country the user lives in).
  * A remote job needs remote_ok, and must not be fenced to other places: "Remote (US)" is not for someone in
    India, "Remote - APAC" is. A bare "Remote" or "Worldwide" is open to everyone.
  * Unknown locations are rejected when the user set preferences (a missing location is not a match).

shortcut: the city table covers the large tech hubs only; unknown cities fall back to country words and region
words. Extend CITIES when a hub is missing.
"""
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set, Tuple

# canonical city -> ISO country code
CITIES = {
    # India
    **{c: "IN" for c in (
        "bangalore", "mumbai", "delhi", "noida", "gurgaon", "hyderabad", "pune", "chennai", "kolkata",
        "ahmedabad", "jaipur", "kochi", "indore", "chandigarh", "trivandrum", "coimbatore", "nagpur",
        "vadodara", "surat", "lucknow", "bhubaneswar", "mysore", "visakhapatnam", "mohali", "nashik")},
    # United States
    **{c: "US" for c in (
        "san francisco", "new york", "seattle", "austin", "boston", "los angeles", "chicago", "denver",
        "atlanta", "miami", "san jose", "palo alto", "mountain view", "sunnyvale", "dallas", "houston",
        "portland", "san diego", "washington", "philadelphia", "pittsburgh", "boulder", "salt lake city",
        "raleigh", "nashville", "minneapolis", "brooklyn", "oakland", "menlo park", "redwood city")},
    **{c: "GB" for c in ("london", "manchester", "edinburgh", "cambridge", "bristol", "leeds", "glasgow")},
    **{c: "CA" for c in ("toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo")},
    **{c: "DE" for c in ("berlin", "munich", "hamburg", "frankfurt", "cologne", "stuttgart")},
    "paris": "FR", "amsterdam": "NL", "rotterdam": "NL", "dublin": "IE", "madrid": "ES", "barcelona": "ES",
    "lisbon": "PT", "porto": "PT", "warsaw": "PL", "krakow": "PL", "stockholm": "SE", "copenhagen": "DK",
    "oslo": "NO", "helsinki": "FI", "zurich": "CH", "geneva": "CH", "vienna": "AT", "prague": "CZ",
    "budapest": "HU", "bucharest": "RO", "milan": "IT", "rome": "IT", "brussels": "BE",
    "singapore": "SG", "dubai": "AE", "abu dhabi": "AE", "tel aviv": "IL", "sydney": "AU", "melbourne": "AU",
    "tokyo": "JP", "seoul": "KR", "hong kong": "HK", "shanghai": "CN", "beijing": "CN", "shenzhen": "CN",
    "sao paulo": "BR", "buenos aires": "AR", "mexico city": "MX", "bogota": "CO", "santiago": "CL",
    "lagos": "NG", "nairobi": "KE", "cape town": "ZA", "cairo": "EG", "jakarta": "ID", "manila": "PH",
    "kuala lumpur": "MY", "bangkok": "TH", "ho chi minh city": "VN", "dhaka": "BD", "karachi": "PK",
    "colombo": "LK", "kathmandu": "NP", "istanbul": "TR", "kyiv": "UA", "auckland": "NZ",
}

# spelling variants -> canonical city
CITY_ALIASES = {
    "bengaluru": "bangalore", "bengalooru": "bangalore", "bombay": "mumbai", "new delhi": "delhi",
    "gurugram": "gurgaon", "madras": "chennai", "calcutta": "kolkata", "thiruvananthapuram": "trivandrum",
    "sf": "san francisco", "sfo": "san francisco", "bay area": "san francisco", "nyc": "new york",
    "ny": "new york", "la": "los angeles", "dc": "washington", "munchen": "munich", "koln": "cologne",
    "krakow": "krakow", "sao paulo": "sao paulo", "são paulo": "sao paulo", "zürich": "zurich",
    "bengaluru karnataka": "bangalore", "ncr": "delhi", "delhi ncr": "delhi",
}

# metro areas that stand for several cities: preferring "delhi ncr" should match noida/gurgaon jobs
METRO = {"delhi": {"delhi", "noida", "gurgaon"}, "san francisco": {"san francisco", "oakland", "san jose",
         "palo alto", "mountain view", "sunnyvale", "menlo park", "redwood city"}}

COUNTRIES = {
    "IN": ("india", "indian"), "US": ("united states", "usa", "u.s.", "u.s.a.", "america"),
    "GB": ("united kingdom", "uk", "u.k.", "england", "scotland", "great britain", "britain"),
    "CA": ("canada",), "DE": ("germany", "deutschland"), "FR": ("france",), "NL": ("netherlands", "holland"),
    "IE": ("ireland",), "ES": ("spain",), "PT": ("portugal",), "PL": ("poland",), "SE": ("sweden",),
    "DK": ("denmark",), "NO": ("norway",), "FI": ("finland",), "CH": ("switzerland",), "AT": ("austria",),
    "CZ": ("czechia", "czech republic"), "IT": ("italy",), "BE": ("belgium",), "RO": ("romania",),
    "HU": ("hungary",), "SG": ("singapore",), "AE": ("uae", "united arab emirates"), "IL": ("israel",),
    "AU": ("australia",), "NZ": ("new zealand",), "JP": ("japan",), "KR": ("south korea", "korea"),
    "CN": ("china",), "HK": ("hong kong",), "BR": ("brazil", "brasil"), "AR": ("argentina",),
    "MX": ("mexico",), "CO": ("colombia",), "CL": ("chile",), "NG": ("nigeria",), "KE": ("kenya",),
    "ZA": ("south africa",), "EG": ("egypt",), "ID": ("indonesia",), "PH": ("philippines",),
    "MY": ("malaysia",), "TH": ("thailand",), "VN": ("vietnam",), "BD": ("bangladesh",),
    "PK": ("pakistan",), "LK": ("sri lanka",), "NP": ("nepal",), "TR": ("turkey", "turkiye"), "UA": ("ukraine",),
}
COUNTRY_WORDS = {w: code for code, words in COUNTRIES.items() for w in words}
US_STATES = {"al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky",
             "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd",
             "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc"}

# region word -> countries it covers (for "Remote - APAC" style fences)
REGIONS = {
    "apac": {"IN", "SG", "AU", "NZ", "JP", "KR", "CN", "HK", "ID", "PH", "MY", "TH", "VN", "BD", "PK", "LK", "NP"},
    "asia": {"IN", "SG", "JP", "KR", "CN", "HK", "ID", "PH", "MY", "TH", "VN", "BD", "PK", "LK", "NP", "AE", "IL", "TR"},
    "emea": {"GB", "DE", "FR", "NL", "IE", "ES", "PT", "PL", "SE", "DK", "NO", "FI", "CH", "AT", "CZ", "IT", "BE",
             "RO", "HU", "AE", "IL", "ZA", "NG", "KE", "EG", "TR", "UA"},
    "europe": {"GB", "DE", "FR", "NL", "IE", "ES", "PT", "PL", "SE", "DK", "NO", "FI", "CH", "AT", "CZ", "IT", "BE",
               "RO", "HU", "UA", "TR"},
    "eu": {"DE", "FR", "NL", "IE", "ES", "PT", "PL", "SE", "DK", "FI", "AT", "CZ", "IT", "BE", "RO", "HU"},
    "latam": {"BR", "AR", "MX", "CO", "CL"}, "latin america": {"BR", "AR", "MX", "CO", "CL"},
    "north america": {"US", "CA", "MX"}, "americas": {"US", "CA", "MX", "BR", "AR", "CO", "CL"},
    "africa": {"NG", "KE", "ZA", "EG"}, "middle east": {"AE", "IL", "TR", "EG"}, "oceania": {"AU", "NZ"},
}
WORLDWIDE = ("worldwide", "anywhere", "global", "work from anywhere", "world wide", "any location", "everywhere")
REMOTE_WORDS = ("remote", "work from home", "wfh", "distributed", "telecommute")


# "US only", "US-based", "US residents": the bare word "us" is not a country word, but with one of these it is a fence.
_FENCE_US = re.compile(r"(?<![a-z])(?:us|u s)(?![a-z])[ -]*(?:only|based|residents?|citizens?|candidates|time ?zones?)")
# Sentences in a description that restrict where the person must live or may work.
_FENCE_SENTENCE = re.compile(
    r"(?:must (?:be )?(?:located|based|reside|living|resident)|(?:authori[sz]ed|eligible|legally entitled|right) to work|"
    r"work authori[sz]ation|only (?:accepting|considering) (?:applicants|candidates)|open to candidates)"
    r"[^.\n]{0,80}", re.I)


def restriction_text(description: str) -> str:
    """The location-fence sentences of a job description ('must be located in the US', 'authorized to work in
    Canada'), so a bare 'Remote' job that is really US-only is not shown to someone in India."""
    return " . ".join(m.group(0) for m in _FENCE_SENTENCE.finditer((description or "")[:4000]))[:600]


def _clean(text: str) -> str:
    t = (text or "").lower().replace("&", " and ")
    t = re.sub(r"[()\[\]{}/;|•·\\+]", ",", t)
    t = re.sub(r"[^a-z0-9,.\-\sÀ-ɏ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class Place:
    remote: bool = False
    worldwide: bool = False
    cities: Set[str] = field(default_factory=set)
    countries: Set[str] = field(default_factory=set)        # named or implied by a city
    named_countries: Set[str] = field(default_factory=set)  # written as a country/code
    regions: Set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.remote or self.worldwide or self.cities or self.countries or self.regions)


def _find_cities(text: str) -> Set[str]:
    found: Set[str] = set()
    for alias, canon in CITY_ALIASES.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text):
            found.add(canon)
    for city in CITIES:
        if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", text):
            found.add(city)
    return found


def parse_place(location: str, extra: str = "") -> Place:
    """location is the board's location field; extra is optional text (title, region tags) that may hold
    restrictions such as 'Remote - US only'."""
    place = Place()
    text = _clean(f"{location} {extra}")
    if not text:
        return place
    place.worldwide = any(w in text for w in WORLDWIDE)
    place.remote = place.worldwide or any(w in text for w in REMOTE_WORDS)
    place.cities = _find_cities(text)
    for city in place.cities:
        place.countries.add(CITIES[city])
    for word, code in COUNTRY_WORDS.items():
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text):
            place.countries.add(code)
            place.named_countries.add(code)
    parts = [p.strip(" .") for p in text.split(",") if p.strip(" .")]
    if len(parts) > 1:
        last = parts[-1].upper()
        known_city_countries = {CITIES[c] for c in place.cities}
        if len(last) == 2 and last in COUNTRIES:
            # Many codes are also US states (CA, IN, DE, ID, CO, AR, IL). Read them as a country only when a
            # city we know confirms it ("Toronto, ON, CA", "Bengaluru, KA, IN") or they are not a state ("US", "GB").
            if last not in US_STATES or last in known_city_countries:
                place.countries.add(last)
                place.named_countries.add(last)
        if last.lower() in US_STATES and "US" not in place.named_countries and last not in known_city_countries:
            place.countries.add("US")                       # "Austin, TX": a US state, not a country code
    if _FENCE_US.search(text):
        place.countries.add("US")
        place.named_countries.add("US")
    for region in REGIONS:
        if re.search(rf"(?<![a-z]){re.escape(region)}(?![a-z])", text):
            place.regions.add(region)
    return place


def _prefs(prefs: Iterable[str]) -> Tuple[Set[str], Set[str]]:
    """(cities incl. metro expansion, countries typed by the user)"""
    cities: Set[str] = set()
    typed_countries: Set[str] = set()
    for raw in prefs:
        p = parse_place(raw)
        for c in p.cities:
            cities |= METRO.get(c, {c})
        typed_countries |= p.named_countries
    return cities, typed_countries


def split_preferences(text: str) -> List[str]:
    """'Bangalore, Pune; Remote' -> ['Bangalore', 'Pune', 'Remote']"""
    return [p.strip() for p in re.split(r"[,;\n|]+", text or "") if p.strip()]


def location_ok(
    job_location: str,
    prefs: List[str],
    remote_ok: bool = True,
    extra: str = "",
    assume_remote: bool = False,
) -> Tuple[bool, str]:
    """Return (acceptable, short reason). With no preferences everything is acceptable.
    assume_remote: the source only lists remote jobs, so an empty location means 'Remote'."""
    prefs = [p for p in prefs if p and p.strip().lower() not in ("remote", "anywhere")]
    if not prefs:
        return True, ""
    pref_cities, pref_countries = _prefs(prefs)
    home_countries = pref_countries | {CITIES[c] for c in pref_cities}

    job = parse_place(job_location, extra)
    if job.empty and assume_remote:
        job.remote = True

    onsite_city = job.cities & pref_cities
    if onsite_city:
        return True, f"In {sorted(onsite_city)[0].title()}"
    if job.countries & pref_countries and not (job.remote and job.cities):
        return True, f"In {sorted(job.countries & pref_countries)[0]}"

    if job.remote or job.worldwide:
        if not remote_ok:
            return False, ""
        if job.worldwide:
            return True, "Remote (worldwide)"
        fenced_countries = job.countries
        fenced_regions = job.regions
        if not fenced_countries and not fenced_regions:
            return True, "Remote"
        if fenced_countries & home_countries:
            return True, "Remote (in your country)"
        if any(REGIONS[r] & home_countries for r in fenced_regions):
            return True, "Remote (your region)"
        return False, ""

    # on-site listing that names only the country the user lives in ("India")
    if job.countries & home_countries and not job.cities:
        return True, "In your country"
    return False, ""


def search_locations(prefs: List[str], fallback: str = "") -> List[str]:
    """Places worth searching boards for: the user's cities and countries (original spelling), capped."""
    out = [p for p in prefs if p and p.strip().lower() not in ("remote", "anywhere")]
    if not out and fallback.strip():
        out = [fallback.strip()]
    return out[:3]


def country_of(text: str) -> Optional[str]:
    p = parse_place(text)
    return next(iter(p.countries), None)
