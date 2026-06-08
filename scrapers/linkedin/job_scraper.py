"""LinkedIn Job Scraper.

Scrapes LinkedIn job search cards and details, normalizes the extracted fields,
and writes them directly to the jobs table.
"""

import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from scrapers.linkedin.cdp_client import CDPClient
from normalizer import normalize_role, extract_experience, extract_location, classify_contact

logger = logging.getLogger(__name__)

DEFAULT_ROLES = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Python Developer",
    "Backend Developer",
    "Full Stack Developer",
    "Generative AI Engineer",
    "LLM Engineer",
    "AI Automation Engineer"
]

class LinkedInJobScraper:
    """Scraper for LinkedIn job search results."""
    
    def __init__(self, cdp: CDPClient, db: Any):
        self.cdp = cdp
        self.db = db

    def _extract_job_id(self, url: str) -> str:
        """Extract LinkedIn job ID from URL."""
        m = re.search(r'/jobs/view/(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'currentJobId=(\d+)', url)
        return m.group(1) if m else ""

    def scrape(self, roles: Optional[List[str]] = None, limit_per_role: int = 15, pages_per_role: int = 2) -> Dict[str, Any]:
        """Scrape structured job listings for the given roles."""
        roles_to_scrape = roles or DEFAULT_ROLES
        total_scraped = 0
        total_new = 0
        per_role = {role: 0 for role in roles_to_scrape}

        logger.info("Starting LinkedIn jobs scraping for %d roles", len(roles_to_scrape))

        for role in roles_to_scrape:
            role_jobs_count = 0
            logger.info("Scraping jobs for role [%s]", role)

            for page in range(pages_per_role):
                if role_jobs_count >= limit_per_role:
                    break

                start = page * 25
                url = (
                    f"https://www.linkedin.com/jobs/search/"
                    f"?keywords={urllib.parse.quote(role)}"
                    f"&location=India"
                    f"&f_TPR=r86400"
                    f"&sortBy=R"
                )
                if page > 0:
                    url += f"&start={start}"

                logger.info("Accessing Page %d: %s", page + 1, url)
                try:
                    self.cdp.navigate(url, wait_seconds=5)
                except Exception as e:
                    logger.error("Failed to navigate to page URL: %s", e)
                    continue

                # Scroll to load job list scaffold finite scroll
                scroll_expr = (
                    "(async function(){"
                    "  for(var i=0; i<5; i++){"
                    "    var el = document.querySelector('.jobs-search-results-list, [class*=\"scaffold-finite-scroll\"]');"
                    "    if(el) el.scrollBy(0, 600);"
                    "    else window.scrollBy(0, 600);"
                    "    await new Promise(r=>setTimeout(r, 1200));"
                    "  }"
                    "  await new Promise(r=>setTimeout(r, 1000));"
                    "  return 'done';"
                    "})()"
                )
                self.cdp.eval_js(scroll_expr, timeout=15, await_promise=True)

                # Extract all job cards
                extract_cards_expr = """
                JSON.stringify([...document.querySelectorAll('[data-occludable-job-id], .job-card-container, .jobs-search-two-pane__job-card-container, .job-card-list__container')].map(function(el){
                    var a = el.querySelector('a[href*="/jobs/view/"], .job-card-list__title, a.job-card-container__link');
                    if(!a) return null;
                    
                    var titleEl = el.querySelector('strong, .job-card-list__title, [class*="title"]');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0].trim() : '';
                    
                    var companyEl = el.querySelector('.job-card-container__primary-description, .job-card-container__company-name, [class*="company-name"], [class*="primary-description"]');
                    var company = companyEl ? companyEl.innerText.trim().split('\\n')[0].trim() : '';
                    
                    var locEl = el.querySelector('.job-card-container__metadata-item, .job-card-container__metadata-item--one-line, [class*="metadata-item"]');
                    var location = locEl ? locEl.innerText.trim().split('\\n')[0].trim() : '';
                    
                    var tEl = el.querySelector('time, [class*="posted-time"]');
                    var posted_time = tEl ? tEl.innerText.trim().split('\\n')[0].trim() : '';
                    
                    return {
                        title: title,
                        company: company,
                        location: location,
                        posted_time: posted_time,
                        url: a.href
                    };
                }).filter(function(j){return j && j.url;}))
                """
                
                cards_raw = self.cdp.eval_js(extract_cards_expr, timeout=10)
                cards = []
                if cards_raw:
                    try:
                        import json
                        cards = json.loads(cards_raw)
                    except Exception as e:
                        logger.error("Failed to parse cards JSON: %s", e)

                logger.info("Found %d cards on page %d for role [%s]", len(cards), page + 1, role)
                if not cards:
                    break

                new_on_page = 0
                for ci, card in enumerate(cards):
                    if role_jobs_count >= limit_per_role:
                        break

                    card_url = card.get("url", "")
                    if not card_url:
                        continue

                    jid = self._extract_job_id(card_url)
                    if not jid:
                        continue

                    # Check if already present via job_id = f"linkedin_{jid}"
                    expected_job_id = f"linkedin_{jid}"
                    existing = self.db.jobs.get_job_by_id(expected_job_id)
                    if existing:
                        logger.debug("Job %s already exists in db, skipping details page", expected_job_id)
                        continue

                    # Click card to open detail pane
                    click_expr = (
                        f"(function(){{"
                        f"  var cards = document.querySelectorAll('[data-occludable-job-id], .job-card-container, .jobs-search-two-pane__job-card-container, .job-card-list__container');"
                        f"  if(cards.length > {ci}){{"
                        f"    var btn = cards[{ci}].querySelector('a[href*=\"/jobs/view/\"], .job-card-list__title, a.job-card-container__link');"
                        f"    if(btn){{ btn.click(); return 'clicked'; }}"
                        f"  }}"
                        f"  return 'not found';"
                        f"}})()"
                    )
                    clicked_status = self.cdp.eval_js(click_expr)
                    if clicked_status != "clicked":
                        logger.warning("Could not click card index %d", ci)
                        continue
                    
                    time_to_wait = 2.0
                    import time
                    time.sleep(time_to_wait)

                    # Extract detail pane content
                    detail_expr = """
                    (function(){
                        var detail = document.querySelector('.jobs-search__job-details--container, [class*="job-details"], .jobs-details__main-content, .jobs-details');
                        if(!detail) return null;
                        var desc = detail.querySelector('.jobs-description__content, .jobs-description, [class*="description"], #job-details, .job-details-module, .jobs-box__html-content');
                        var jdText = desc ? desc.innerText : '';
                        
                        var easyBtn = detail.querySelector('button.jobs-apply-button, .jobs-apply-button--top-card, button[aria-label*="Easy Apply"], button[class*="apply-button"]');
                        var applyType = easyBtn ? 'easy_apply' : 'external_apply';
                        
                        var extUrl = '';
                        if(!easyBtn){
                            var extBtn = detail.querySelector('a[data-tracking-control-name="public_jobs_apply-link"], a[href*="/jobs/apply/"], a[class*="apply"], [class*="apply-link"]');
                            extUrl = extBtn ? extBtn.href : '';
                        }
                        return {
                            description: jdText,
                            apply_mode: applyType,
                            external_url: extUrl
                        };
                    })()
                    """
                    
                    detail = self.cdp.eval_js(detail_expr, timeout=10)
                    if not detail:
                        logger.warning("Failed to extract details for card %d", ci)
                        continue

                    jd_text = detail.get("description", "")
                    apply_mode = detail.get("apply_mode", "unknown")
                    external_url = detail.get("external_url", "")

                    # Classify roles/locations using normalizers
                    title = card.get("title", "")
                    company = card.get("company", "")
                    location = card.get("location", "")
                    
                    normalized_r = normalize_role(title)
                    norm_location = extract_location(location) or extract_location(jd_text) or "india"
                    experience = extract_experience(jd_text)
                    
                    # Generate a clean fingerprint key
                    company_clean = re.sub(r'[^a-z0-9]', '', company.lower()) if company else 'unknown'
                    role_clean = normalized_r if normalized_r else 'unknown'
                    loc_clean = norm_location.lower().strip()[:50] if norm_location else ''
                    fingerprint = f"{company_clean}:{role_clean}:{loc_clean}"

                    links = [external_url] if external_url else []
                    if not links:
                        links = [card_url]
                    c_method = "form" if apply_mode == "easy_apply" else classify_contact(links=links, text=jd_text)

                    job_data = {
                        "job_id": expected_job_id,
                        "company_name": company,
                        "job_role": title,
                        "location": location,
                        "eligibility": experience,
                        "salary": None,
                        "jd_text": jd_text,
                        "raw_message_id": None,
                        "email": None,
                        "phone": None,
                        "application_link": external_url or card_url,
                        "recruiter_name": None,
                        "is_hidden": False,
                        "is_duplicate": False,
                        "duplicate_of_id": None,
                        "confidence_score": 1.0,
                        "extraction_method": "direct_scrape",
                        "job_fingerprint": fingerprint,
                        "normalized_role": normalized_r,
                        "role_category": normalized_r,
                        "experience_hint": experience,
                        "location_hint": norm_location,
                        "contact_method": c_method,
                        "poster_name": None,
                        "poster_url": None,
                        "post_url": card_url,
                        "source_event_id": None,
                        "job_relevance": "relevant",
                        "metadata": {
                            "apply_mode": apply_mode,
                            "posted_time_text": card.get("posted_time", ""),
                            "scraped_at": datetime.now(timezone.utc).isoformat()
                        }
                    }

                    # Tiered Deduplication Check: we check exact job fingerprint match in database
                    # Later, Phase 5 integrates the comprehensive DedupAgent. For now, check fingerprint.
                    try:
                        # Find duplicate by fingerprint in UnifiedJobRepository
                        # (UnifiedJobRepository has find_duplicate_processed_job or similar, we will make sure it handles fingerprint check)
                        duplicate_job = self.db.jobs.find_duplicate_processed_job(
                            company, title, None
                        )
                        if duplicate_job:
                            logger.info("Duplicate job found for '%s' - '%s' in jobs table. Skipping.", company, title)
                            continue

                        inserted_id = self.db.jobs.add_job(job_data, source="linkedin")
                        if inserted_id:
                            total_new += 1
                            new_on_page += 1
                            role_jobs_count += 1
                            logger.info("Successfully added LinkedIn job: %s - %s", company, title)
                    except Exception as e:
                        logger.error("Failed to add job to database: %s", e)

                total_scraped += len(cards)
                logger.info("Page %d summary: new %d jobs", page + 1, new_on_page)
                if new_on_page == 0:
                    logger.info("No new jobs captured on this page, moving to next role.")
                    break

        return {
            "total_scraped": total_scraped,
            "total_new": total_new,
            "per_role": per_role
        }
