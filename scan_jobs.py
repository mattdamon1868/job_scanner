#!/usr/bin/env python3
"""Scan configured company career pages for keyword-matched, seniority-filtered, or newly posted jobs."""

import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from generic_scraper import extract_jobs, render_html

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
SEEN_FILE = BASE_DIR / "seen_jobs.json"
RESULTS_FILE = BASE_DIR / "results.md"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; robotics-job-scanner/1.0)"}
TIMEOUT = 30


def fetch_greenhouse(company):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['id']}/jobs"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for job in resp.json().get("jobs", []):
        jobs.append({
            "id": f"greenhouse:{job['id']}",
            "title": job.get("title", ""),
            "location": (job.get("location") or {}).get("name", ""),
            "url": job.get("absolute_url", ""),
        })
    return jobs


def fetch_lever(company):
    url = f"https://api.lever.co/v0/postings/{company['id']}?mode=json"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for job in resp.json():
        jobs.append({
            "id": f"lever:{job['id']}",
            "title": job.get("text", ""),
            "location": (job.get("categories") or {}).get("location", ""),
            "url": job.get("hostedUrl", ""),
        })
    return jobs


def fetch_skydio_html(company):
    resp = requests.get(company["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []
    for entry in soup.select("div.job-listings__job"):
        title_el = entry.select_one(".job-listings__title")
        loc_el = entry.select_one(".job-listings__location")
        link_el = entry.select_one("a[href]")
        if not title_el or not link_el:
            continue
        href = urljoin(company["url"], link_el["href"])
        jobs.append({
            "id": f"skydio:{href}",
            "title": title_el.get_text(strip=True),
            "location": loc_el.get_text(strip=True) if loc_el else "",
            "url": href,
        })
    return jobs


def fetch_ashby(company):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company['id']}"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for job in resp.json().get("jobs", []):
        jobs.append({
            "id": f"ashby:{job['id']}",
            "title": job.get("title", ""),
            "location": job.get("location", ""),
            "url": job.get("jobUrl", ""),
        })
    return jobs


def fetch_generic_html(company):
    html = render_html(company["url"])
    return extract_jobs(
        html,
        company["url"],
        company["item_selector"],
        company.get("title_selector"),
        company.get("location_selector"),
    )


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "skydio_html": fetch_skydio_html,
    "generic_html": fetch_generic_html,
}


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def prompt_keywords():
    raw = input(
        "Enter position-type keywords to search for, comma-separated "
        "(e.g. robotics, autonomy, perception, controls): "
    ).strip()
    keywords = [k.strip().lower() for k in raw.split(",") if k.strip()]
    if not keywords:
        print("No keywords entered — defaulting to 'robotics'.")
        keywords = ["robotics"]
    return keywords


def prompt_seniority_keywords(defaults):
    default_str = ", ".join(defaults) if defaults else "none"
    raw = input(
        "Enter seniority-level keywords to filter for, comma-separated "
        "(e.g. senior, staff, principal — or junior, entry level, associate; "
        f"type 'any' for no seniority filter) [{default_str}]: "
    ).strip()
    if not raw:
        return defaults
    if raw.lower() in ("any", "all", "none"):
        return []
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def matched_keyword(title, keywords):
    title_lower = title.lower()
    for kw in keywords:
        if kw in title_lower:
            return kw
    return None


def main():
    settings = load_json(SETTINGS_FILE, {})
    companies = settings.get("companies", [])
    default_seniority_keywords = [k.lower() for k in settings.get("seniority_keywords", [])]

    keywords = prompt_keywords()
    seniority_keywords = prompt_seniority_keywords(default_seniority_keywords)

    first_run = not SEEN_FILE.exists()
    seen_ids = set(load_json(SEEN_FILE, []))

    all_jobs = []
    for company in companies:
        fetcher = FETCHERS.get(company["type"])
        if not fetcher:
            if company["type"] == "pending":
                print(f"[skip] {company['name']}: awaiting a custom parser (run add_company.py results "
                      f"weren't on a supported ATS) — {company.get('url', '')}", file=sys.stderr)
            else:
                print(f"[skip] {company['name']}: unknown type '{company['type']}'", file=sys.stderr)
            continue
        try:
            jobs = fetcher(company)
        except Exception as exc:
            print(f"[error] {company['name']}: {exc}", file=sys.stderr)
            continue
        if company.get("possibly_paginated"):
            print(f"[warn] {company['name']}: this page showed signs of pagination when added "
                  f"only the jobs on that one page load are being scanned, there may be more.", file=sys.stderr)
        for job in jobs:
            job["company"] = company["name"]
            job["positions_url"] = company.get("positions_url", "")
            job["possibly_paginated"] = company.get("possibly_paginated", False)
            all_jobs.append(job)

    matches = []
    for job in all_jobs:
        kw_hit = matched_keyword(job["title"], keywords)
        if not kw_hit:
            continue
        if seniority_keywords:
            seniority_hit = matched_keyword(job["title"], seniority_keywords)
            if not seniority_hit:
                continue
        else:
            seniority_hit = None
        tags = ([seniority_hit.upper()] if seniority_hit else []) + [kw_hit]
        if (not first_run) and job["id"] not in seen_ids:
            tags.insert(0, "NEW")
        job["tags"] = tags
        matches.append(job)

    seniority_label = ", ".join(seniority_keywords) if seniority_keywords else "none (all levels)"
    lines = [
        f"# Job scan results ({len(all_jobs)} total postings checked)\n",
        f"Keywords: {', '.join(keywords)} | Seniority filter: {seniority_label}\n",
    ]
    if first_run:
        lines.append("(First run: baseline saved for future NEW detection.)\n")
    if not matches:
        lines.append("\nNo matching positions found.\n")
    else:
        by_company = {}
        for job in matches:
            by_company.setdefault(job["company"], []).append(job)
        for company_name, jobs in by_company.items():
            positions_url = jobs[0]["positions_url"]
            lines.append(f"\n## {company_name} ({positions_url})\n")
            if jobs[0]["possibly_paginated"]:
                lines.append("(warning: this source showed signs of pagination results below may only "
                              "reflect one page of listings.)\n")
            for job in jobs:
                tag_str = " ".join(f"[{t}]" for t in job["tags"])
                loc = f" {job['location']}" if job["location"] else ""
                lines.append(f"- {tag_str} **{job['title']}**{loc}\n  {job['url']}\n")

    output = "".join(lines)
    print("\n" + output)
    RESULTS_FILE.write_text(output)

    SEEN_FILE.write_text(json.dumps(sorted(job["id"] for job in all_jobs), indent=2))


if __name__ == "__main__":
    main()
