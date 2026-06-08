"""LinkedIn Post Scraper.

Scrapes LinkedIn posts using content searches, extracts relevant metadata,
and inserts them into the raw_events table and processing queue.
"""

import hashlib
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from scrapers.linkedin.cdp_client import CDPClient

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

class LinkedInPostScraper:
    """Scraper for LinkedIn content search posts."""
    
    def __init__(self, cdp: CDPClient, db: Any):
        self.cdp = cdp
        self.db = db

    def scrape(self, roles: Optional[List[str]] = None, scrolls: int = 3) -> Dict[str, Any]:
        """Scrape posts for all configured roles and search queries."""
        roles_to_scrape = roles or DEFAULT_ROLES
        queries = []
        for r in roles_to_scrape:
            queries.append((r, f"hiring {r}"))
            queries.append((r, f"looking for {r}"))

        logger.info("Starting LinkedIn post scraping for %d queries", len(queries))
        total_scraped = 0
        total_new = 0
        per_role = {role: 0 for role in roles_to_scrape}

        for role, query in queries:
            try:
                escaped_query = urllib.parse.quote(query)
                url = f"https://www.linkedin.com/search/results/content/?keywords={escaped_query}&datePosted=%5B%22past-24h%22%5D"
                logger.info("Scraping query [%s]: %s", query, url)
                
                self.cdp.navigate(url, wait_seconds=5)

                # Expand post text buttons
                expand_expr = (
                    "Array.from(document.querySelectorAll("
                    "'[data-testid=\"expandable-text-button\"], button[data-testid=\"expandable-text-button\"]'"
                    ")).forEach(function(b){try{b.click()}catch(e){}}); true"
                )
                self.cdp.eval_js(expand_expr)

                # Scroll to load more content
                scroll_expr = (
                    f"(async function(){{"
                    f"  for(var i=0; i<{scrolls}; i++){{"
                    f"    window.scrollBy(0, Math.floor(window.innerHeight * 2.3));"
                    f"    await new Promise(function(r){{setTimeout(r, 1200)}});"
                    f"    Array.from(document.querySelectorAll("
                    f"      '[data-testid=\"expandable-text-button\"], button[data-testid=\"expandable-text-button\"]'"
                    f"    )).forEach(function(b){{try{{b.click()}}catch(e){{}}}});"
                    f"  }}"
                    f"  return true;"
                    f"}})()"
                )
                self.cdp.eval_js(scroll_expr, timeout=15, await_promise=True)

                # Extract post elements
                extract_expr = """
                JSON.stringify(Array.from(document.querySelectorAll('div[role="listitem"], .reusable-search__result-container, [class*="search-result"]')).map(function(el){
                    var descEl = el.querySelector('.feed-shared-update-v2__description, .update-components-text, [class*="update-v2__description"], [class*="update-components-text"], .feed-shared-text, .feed-shared-inline-show-more-text');
                    var postText = descEl ? descEl.innerText : (el.innerText || '');
                    
                    var links = Array.from(el.querySelectorAll('a')).map(function(a){return a.href}).filter(Boolean);
                    var emails = postText.match(/[\\w\\.-]+@[\\w\\.-]+\\.\\w+/g) || [];
                    
                    var posterLink = el.querySelector('a[href*="/in/"], a[href*="/company/"]');
                    var posterName = posterLink && posterLink.innerText ? posterLink.innerText.trim().split('\\n')[0].trim() : '';
                    var posterUrl = posterLink ? posterLink.href : '';
                    
                    var postA = el.querySelector('a[href*="/feed/update/urn:li:activity:"], a[href*="/posts/"], a[href*="/detail/recent-activity/shares/"]');
                    var postUrl = postA ? postA.href : '';

                    return {
                        posterName: posterName,
                        posterUrl: posterUrl,
                        postText: postText,
                        postUrl: postUrl,
                        emails: Array.from(new Set(emails)),
                        links: Array.from(new Set(links))
                    };
                }).filter(function(p){return p.postText && p.postText.trim().length > 50;}))
                """
                extracted_data_raw = self.cdp.eval_js(extract_expr, timeout=15)
                posts = []
                if extracted_data_raw:
                    try:
                        import json
                        posts = json.loads(extracted_data_raw)
                    except Exception as e:
                        logger.error("Failed to parse extracted JSON: %s", e)

                logger.info("Found %d post candidates for query [%s]", len(posts), query)
                added = 0
                for p in posts:
                    post_text = p.get("postText", "")
                    if len(post_text) < 80:
                        continue

                    # Construct unique deterministic source ID
                    poster_url = p.get("posterUrl") or ""
                    # Normalize text slightly for deduplication hash key
                    text_prefix = post_text[:140].strip()
                    raw_id = f"{poster_url}_{text_prefix}"
                    source_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

                    metadata = {
                        "keyword": query,
                        "role": role,
                        "poster_name": p.get("posterName"),
                        "poster_url": poster_url,
                        "post_url": p.get("postUrl") or f"https://www.linkedin.com/search/results/content/?keywords={escaped_query}",
                        "emails_found": p.get("emails", []),
                        "links_found": p.get("links", []),
                        "scraped_at": datetime.now(timezone.utc).isoformat()
                    }

                    # Add event and enqueue
                    try:
                        event_id = self.db.events.add_event(
                            source="linkedin",
                            source_id=source_id,
                            content=post_text,
                            metadata=metadata
                        )
                        if event_id:
                            self.db.queue.enqueue(event_id, priority=0)
                            added += 1
                            per_role[role] += 1
                    except Exception as exc:
                        logger.error("Failed to add LinkedIn event to database: %s", exc)

                total_scraped += len(posts)
                total_new += added
                logger.info("Query [%s]: Added %d new events to raw_events and queue", query, added)

            except Exception as e:
                logger.error("Error scraping query [%s]: %s", query, e, exc_info=True)

        return {
            "total_scraped": total_scraped,
            "total_new": total_new,
            "per_role": per_role
        }
