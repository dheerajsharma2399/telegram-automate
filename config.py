import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_GROUP_USERNAME = os.getenv('TELEGRAM_GROUP_USERNAME')
AUTHORIZED_USER_IDS = [int(x) for x in os.getenv('AUTHORIZED_USER_IDS', '').split(',') if x]
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
OPENROUTER_FALLBACK_MODEL = os.getenv('OPENROUTER_FALLBACK_MODEL', 'openai/gpt-4o-mini')

# Google Sheets Configuration
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# Database Configuration
DATABASE_PATH = 'jobs.db'

# Processing Configuration
BATCH_SIZE = 10
PROCESSING_INTERVAL_MINUTES = 5
MAX_RETRIES = 3

# System Prompt for LLM
SYSTEM_PROMPT = """You are an expert job posting parser. Extract ALL job postings from the given text.

For EACH job posting found, extract:
1. company_name: Company or organization name
2. job_role: Position/role title
3. location: Job location(s) (empty string if not found)
4. eligibility: Year of graduation, degree requirements (empty string if not found)
5. email: Contact email (null if not present)
6. phone: Phone number (null if not present)
7. application_link: External link for application (null if not present)
8. recruiter_name: HR/recruiter name (empty string if not mentioned)
9. email_subject: Custom subject line if specified (null if not mentioned)
10. jd_text: Complete job description text

Return ONLY a JSON array of job objects. If no jobs found, return empty array [].
Do not include any explanation or markdown formatting, just the JSON array."""
