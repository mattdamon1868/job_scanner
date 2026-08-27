from scan_jobs import (
    matched_keyword,
    prompt_company_filter,
    prompt_location_keywords,
    prompt_seniority_keywords,
)


def test_matched_keyword_finds_hit():
    assert matched_keyword("Senior Robotics Engineer", ["robotics", "autonomy"]) == "robotics"


def test_matched_keyword_no_hit():
    assert matched_keyword("Product Manager", ["robotics", "autonomy"]) is None


def test_matched_keyword_case_insensitive():
    assert matched_keyword("SENIOR ROBOTICS ENGINEER", ["robotics"]) == "robotics"


def test_matched_keyword_empty_list():
    assert matched_keyword("Robotics Engineer", []) is None


def test_prompt_seniority_keywords_blank_keeps_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_seniority_keywords(["senior", "staff"]) == ["senior", "staff"]


def test_prompt_seniority_keywords_any_clears_filter(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "any")
    assert prompt_seniority_keywords(["senior", "staff"]) == []


def test_prompt_seniority_keywords_custom_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "junior, new grad")
    assert prompt_seniority_keywords(["senior"]) == ["junior", "new grad"]


def test_prompt_location_keywords_blank_means_any(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_location_keywords() == []


def test_prompt_location_keywords_custom_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "remote, austin")
    assert prompt_location_keywords() == ["remote", "austin"]


SAMPLE_COMPANIES = [
    {"name": "Anduril", "type": "greenhouse"},
    {"name": "Skydio", "type": "skydio_html"},
    {"name": "Skild AI", "type": "greenhouse"},
]


def test_prompt_company_filter_blank_returns_all(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_company_filter(SAMPLE_COMPANIES) == SAMPLE_COMPANIES


def test_prompt_company_filter_partial_match(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "anduril")
    result = prompt_company_filter(SAMPLE_COMPANIES)
    assert [c["name"] for c in result] == ["Anduril"]


def test_prompt_company_filter_matches_case_insensitively(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "SKILD")
    result = prompt_company_filter(SAMPLE_COMPANIES)
    assert [c["name"] for c in result] == ["Skild AI"]


def test_prompt_company_filter_typo_falls_back_to_all(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "nonexistentcompany")
    result = prompt_company_filter(SAMPLE_COMPANIES)
    assert result == SAMPLE_COMPANIES
    assert "no company name matched" in capsys.readouterr().out
