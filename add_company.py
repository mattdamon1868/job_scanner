#!/usr/bin/env python3
"""Interactively add a company to settings.json from just its careers page URL.

Detects Greenhouse, Lever, or Ashby job boards automatically first by looking
for board links or JS config values embedded in the page, then (if the site
loads its board token via client-side JS and hides it) by trying common name
variations and verifying each against the real public API. Every candidate is
verified against the live API and shown with sample job titles before being
saved, so nothing gets written on a guess alone. Anything not on a supported
ATS is saved as a 'pending' placeholder for a custom parser to be added later.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from generic_scraper import detect as detect_generic, render_html

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; robotics-job-scanner/1.0)"}
TIMEOUT = 30

DEFAULT_SETTINGS = {
    "seniority_keywords": ["senior", "staff", "principal", "lead", "sr."],
    "companies": [],
}

# (ats_type, regex-with-one-capture-group-for-the-slug)
LINK_PATTERNS = [
    ("greenhouse",
    re.compile(r"(?:boards|job-boards|boards-api)\.greenhouse\.io/(?:v1/boards/)?([a-zA-Z0-9_-]+)")),
    ("greenhouse",
    re.compile(r"job_board/js\?for=([a-zA-Z0-9_-]+)")),
    ("lever",
    re.compile(r"(?:jobs|api)\.lever\.co/(?:v0/postings/)?([a-zA-Z0-9_-]+)")),
    ("lever",
    re.compile(r"accountName[\"']?\s*:\s*[\"']([a-zA-Z0-9_-]+)[\"']")),
    ("ashby",
    re.compile(r"(?:jobs|api)\.ashbyhq\.com/(?:posting-api/job-board/)?([a-zA-Z0-9_-]+)")),
]

# generic mention of the ATS domain, used to trigger slug-guessing when no
# slug could be read directly out of the page (site loads it via JS)
ATS_HOST_HINTS = {
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "ashbyhq.com": "ashby",
}

HOST_ATS = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
}


def verify_greenhouse(slug):
    ''' Verify the Greenhouse board token is valid. '''
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                     headers=HEADERS,
                     timeout=TIMEOUT) # get the jobs from the Greenhouse board
    if r.status_code != 200: # if the board token is invalid, return None
        return None
    jobs = r.json().get("jobs")
    if jobs is None: # if the board token is valid, but no jobs are found, return None
        return None
    return {"count": len(jobs), "titles": [j.get("title", "") for j in jobs[:3]]}


def verify_lever(slug):
    r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json",
                     headers=HEADERS,
                     timeout=TIMEOUT) # get the jobs from the Lever board
    if r.status_code != 200:
        return None
    data = r.json()
    if not isinstance(data, list):
        return None
    return {"count": len(data), "titles": [j.get("text", "") for j in data[:3]]}


def verify_ashby(slug):
    r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                    headers=HEADERS,
                    timeout=TIMEOUT) # get the jobs from the Ashby board
    if r.status_code != 200:
        return None
    jobs = r.json().get("jobs")
    if jobs is None:
        return None
    return {"count": len(jobs), "titles": [j.get("title", "") for j in jobs[:3]]}


VERIFIERS = {
    "greenhouse": verify_greenhouse,
    "lever": verify_lever,
    "ashby": verify_ashby,
}


def fetch_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"  (couldn't fetch the page to inspect it: {exc})")
        return None


def candidates_from_url(url):
    """Slug candidates found directly in the URL the user entered."""
    parsed = urlparse(url)
    ats_type = HOST_ATS.get(parsed.netloc.lower())
    if not ats_type:
        return []
    slug = parsed.path.strip("/").split("/")[0]
    return [(ats_type, slug)] if slug else []


def candidates_from_text(html):
    found = set()
    for ats_type, pattern in LINK_PATTERNS:
        for match in pattern.finditer(html):
            found.add((ats_type, match.group(1)))
    return found


def guess_slugs(url):
    host = urlparse(url).netloc.lower().removeprefix("www.")
    stem = host.split(".")[0]
    compact = stem.replace("-", "")
    suffixes = ["", "industries", "-industries", "inc", "tech", "robotics", "ai"]
    variants = set()
    for base in {stem, compact}:
        for suffix in suffixes:
            variants.add(f"{base}{suffix}")
    return sorted(variants)


def guess_name(url):
    host = urlparse(url).netloc.lower().removeprefix("www.")
    stem = host.split(".")[0]
    return stem.replace("-", " ").title()


def load_settings():
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")


def gather_candidates(url):
    """Returns a list of (ats_type, slug, count, titles, source) verified candidates."""
    candidates = set(candidates_from_url(url))
    html = fetch_page(url)
    if html:
        candidates.update(candidates_from_text(html))

    verified = []
    checked = set()
    for ats_type, slug in candidates:
        checked.add((ats_type, slug))
        result = VERIFIERS[ats_type](slug)
        if result:
            verified.append((ats_type, slug, result["count"], result["titles"], "detected"))

    if not verified and html:
        hints = {ats for host, ats in ATS_HOST_HINTS.items() if host in html.lower()}
        if hints:
            print(f"Found a reference to {', '.join(sorted(hints))} but the exact board token isn't in the "
                  f"page's static HTML (it's likely loaded via JavaScript) trying common name variations...")
            for ats_type in hints:
                for slug in guess_slugs(url):
                    if (ats_type, slug) in checked:
                        continue
                    checked.add((ats_type, slug))
                    result = VERIFIERS[ats_type](slug)
                    if result:
                        verified.append((ats_type, slug, result["count"], result["titles"], "guessed"))

    return verified


def main():
    url = input("Enter the careers page URL: ").strip()

    print("Checking for a known job board system...")
    verified = gather_candidates(url)

    if not verified:
        print("No supported job board (Greenhouse/Lever/Ashby) detected on this page.")
        print("Rendering the page with a headless browser to look for a generic listing pattern...")
        detection = None
        try:
            rendered_html = render_html(url)
        except Exception as exc:
            print(f"  (couldn't render the page: {exc})")
            rendered_html = None
        if rendered_html:
            detection = detect_generic(rendered_html, url)

        use_generic = False
        if detection:
            print(f"Found a repeated listing pattern ({detection.count} items matching '{detection.item_selector}'):")
            for job in detection.sample:
                loc = f" {job['location']}" if job["location"] else ""
                print(f"  e.g. {job['title']}{loc}\n     {job['url']}")
            if detection.pagination_hint:
                print(f"  WARNING: {detection.pagination_hint} this page likely only shows a subset of "
                      f"listings. Scans will probably under-report open roles for this company.")
            confirm = input("Use this pattern? [Y/n]: ").strip().lower()
            use_generic = confirm != "n"

        if use_generic:
            default_name = guess_name(url)
            name = input(f"Company display name [{default_name}]: ").strip() or default_name
            entry = {
                "name": name,
                "type": "generic_html",
                "url": url,
                "positions_url": url,
                "item_selector": detection.item_selector,
                "title_selector": detection.title_selector,
                "location_selector": detection.location_selector,
                "possibly_paginated": bool(detection.pagination_hint),
            }
        else:
            if detection:
                print("Discarding the generic pattern it was under review, not saved.")
            name = input("What would you like to call this company? ").strip() or guess_name(url)
            entry = {
                "name": name,
                "type": "pending",
                "url": url,
                "positions_url": url,
                "note": "No supported ATS or reliable generic listing pattern found needs a custom parser added to scan_jobs.py.",
            }
    else:
        if len(verified) > 1:
            print("Found multiple possible job boards on this page:")
            for i, (ats_type, slug, count, titles, source) in enumerate(verified, 1):
                sample = "; ".join(t for t in titles if t) or "no titles available"
                print(f"  {i}. [{source}] {ats_type} '{slug}' ({count} open postings)")
                print(f"     e.g. {sample}")
            choice = input(f"Which one? [1-{len(verified)}]: ").strip()
            index = int(choice) - 1 if choice.isdigit() else 0
            index = index if 0 <= index < len(verified) else 0
            ats_type, slug, count, titles, source = verified[index]
        else:
            ats_type, slug, count, titles, source = verified[0]
            sample = "; ".join(t for t in titles if t) or "no titles available"
            print(f"[{source}] Detected {ats_type.title()} board token '{slug}' ({count} open postings).")
            print(f"  e.g. {sample}")
            confirm = input("Use this? [Y/n]: ").strip().lower()
            if confirm == "n":
                slug = input(f"Enter the correct {ats_type} board token/slug: ").strip()

        default_name = guess_name(url)
        name = input(f"Company display name [{default_name}]: ").strip() or default_name
        entry = {"name": name, "type": ats_type, "id": slug, "positions_url": url}

    settings = load_settings()
    settings.setdefault("companies", [])

    existing_index = next(
        (i for i, c in enumerate(settings["companies"]) if c.get("name", "").lower() == entry["name"].lower()),
        None,
    )
    if existing_index is not None:
        old = settings["companies"][existing_index]
        print(f"'{entry['name']}' already exists (type '{old['type']}').")
        replace = input("Replace it with this new entry? [Y/n]: ").strip().lower()
        if replace == "n":
            print("Kept the existing entry nothing saved.")
            return
        settings["companies"][existing_index] = entry
    else:
        settings["companies"].append(entry)
    save_settings(settings)

    if entry["type"] == "pending":
        print(f"Saved '{entry['name']}' as pending scan_jobs.py will skip it until a parser is added.")
    elif entry["type"] == "generic_html":
        print(f"Saved '{entry['name']}' (generic_html, '{entry['item_selector']}') to settings.json.")
    else:
        print(f"Saved '{entry['name']}' ({entry['type']}, '{entry['id']}') to settings.json.")


if __name__ == "__main__":
    main()
