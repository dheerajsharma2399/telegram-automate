import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# Support multiple group usernames/ids via comma-separated env var
TELEGRAM_GROUP_USERNAME = os.getenv('TELEGRAM_GROUP_USERNAME')
TELEGRAM_GROUP_USERNAMES = [s.strip() for s in os.getenv('TELEGRAM_GROUP_USERNAMES', '').split(',') if s.strip()]
# Backwards compatible fallback to single value
if not TELEGRAM_GROUP_USERNAMES and TELEGRAM_GROUP_USERNAME:
	TELEGRAM_GROUP_USERNAMES = [TELEGRAM_GROUP_USERNAME]

AUTHORIZED_USER_IDS = [int(x) for x in os.getenv('AUTHORIZED_USER_IDS', '').split(',') if x]
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
OPENROUTER_FALLBACK_MODEL = os.getenv('OPENROUTER_FALLBACK_MODEL', 'openai/gpt-4o-mini')

# Google Sheets Configuration
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# Database Configuration - PURE POSTGRESQL ONLY (Supabase)
DATABASE_TYPE = 'postgresql'  # Always PostgreSQL, no SQLite
DATABASE_PATH = os.getenv('DATABASE_PATH')  # Ignored in PostgreSQL mode
DATABASE_URL = os.getenv('DATABASE_URL') or 'postgres://***REMOVED***@152.67.7.111:5433/postgres'

# Ensure DATABASE_URL is set for Supabase connection
if not DATABASE_URL:
    raise ValueError("DATABASE_URL must be set for Supabase PostgreSQL connection")

# Processing Configuration
BATCH_SIZE = 10
PROCESSING_INTERVAL_MINUTES = 10
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
12. job_relevance: "relevant" for very recent or future graduates (e.g., 2025 batch, 2026 batch, "fresher", "entry level", 0-1 years experience), "irrelevant" for all other roles, especially those mentioning graduation years of 2024 or earlier (e.g., "2024 batch", "2023 or before", "2-5 years experience", "senior/lead/manager positions")

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
    "jd_text": "We are looking for a Software Engineer to join our team..."
  }
]"""