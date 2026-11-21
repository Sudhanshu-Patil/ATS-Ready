"""Location parsing and the user's location preferences."""
import pytest

from app.services.locations import location_ok, parse_place, split_preferences

INDIA = ["Bangalore", "Pune"]


@pytest.mark.parametrize("loc,cities,countries", [
    ("Bengaluru, KA, IN", {"bangalore"}, {"IN"}),
    ("New York, NY, US / Remote", {"new york"}, {"US"}),
    ("Toronto, ON, CA", {"toronto"}, {"CA"}),
    ("Austin, TX", {"austin"}, {"US"}),
    ("Gurugram, Haryana", {"gurgaon"}, {"IN"}),
    ("Remote (US; CA)", set(), {"US"}),
])
def test_parse_place(loc, cities, countries):
    p = parse_place(loc)
    assert p.cities == cities and countries <= p.countries


def test_remote_and_worldwide_flags():
    assert parse_place("Remote").remote and not parse_place("Remote").countries
    assert parse_place("Anywhere in the world").worldwide
    assert parse_place("Remote - APAC").regions == {"apac"}


@pytest.mark.parametrize("loc,ok", [
    ("Bangalore, India", True), ("Bengaluru, KA, IN", True), ("Pune", True), ("Remote", True),
    ("Worldwide", True), ("Remote - APAC", True), ("India", True),
    ("Remote (US)", False), ("San Francisco, CA, US", False), ("Remote / New York, NY, US", False),
    ("London, UK", False), ("Remote - EMEA", False), ("Remote (US; CA)", False), ("", False),
    ("Hyderabad, India", False),                      # India, but not a preferred city
])
def test_user_in_bangalore_and_pune(loc, ok):
    assert location_ok(loc, INDIA, remote_ok=True)[0] is ok


def test_remote_off_drops_remote_jobs_but_keeps_city_matches():
    assert location_ok("Remote", INDIA, remote_ok=False)[0] is False
    assert location_ok("Worldwide", INDIA, remote_ok=False)[0] is False
    assert location_ok("Pune / Remote", INDIA, remote_ok=False)[0] is True


def test_country_preference_matches_any_city_in_it():
    assert location_ok("Hyderabad, India", ["India"], True)[0] is True
    assert location_ok("Mumbai", ["India"], True)[0] is True
    assert location_ok("Dubai", ["India"], True)[0] is False


def test_metro_area_expansion():
    assert location_ok("Noida", ["Delhi NCR"], True)[0] is True
    assert location_ok("Gurgaon", ["Delhi"], True)[0] is True


def test_no_preferences_means_no_filtering():
    assert location_ok("Anywhere on Mars", [], True)[0] is True
    assert location_ok("Mars", ["Remote"], True)[0] is True        # "Remote" alone is not a place


def test_us_user_is_not_sent_indian_or_european_only_jobs():
    assert location_ok("Remote - US only", ["Austin, TX"], True)[0] is True
    assert location_ok("Remote - EMEA", ["Austin"], True)[0] is False
    assert location_ok("Bangalore", ["Austin"], True)[0] is False


def test_remote_only_sources_may_omit_the_location():
    assert location_ok("", INDIA, True, assume_remote=True)[0] is True
    assert location_ok("", INDIA, True)[0] is False


def test_split_preferences():
    assert split_preferences("Bangalore, Pune; Remote\nIndia") == ["Bangalore", "Pune", "Remote", "India"]


@pytest.mark.parametrize("loc,extra,ok", [
    ("Remote", "Python Developer (US only)", False),
    ("Remote", "Python Developer", True),
    ("Remote", "Developer. Candidates must be located in the United States.", False),
    ("Remote", "Developer. You must be authorized to work in Canada.", False),
    ("Remote", "Developer. Open to candidates anywhere in India.", True),
])
def test_bare_remote_with_a_fence_in_the_text(loc, extra, ok):
    from app.services.locations import restriction_text
    title, _, desc = extra.partition(". ")
    assert location_ok(loc, INDIA, True, extra=f"{title} {restriction_text(desc)}")[0] is ok
