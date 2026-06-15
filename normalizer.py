"""Normalization helpers for queue-based lead extraction.

These helpers are deterministic post-processing used after LLM extraction. They
avoid user-specific scoring; the server remains a source-agnostic ingestion and
normalization engine.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional


ROLE_PATTERNS = [
    ("ai_engineer", ("ai engineer", "artificial intelligence engineer", "genai engineer", "generative ai", "llm engineer", "prompt engineer")),
    ("ml_engineer", ("machine learning", "ml engineer", "deep learning", "computer vision", "nlp engineer")),
    ("data_engineer", ("data engineer", "etl", "pipeline engineer", "analytics engineer")),
    ("data_scientist", ("data scientist", "data science", "ml scientist")),
    ("python_developer", ("python developer", "python engineer", "django", "fastapi", "flask")),
    ("backend_developer", ("backend", "back end", "api developer", "server-side", "server side")),
    ("fullstack_developer", ("full stack", "fullstack", "mern", "mean stack")),
    ("frontend_developer", ("frontend", "front end", "react", "vue", "angular")),
    ("software_engineer", ("software engineer", "software developer", "sde", "developer", "programmer")),
    ("devops_engineer", ("devops", "sre", "site reliability", "cloud engineer", "platform engineer")),
    ("qa_engineer", ("qa", "quality assurance", "sdet", "test engineer", "testing")),
    ("intern", ("intern", "internship", "trainee")),
]

LOCATION_PATTERNS = [
    ("remote", r"\b(remote|work from home|wfh)\b"),
    ("india", r"\b(india|bharat|pan india|bangalore|bengaluru|mumbai|delhi|ncr|gurgaon|gurugram|noida|hyderabad|pune|chennai|kolkata|ahmedabad|kochi|coimbatore)\b"),
    ("us", r"\b(united states|usa|u\.s\.|new york|california|san francisco|texas|seattle)\b"),
    ("uk", r"\b(united kingdom|uk|london|england)\b"),
    ("europe", r"\b(europe|eu|germany|france|netherlands|spain|ireland|poland)\b"),
]


COMPANY_STOPWORDS = {
    "hiring", "looking", "urgent", "immediate", "job", "jobs", "opening", "openings",
    "recruiter", "talent", "acquisition", "human", "resources", "hr", "team",
}


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_role(role: object) -> Optional[str]:
    """Map a free-form job role to a canonical role category."""
    text = _clean_text(role).lower()
    if not text:
        return None
    for canonical, needles in ROLE_PATTERNS:
        if any(needle in text for needle in needles):
            return canonical
    # Preserve a compact normalized fallback instead of losing the signal.
    compact = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return compact[:80] or None


def infer_company(poster_name: object = None, post_text: object = None) -> Optional[str]:
    """Infer company from LinkedIn poster metadata or post content.

    Conservative by design: returns None when the signal looks like a person or
    generic recruiter phrase.
    """
    text = _clean_text(post_text)
    poster = _clean_text(poster_name)

    patterns = [
        r"(?:company|organisation|organization)\s*[:\-–—]\s*([A-Z][A-Za-z0-9&.,'()\- ]{1,80})",
        r"(?:at|@)\s+([A-Z][A-Za-z0-9&.,'()\- ]{1,80})\s+(?:is hiring|we are hiring|hiring|has an opening)",
        r"([A-Z][A-Za-z0-9&.,'()\- ]{1,80})\s+(?:is hiring|we are hiring|hiring for|has an opening)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = re.split(r"[\n|•·;]", match.group(1))[0]
            candidate = re.sub(r"\s+(?:is|are|we)\s*$", "", candidate, flags=re.IGNORECASE).strip(" .,-–—")
            words = {w.lower() for w in re.findall(r"[A-Za-z]+", candidate)}
            if candidate and not words.issubset(COMPANY_STOPWORDS):
                return candidate[:120]

    # Company pages often arrive as poster names. Avoid names that look like a
    # two-word human name unless they include company suffixes/signals.
    if poster:
        lower = poster.lower()
        if any(sig in lower for sig in (" inc", " ltd", " llp", " pvt", " technologies", " labs", " ai", " software", " solutions")):
            return poster[:120]
        if len(poster.split()) >= 3 and not any(w in lower for w in ("recruiter", "talent", "hr")):
            return poster[:120]
    return None


def extract_location(text: object) -> Optional[str]:
    """Extract a coarse location hint such as india, remote, us, uk, europe."""
    value = _clean_text(text).lower()
    if not value:
        return None
    found = []
    for label, pattern in LOCATION_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            found.append(label)
    if not found:
        return None
    # Keep remote+region when both are present.
    if "remote" in found and len(found) > 1:
        return "remote," + ",".join(x for x in found if x != "remote")
    return found[0]


def extract_experience(text: object) -> Optional[str]:
    """Extract years-of-experience requirement from text."""
    value = _clean_text(text).lower()
    if not value:
        return None
    patterns = [
        r"(\d{1,2}\s*[-–—+]\s*\d{1,2}\s*(?:years?|yrs?))",
        r"(\d{1,2}\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)?)",
        r"(?:experience|exp)\s*[:\-–—]?\s*(\d{1,2}\s*[-–—+]\s*\d{1,2}\s*(?:years?|yrs?)?)",
        r"\b(fresher|freshers|entry[ -]?level|new grad|graduate)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None


def classify_contact(emails: Optional[Iterable[object]] = None, links: Optional[Iterable[object]] = None, text: object = None) -> str:
    """Classify the best available contact method for an extracted lead."""
    emails = [str(e).strip() for e in (emails or []) if e]
    links = [str(l).strip() for l in (links or []) if l]
    value = _clean_text(text).lower()

    if emails or re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", value, re.IGNORECASE):
        return "email"
    if any(re.search(r"(forms\.gle|docs\.google\.com/forms|airtable|typeform|greenhouse|lever|workday|ashbyhq|wellfound|apply|careers)", link, re.IGNORECASE) for link in links):
        return "form"
    if links:
        return "link"
    if re.search(r"\b(linkedin post|comment interested|comment your|drop your cv|share your resume)\b", value):
        return "linkedin_post"
    if re.search(r"\b(dm|direct message|inmail|message me|connect with me|linkedin dm)\b", value):
        return "linkedin_dm"
    if re.search(r"\b(whatsapp|wa\.me|telegram)\b", value):
        return "messaging"
    return "none"


import urllib.request
import urllib.error
import urllib.parse
import ssl
import time

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

AGGREGATOR_DOMAINS = {
    'techjobs360.com', 'jobsrmine.com', 'remoteyeah.com', 'onnetpulse.com',
    'fresherscall.com', 'careerten.com', 'hirist.com', 'naukri.com',
    'shine.com', 'monster.com', 'timesjobs.com', 'updazz.com',
    'linkedin.com'
}

def extract_hrefs(html: str) -> set[str]:
    """Extract all href URLs from HTML that look like real links."""
    urls = set()
    for m in re.finditer(r'href="(https?://[^"]+)"', html, re.IGNORECASE):
        u = m.group(1)
        if not any(skip in u for skip in ['static.licdn.com', 'linkedin.com/help', 'linkedin.com/scds']):
            urls.add(u)
    return urls

def resolve_lnkd_url(url: str, max_retries: int = 2) -> Optional[str]:
    """Resolve a LinkedIn short URL by fetching the interstitial page."""
    req = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    for attempt in range(max_retries):
        try:
            resp = urllib.request.urlopen(req, timeout=15, context=ssl_ctx)
            html = resp.read().decode('utf-8', errors='replace')
            meta = re.search(r'meta\s+http-equiv="refresh"\s+content="\d+;url=\'([^\']+)\'"', html, re.IGNORECASE)
            if meta:
                return meta.group(1)
            
            hrefs = extract_hrefs(html)
            external = [h for h in hrefs if not h.startswith('https://www.linkedin.com') and 'linkedin.com/help' not in h]
            if external:
                return external[-1]
            
            li_pages = [h for h in hrefs if h.startswith('https://www.linkedin.com')]
            if li_pages:
                for h in li_pages:
                    if '/jobs/view/' in h or '/jobs/' in h:
                        return h
                return li_pages[0]
            
            return None
            
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return f"ERROR: {e}"
    return None

def resolve_direct_url(url: str) -> str:
    """Follow redirects for a direct (non-lnkd.in) URL."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        resp = urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
        return resp.geturl()
    except Exception:
        return url

def categorize_url(final_url: str) -> tuple[str, str]:
    """Categorize the resolved URL. Returns (category, final_url)."""
    if not final_url or final_url.startswith('ERROR'):
        return 'unresolvable', final_url
    
    parsed = urllib.parse.urlparse(final_url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    full_url = final_url.lower()
    
    if 't.me' in domain or 'telegram' in domain:
        return 'telegram', final_url
    
    if any(fd in full_url for fd in ['forms.gle', 'docs.google.com/forms', 'typeform.com', 'jotform.com']):
        return 'form', final_url
    
    if domain in ('www.linkedin.com', 'linkedin.com') and '/jobs/view/' in path:
        qs = urllib.parse.parse_qs(parsed.query)
        if 'easyApply' in qs:
            return 'linkedin_easy_apply', final_url
        return 'linkedin_job_view', final_url
    
    if domain in ('www.linkedin.com', 'linkedin.com') and ('/posts/' in path or '/feed/' in path):
        return 'linkedin_post', final_url
    
    if domain in ('www.linkedin.com', 'linkedin.com'):
        return 'linkedin_page', final_url
    
    if domain in AGGREGATOR_DOMAINS:
        return 'aggregator', final_url
    
    aggregator_patterns = ['fresherscall', 'careerten', 'hirist', 'timesjobs', 'updazz']
    if any(p in domain for p in aggregator_patterns):
        return 'aggregator', final_url
    
    return 'external_apply', final_url

def resolve_and_categorize_link(url: str) -> tuple[str, str]:
    """Resolves any shortlinks and categorizes the URL. Returns (category, resolved_url)."""
    if not url or url == '-':
        return 'no_link', ''
    
    is_lnkd = 'lnkd.in' in url
    resolved = None
    
    if is_lnkd:
        resolved = resolve_lnkd_url(url)
    else:
        resolved = resolve_direct_url(url)
    
    if not resolved:
        resolved = url
        
    return categorize_url(resolved)

