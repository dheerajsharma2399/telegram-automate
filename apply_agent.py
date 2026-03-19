import os
import json
import logging
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SECONDS = 90

# Match config.py convention: use OPENROUTER_API_KEY (singular) as primary
_api_keys_str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEYS = [k.strip() for k in _api_keys_str.split(",") if k.strip()]
OPENROUTER_API_KEY = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else None
OPENROUTER_MODELS = os.getenv("OPENROUTER_MODELS", "anthropic/claude-3.5-sonnet").split(",")
OPENROUTER_FALLBACK_MODELS = os.getenv("OPENROUTER_FALLBACK_MODELS", "openai/gpt-4o-mini").split(",")

logger = logging.getLogger(__name__)


def _score_keywords(text: str, keywords: list) -> int:
    """Count overlapping keywords between text and keyword list."""
    if not text or not keywords:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def _match_relevant_projects(jd_text: str, profile: dict) -> list:
    """Score and return top 2 projects matching the job description."""
    projects = profile.get("projects", [])
    scored = []
    for proj in projects:
        tech_stack = proj.get("tech_stack", [])
        description = proj.get("description", "")
        score = _score_keywords(jd_text, tech_stack) + _score_keywords(jd_text, description.split())
        scored.append((score, proj))
    scored.sort(reverse=True)
    return [p for _, p in scored[:2]]


def _match_relevant_experience(jd_text: str, profile: dict) -> list:
    """Score and return top 2 work achievements matching the job description."""
    experience = profile.get("work_experience", [])
    scored = []
    for exp in experience:
        achievements = exp.get("key_achievements", [])
        techs = exp.get("technologies", [])
        for ach in achievements:
            score = _score_keywords(jd_text, [ach]) + _score_keywords(jd_text, techs)
            scored.append((score, ach))
    scored.sort(reverse=True)
    return [a for _, a in scored[:2]]


def _call_openrouter(model: str, messages: list, api_keys: list) -> Optional[dict]:
    """Make synchronous call to OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {api_keys[0]}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/dheerajsharma2399/telegram-automate",
        "X-Title": "telegram-automate-apply"
    }
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": 2000
    }
    for key in api_keys:
        headers["Authorization"] = f"Bearer {key}"
        try:
            resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return json.loads(content)
            else:
                logger.warning(f"Model {model} returned status {resp.status_code}")
        except Exception as e:
            logger.warning(f"API call failed with {model}: {e}")
    return None


def generate_email_draft(
    jd_text: str,
    profile: dict,
    company: str = "",
    role: str = "",
    recruiter_name: str = ""
) -> dict:
    """
    Generate an email draft for a job application.

    Returns:
        {
            "subject": "Application: Backend Engineer — Dheeraj Sharma",
            "body_html": "<p>...</p>",
            "tokens_used": 1240,
            "model_used": "anthropic/claude-3.5-sonnet"
        }
    Raises: RuntimeError if all models fail
    """
    # Match relevant projects and experience
    top_projects = _match_relevant_projects(jd_text, profile)
    top_achievements = _match_relevant_experience(jd_text, profile)

    candidate_name = profile.get("personal_information", {}).get("full_name", "Candidate")

    system_prompt = """You are a professional job application email writer. Generate a cold outreach email.

Output JSON with exactly this schema:
{
  "subject": "string — max 98 chars",
  "body_html": "string — HTML email body, 250-300 words"
}

Requirements:
- Write a professional but warm cold email, 250-300 words
- Lead with one concrete achievement or metric directly relevant to the job description
- Mention 1-2 of the candidate's most relevant projects with repo links as clickable <a href=""> tags
- Bold key metrics using <strong>
- No generic openers like "I hope this email finds you well"
- End with a clear call to action
- Use light HTML only: <p>, <strong>, <a>, <ul>, <li>
- Subject line format: Application: {role} — {candidate_name}
"""

    user_prompt = f"""Generate a tailored application email.

Job Description:
{jd_text}

Company: {company}
Role: {role}
Recruiter Name: {recruiter_name or 'Hiring Manager'}

Candidate Profile:
{json.dumps(profile, indent=2)}

Top Relevant Projects (include these with links):
{json.dumps(top_projects, indent=2)}

Top Relevant Achievements:
{json.dumps(top_achievements, indent=2)}

Write the email now. Return only valid JSON."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Try primary model
    result = _call_openrouter(OPENROUTER_MODELS[0].strip(), messages, OPENROUTER_API_KEYS)

    # Try fallback if primary fails
    if result is None and OPENROUTER_FALLBACK_MODELS:
        result = _call_openrouter(OPENROUTER_FALLBACK_MODELS[0].strip(), messages, OPENROUTER_API_KEYS)

    if result is None:
        raise RuntimeError("All OpenRouter models failed to generate email")

    return {
        "subject": result.get("subject", ""),
        "body_html": result.get("body_html", ""),
        "tokens_used": 0,  # OpenRouter doesn't return token count in response
        "model_used": OPENROUTER_MODELS[0].strip()
    }


if __name__ == "__main__":
    # Test with sample data
    import sys
    sys.path.insert(0, "/home/drdash/Documents/Projects/telegram-automate")

    # Load user profile
    with open("/home/drdash/Documents/Projects/telegram-automate/user_profile.json") as f:
        profile = json.load(f)

    jd_text = "We are looking for a Backend Engineer with Python, PostgreSQL, and AWS experience. 2+ years experience required."

    try:
        result = generate_email_draft(jd_text, profile, "Acme Corp", "Backend Engineer", "John")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")