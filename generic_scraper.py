"""ATS-agnostic job listing scraper.

Used as the fallback when a careers page isn't on a known ATS (Greenhouse/
Lever/Ashby): renders the page with a headless browser (so client-side
rendered listings are visible too), then finds the repeated block of markup
that looks like a job listing — without knowing anything about the
underlying platform — and derives CSS selectors for it. Those selectors are
stored in settings.json so later scans don't need to re-detect anything.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; robotics-job-scanner/1.0)"

NEGATIVE_CLASS_HINTS = {
    "nav", "menu", "footer", "header", "social", "cookie", "breadcrumb",
    "pagination", "sidebar", "dropdown", "tab", "tabs", "banner",
}
TITLE_CLASS_HINTS = ("title", "name", "role", "position", "heading")
LOCATION_CLASS_HINTS = ("location", "city", "office", "place", "geo")
JOB_URL_HINT = re.compile(r"/(jobs?|careers?|positions?|openings?|postings?|roles?)/", re.I)

PAGINATION_HINTS = ("pagina", "pager", "load-more", "loadmore", "show-more", "showmore")
NEXT_TEXT_HINTS = ("next", "load more", "show more", "view more", "see more")


@dataclass
class Detection:
    item_selector: str
    title_selector: str | None
    location_selector: str | None
    count: int
    sample: list
    pagination_hint: str | None = None


def render_html(url, wait_ms=2500, timeout_ms=30000):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            browser.close()


def _signature(el):
    classes = el.get("class") or []
    if not classes:
        return None
    return el.name + "." + ".".join(sorted(classes))


def _selector_for(el):
    classes = sorted(el.get("class") or [])
    return el.name + "".join(f".{c}" for c in classes)


def _anchor(el):
    if el.name == "a" and el.has_attr("href"):
        return el
    return el.find("a", href=True)


def _has_negative_hint(signature):
    sig_lower = signature.lower()
    return any(hint in sig_lower for hint in NEGATIVE_CLASS_HINTS)


def _score_group(elements, base_url):
    count = len(elements)
    anchors = [_anchor(el) for el in elements]
    if any(a is None for a in anchors):
        return None

    texts = [el.get_text(" ", strip=True) for el in elements]
    lens = [len(t) for t in texts]
    avg_len = sum(lens) / count
    unique_text_ratio = len(set(texts)) / count

    hrefs = [urljoin(base_url, a["href"]) for a in anchors]
    unique_href_ratio = len(set(hrefs)) / count
    job_hint = any(JOB_URL_HINT.search(href) or re.search(r"\d{3,}", href) for href in hrefs)

    if unique_text_ratio < 0.6 or unique_href_ratio < 0.6:
        return None
    if avg_len < 5 or avg_len > 300:
        return None

    score = min(count, 20)
    score += 10 if job_hint else 0
    score += 5 if 8 <= avg_len <= 150 else -5
    return score


def _find_title_and_location(elements):
    def find_relative(hints, require_unique):
        matches = []
        for el in elements:
            found = None
            for desc in el.find_all(True):
                sig = _signature(desc)
                if sig and any(h in sig.lower() for h in hints):
                    found = desc
                    break
            matches.append(found)
        if any(m is None for m in matches):
            return None
        texts = [m.get_text(strip=True) for m in matches]
        if require_unique and len(set(texts)) / len(texts) < 0.6:
            return None
        return _selector_for(matches[0])

    title = find_relative(TITLE_CLASS_HINTS, require_unique=True)
    location = find_relative(LOCATION_CLASS_HINTS, require_unique=False)
    return title, location


def detect_pagination(soup, near):
    """Best-effort check for a 'next page' / 'load more' control near the job listing.

    Scoped to an ancestor of the listing container (rather than the whole page) so an
    unrelated 'next' control elsewhere on the page an image carousel, a blog widget
    doesn't get mistaken for job-list pagination.
    """
    if soup.find("link", attrs={"rel": "next"}):
        return 'a rel="next" link was found in the page head'
    for el in near.find_all(["a", "button"]):
        if el.has_attr("disabled"):
            continue
        classes = " ".join(el.get("class") or []).lower()
        if "disabled" in classes:
            continue
        aria = (el.get("aria-label") or "").lower()
        text = el.get_text(strip=True).lower()
        combined = f"{classes} {aria} {text}"
        if any(h in combined for h in PAGINATION_HINTS + NEXT_TEXT_HINTS):
            label = aria or text or classes
            return f"found what looks like a pagination control: '{label.strip()}'"
    return None


def detect(html, base_url):
    """Find the best repeated job-listing-like block in html. Returns a Detection or None."""
    soup = BeautifulSoup(html, "html.parser")

    groups = {}
    for el in soup.find_all(True):
        parent = el.parent
        if parent is None:
            continue
        sig = _signature(el)
        if not sig or _has_negative_hint(sig):
            continue
        groups.setdefault((id(parent), sig), []).append(el)

    best = None
    best_score = 0
    for elements in groups.values():
        if len(elements) < 2:
            continue
        score = _score_group(elements, base_url)
        if score is not None and score > best_score:
            best_score = score
            best = elements

    if best is None:
        return None

    item_selector = _selector_for(best[0])
    title_selector, location_selector = _find_title_and_location(best)

    sample = []
    for el in best[:3]:
        a = _anchor(el)
        title_el = el.select_one(title_selector) if title_selector else None
        loc_el = el.select_one(location_selector) if location_selector else None
        sample.append({
            "title": (title_el.get_text(strip=True) if title_el else a.get_text(strip=True)),
            "location": loc_el.get_text(strip=True) if loc_el else "",
            "url": urljoin(base_url, a["href"]),
        })

    scope = best[0].parent
    for _ in range(3):
        if scope.parent is None:
            break
        scope = scope.parent

    return Detection(
        item_selector=item_selector,
        title_selector=title_selector,
        location_selector=location_selector,
        count=len(best),
        sample=sample,
        pagination_hint=detect_pagination(soup, scope),
    )


def extract_jobs(html, base_url, item_selector, title_selector, location_selector):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for entry in soup.select(item_selector):
        a = _anchor(entry)
        if not a:
            continue
        href = urljoin(base_url, a["href"])
        title_el = entry.select_one(title_selector) if title_selector else None
        title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
        if not title:
            continue
        loc_el = entry.select_one(location_selector) if location_selector else None
        jobs.append({
            "id": f"generic:{href}",
            "title": title,
            "location": loc_el.get_text(strip=True) if loc_el else "",
            "url": href,
        })
    return jobs
