import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')
# Support multiple group usernames/ids via comma-separated env var
TELEGRAM_GROUP_USERNAME = os.getenv('TELEGRAM_GROUP_USERNAME')
TELEGRAM_GROUP_USERNAMES = [s.strip() for s in os.getenv('TELEGRAM_GROUP_USERNAMES', '').split(',') if s.strip()]
# Backwards compatible fallback to single value
if not TELEGRAM_GROUP_USERNAMES and TELEGRAM_GROUP_USERNAME:
	TELEGRAM_GROUP_USERNAMES = [TELEGRAM_GROUP_USERNAME]

# Parse AUTHORIZED_USER_IDS with error handling for invalid values
def _parse_user_ids():
    raw = os.getenv('AUTHORIZED_USER_IDS', '')
    user_ids = []
    for x in raw.split(','):
        x = x.strip()
        if x:
            try:
                user_ids.append(int(x))
            except ValueError:
                import logging
                logging.getLogger(__name__).warning(f"Invalid user ID in AUTHORIZED_USER_IDS: {x!r}")
    return user_ids

AUTHORIZED_USER_IDS = _parse_user_ids()
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')

# OpenRouter Configuration
_api_keys_str = os.getenv('OPENROUTER_API_KEYS') or os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_API_KEYS = [k.strip() for k in _api_keys_str.split(',') if k.strip()]
# Fallback for single key usage if needed elsewhere, though we should transition to list
OPENROUTER_API_KEY = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else None

_models_str = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
OPENROUTER_MODELS = [m.strip() for m in _models_str.split(',') if m.strip()]
OPENROUTER_MODEL = OPENROUTER_MODELS[0] if OPENROUTER_MODELS else 'anthropic/claude-3.5-sonnet'

_fallback_models_str = os.getenv('OPENROUTER_FALLBACK_MODEL', 'openai/gpt-4o-mini')
OPENROUTER_FALLBACK_MODELS = [m.strip() for m in _fallback_models_str.split(',') if m.strip()]
OPENROUTER_FALLBACK_MODEL = OPENROUTER_FALLBACK_MODELS[0] if OPENROUTER_FALLBACK_MODELS else 'openai/gpt-4o-mini'

# Google Sheets Configuration
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
# Support multiple spreadsheets for broadcasting jobs to other users
_additional_sheets_str = os.getenv('ADDITIONAL_SPREADSHEET_IDS', '')
ADDITIONAL_SPREADSHEET_IDS = [s.strip() for s in _additional_sheets_str.split(',') if s.strip()]

# Database Configuration - PURE POSTGRESQL ONLY (Supabase)
DATABASE_TYPE = 'postgresql'  # Always PostgreSQL, no SQLite
DATABASE_PATH = os.getenv('DATABASE_PATH')  # Ignored in PostgreSQL mode
DATABASE_URL = os.getenv('DATABASE_URL')

# Fix for SQLAlchemy compatibility with postgres:// scheme
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Validate critical environment variables
if not DATABASE_URL:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "DATABASE_URL environment variable is not set; database-backed entrypoints will fail until configured."
    )

if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
    raise ValueError(
        "TELEGRAM_API_ID and TELEGRAM_API_HASH are required for Telegram API access. "
        "Please configure them in .env file."
    )

if not OPENROUTER_API_KEYS or not OPENROUTER_API_KEYS[0]:
    raise ValueError(
        "OPENROUTER_API_KEY is required for LLM job parsing. "
        "Please configure it in .env file."
    )

if not GOOGLE_CREDENTIALS_JSON or not SPREADSHEET_ID:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "GOOGLE_CREDENTIALS_JSON or SPREADSHEET_ID not set — Google Sheets sync disabled. "
        "Set both env vars to enable Sheets integration."
    )

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Processing Configuration
BATCH_SIZE = 10
PROCESSING_INTERVAL_MINUTES = 10
FETCH_INTERVAL_MINUTES = 10  # Run every 10 minutes
FETCH_LOOKBACK_MINUTES = 12  # Look back 12 minutes
MAX_RETRIES = 3
INITIAL_HISTORICAL_FETCH_HOURS = 12

# IMPROVED System Prompt for LLM - ALIGNED with proper Google Sheets headers
SYSTEM_PROMPT = """You are an expert job posting parser. Extract ALL job postings from the given text.

For EACH job posting found, extract the following fields as a JSON object:

1. company_name: Company or organization name (required)
2. job_role: Position/role title (required)
3. location: Job location(s) - city, state, remote, etc. (empty string if not found)
4. eligibility: Year of graduation, degree requirements, experience needed (empty string if not found)
5. email: Contact email address for applications (null if not present)
6. phone: Phone number for applications (null if not present)
7. application_link: External URL/link for online applications (null if not present)
8. recruiter_name: HR person, hiring manager, or recruiter name (empty string if not mentioned)
9. email_subject: Custom email subject line if specified (null if not mentioned)
10. jd_text: Complete job description text including requirements, responsibilities, etc.
11. experience_required: Experience requirements (e.g., "fresher", "0-1 years", "2+ years", "2024/2025/2026 batch")
12. salary: Stipend/CTC/Salary/Compensation (e.g., "10-15 LPA", "20k/month", "Competitive", "Not disclosed")
13. sheet_name: The target sheet name. Use "email" if email is present, "non-email" if email is not present.

CRITICAL REQUIREMENTS:
- Return ONLY a JSON array of job objects
- If no jobs found, return empty array []
- Do not include any explanation or markdown formatting, just the JSON array
- Each field must be properly typed: strings for text fields, null for missing optional fields
- company_name and job_role are mandatory fields - if missing, the job posting is invalid
- Always extract the complete job description in jd_text field

Example format:
[
  {
    "company_name": "TechCorp Inc",
    "job_role": "Software Engineer",
    "location": "San Francisco, CA (Remote)",
    "eligibility": "2024/2025 graduates, CS degree",
    "email": "hr@techcorp.com",
    "phone": null,
    "application_link": "https://techcorp.com/careers",
    "recruiter_name": "Sarah Johnson",
    "email_subject": null,
    "jd_text": "We are looking for a Software Engineer to join our team...",
    "experience_required": "0-1 years",
    "salary": "12-15 LPA",
    "job_relevance": "relevant",
    "sheet_name": "email"
  }
]"""

LINKEDIN_SYSTEM_PROMPT = """You are an expert LinkedIn hiring-post parser. Extract ALL concrete job leads from the given LinkedIn post or repost.

Return ONLY valid JSON: an array of LeadCandidate objects. If no concrete job lead exists, return [].

LinkedIn-specific rules:
- LinkedIn posts may contain multiple roles. Return one object per role/company/contact combination.
- Preserve recruiter and post context: poster_name, poster_url, post_url when available.
- Distinguish real hiring posts from engagement bait. Return [] for generic "comment interested", advice, course ads, or vague networking posts unless a concrete role/company/contact is present.
- DM-only posts are still valid leads. Set contact_method to "dm" or "linkedin_dm" when the candidate must DM/connect/comment.
- If an external apply URL exists, preserve it exactly in application_link.
- Extract emails, phone numbers, WhatsApp links, Google Forms, ATS links, and career links without rewriting them.
- Keep jd_text as the most complete original job-description text available, not a short summary.
- Use null for missing values. Do not invent company names, salaries, locations, or years of experience.

LeadCandidate schema:
{
  "company_name": string | null,
  "job_role": string | null,
  "location": string | null,
  "email": string | null,
  "phone": string | null,
  "application_link": string | null,
  "recruiter_name": string | null,
  "poster_name": string | null,
  "poster_url": string | null,
  "post_url": string | null,
  "contact_method": "email" | "form" | "link" | "dm" | "linkedin_dm" | "linkedin_post" | "messaging" | "none" | null,
  "jd_text": string | null,
  "experience_required": string | null,
  "salary": string | null,
  "normalized_role": string | null,
  "role_category": string | null,
  "location_hint": string | null,
  "experience_hint": string | null,
  "confidence_score": number,
  "extraction_method": "llm_linkedin",
  "job_relevance": "relevant" | "irrelevant" | "unclassified",
  "sheet_name": "email" | "link" | "phone" | "other" | null
}

Confidence scoring rubric:
- 0.85-1.00: role + company + contact/apply path + location or experience signal.
- 0.65-0.84: role + contact/apply path, but company or location is inferred/weak.
- 0.45-0.64: role exists but only DM/comment contact or weak company evidence.
- <0.45: ambiguous post; include only if it is still a concrete hiring lead.
"""
