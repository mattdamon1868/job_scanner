from generic_scraper import detect, extract_jobs

BASE_URL = "https://example.com/careers"

JOB_LISTING_HTML = """
<html><body>
<nav>
  <a class="nav-link" href="/about">About</a>
  <a class="nav-link" href="/contact">Contact</a>
</nav>
<div class="jobs-list">
  <div class="job-card">
    <a class="job-card__link" href="/jobs/1">
      <h3 class="job-card__title">Robotics Engineer</h3>
    </a>
    <span class="job-card__location">Austin, TX</span>
  </div>
  <div class="job-card">
    <a class="job-card__link" href="/jobs/2">
      <h3 class="job-card__title">Autonomy Engineer</h3>
    </a>
    <span class="job-card__location">Remote</span>
  </div>
  <div class="job-card">
    <a class="job-card__link" href="/jobs/3">
      <h3 class="job-card__title">Perception Engineer</h3>
    </a>
    <span class="job-card__location">Austin, TX</span>
  </div>
</div>
</body></html>
"""


def test_detect_finds_job_listing_pattern():
    d = detect(JOB_LISTING_HTML, BASE_URL)
    assert d is not None
    assert d.item_selector == "div.job-card"
    assert d.title_selector == "h3.job-card__title"
    assert d.location_selector == "span.job-card__location"
    assert d.count == 3


def test_detect_ignores_nav_links():
    d = detect(JOB_LISTING_HTML, BASE_URL)
    titles = [job["title"] for job in d.sample]
    assert "About" not in titles
    assert "Contact" not in titles


def test_extract_jobs_uses_detected_selectors():
    d = detect(JOB_LISTING_HTML, BASE_URL)
    jobs = extract_jobs(JOB_LISTING_HTML, BASE_URL, d.item_selector, d.title_selector, d.location_selector)
    assert len(jobs) == 3
    assert jobs[0]["title"] == "Robotics Engineer"
    assert jobs[0]["location"] == "Austin, TX"
    assert jobs[0]["url"] == "https://example.com/jobs/1"
    assert jobs[1]["location"] == "Remote"


def test_detect_returns_none_with_no_repeated_pattern():
    html = "<html><body><p>Nothing here but a single paragraph.</p></body></html>"
    assert detect(html, BASE_URL) is None


PAGINATION_NEARBY_HTML = """
<html><body>
<main>
  <section class="careers">
    <div class="layout">
      <div class="sidebar">filters</div>
      <div class="results-wrapper">
        <div class="jobs-list">
          <div class="job-card"><a href="/jobs/1"><h3 class="job-card__title">Robotics Engineer</h3></a></div>
          <div class="job-card"><a href="/jobs/2"><h3 class="job-card__title">Autonomy Engineer</h3></a></div>
          <div class="job-card"><a href="/jobs/3"><h3 class="job-card__title">Perception Engineer</h3></a></div>
        </div>
        <button aria-label="Next jobs" class="pagination-next">Next</button>
      </div>
    </div>
  </section>
</main>
</body></html>
"""


def test_detect_pagination_finds_nearby_next_button():
    d = detect(PAGINATION_NEARBY_HTML, BASE_URL)
    assert d.pagination_hint is not None
    assert "next jobs" in d.pagination_hint.lower()


UNRELATED_CAROUSEL_HTML = """
<html><body>
<div class="hero-section">
  <div class="hero-inner">
    <div class="carousel-wrapper">
      <button aria-label="Next slide">Next</button>
    </div>
  </div>
</div>
<main>
  <section class="careers">
    <div class="layout">
      <div class="sidebar">filters</div>
      <div class="results-wrapper">
        <div class="jobs-list">
          <div class="job-card"><a href="/jobs/1"><h3 class="job-card__title">Robotics Engineer</h3></a></div>
          <div class="job-card"><a href="/jobs/2"><h3 class="job-card__title">Autonomy Engineer</h3></a></div>
          <div class="job-card"><a href="/jobs/3"><h3 class="job-card__title">Perception Engineer</h3></a></div>
        </div>
      </div>
    </div>
  </section>
</main>
</body></html>
"""


def test_detect_pagination_ignores_unrelated_carousel():
    d = detect(UNRELATED_CAROUSEL_HTML, BASE_URL)
    assert d.pagination_hint is None
