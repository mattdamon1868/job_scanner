from add_company import (
    candidates_from_text,
    candidates_from_url,
    guess_name,
    guess_slugs,
    workday_candidates_from_text,
    workday_candidates_from_url,
)


def test_candidates_from_url_greenhouse():
    assert candidates_from_url("https://boards.greenhouse.io/andurilindustries") == [
        ("greenhouse", "andurilindustries")
    ]


def test_candidates_from_url_lever():
    assert candidates_from_url("https://jobs.lever.co/field-ai") == [("lever", "field-ai")]


def test_candidates_from_url_unknown_host_returns_empty():
    assert candidates_from_url("https://www.somecompany.com/careers") == []


def test_candidates_from_text_finds_greenhouse_link():
    html = '<a href="https://boards.greenhouse.io/skildai-careers/jobs/123">Careers</a>'
    assert ("greenhouse", "skildai-careers") in candidates_from_text(html)


def test_candidates_from_text_finds_lever_account_name():
    html = '<script>window.config = {accountName: "field-ai"};</script>'
    assert ("lever", "field-ai") in candidates_from_text(html)


def test_candidates_from_text_no_match_returns_empty_set():
    assert candidates_from_text("<html><body>nothing here</body></html>") == set()


def test_workday_candidates_from_url():
    result = workday_candidates_from_url("https://citjpl.wd5.myworkdayjobs.com/en-US/Jobs")
    assert result == [("workday", "citjpl.wd5.myworkdayjobs.com/Jobs")]


def test_workday_candidates_from_url_no_locale():
    result = workday_candidates_from_url("https://citjpl.wd5.myworkdayjobs.com/Jobs")
    assert result == [("workday", "citjpl.wd5.myworkdayjobs.com/Jobs")]


def test_workday_candidates_from_url_non_workday_host():
    assert workday_candidates_from_url("https://www.jpl.jobs/search-results") == []


def test_workday_candidates_from_text_finds_embedded_link():
    html = '<a href="https://citjpl.wd5.myworkdayjobs.com/en-US/Jobs/userHome">My Applications</a>'
    found = workday_candidates_from_text(html)
    assert ("workday", "citjpl.wd5.myworkdayjobs.com/Jobs") in found


def test_guess_slugs_includes_stem_and_suffixed_variants():
    slugs = guess_slugs("https://www.anduril.com/careers")
    assert "anduril" in slugs
    assert "andurilindustries" in slugs


def test_guess_name_strips_www_and_titlecases():
    assert guess_name("https://www.skild.ai/career") == "Skild"
