import re
from typing import Dict, Any, Optional

GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "protonmail.com",
    "aol.com", "zoho.com", "mail.com", "yandex.com", "live.com", "icloud.com",
    "gmail.co", "yahoo.co.in", "outlook.co.in", "hotmail.co.uk", "gmx.com",
    "yopmail.com", "tempmail.com", "proton.me", "googlemail.com", "rediffmail.com"
}

DISPLAY_ROLE_MAP = {
    "ai_engineer": "AI Engineer",
    "ml_engineer": "Machine Learning Engineer",
    "data_engineer": "Data Engineer",
    "data_scientist": "Data Scientist",
    "python_developer": "Python Developer",
    "backend_developer": "Backend Developer",
    "fullstack_developer": "Full Stack Developer",
    "frontend_developer": "Frontend Developer",
    "software_engineer": "Software Engineer",
    "devops_engineer": "DevOps Engineer",
    "qa_engineer": "QA Engineer",
    "intern": "Intern"
}

def extract_company_from_email(email: Optional[str]) -> Optional[str]:
    """Infers company name from a corporate email address."""
    if not email or "@" not in email:
        return None
    domain = email.split("@")[-1].lower().strip()
    if domain in GENERIC_DOMAINS:
        return None
    
    parts = domain.split(".")
    if len(parts) >= 2:
        # Check for co.in, org.uk, etc.
        if len(parts) >= 3 and parts[-2] in ("co", "org", "net", "gov", "ac", "edu", "res"):
            company = parts[-3]
        else:
            company = parts[-2]
            
        # Clean up special chars
        company = re.sub(r"[^a-zA-Z0-9]+", " ", company).strip()
        if company:
            return company.title()
    return None

def is_valid_company_name(s: str) -> bool:
    """Strictly validates whether a string looks like a legitimate company name."""
    s_lower = s.lower().strip()
    if not (2 <= len(s_lower) <= 50):
        return False
        
    # Rejects lines starting with bullets or special chars
    if s_lower.startswith(("-", "*", "🔹", "•", "▪", "+", "/", "\\", "📍", "📌", "🌍", "💰")):
        return False
        
    # Check common invalid phrases
    invalid_phrases = (
        "about the", "key skills", "role description", "apply here", "looking for you",
        "we are hiring", "urgent requirement", "opportunity for", "talent acquisition",
        "talent partner", "talent sourcer", "talent specialist", "talent manager",
        "talent team", "hr department", "recruitment consultant", "hiring manager",
        "hr manager", "hr executive", "hr specialist", "human resources", "human resource"
    )
    if any(phrase in s_lower for phrase in invalid_phrases):
        return False
        
    # Check individual words for recruiter/job post terminology
    words = set(re.findall(r"\b[a-z]{2,}\b", s_lower))
    invalid_words = {
        "apply", "click", "job", "jobs", "role", "roles", "position", "positions",
        "hiring", "opportunity", "opportunities", "opening", "openings", "recruiter",
        "acquisition", "experience", "location", "skills", "requirements",
        "qualifications", "responsibilities", "salary", "compensation", "stipend",
        "remote", "onsite", "on-site", "hybrid", "description", "details", "candidate",
        "learning", "development", "internship", "reactions", "reposts", "followers",
        "connections", "hr", "weintern"
    }
    if any(w in invalid_words for w in words):
        return False
        
    # Rejects pure location names and common location patterns (e.g., "Atlanta, Georgia")
    location_keywords = {
        "georgia", "california", "texas", "florida", "new york", "washington", "oregon", "colorado", 
        "illinois", "massachusetts", "arizona", "north carolina", "south carolina", "virginia", "maryland", 
        "ohio", "michigan", "pennsylvania", "new jersey", "ga", "ca", "tx", "fl", "ny", "wa", "ma", 
        "il", "pa", "nj", "nc", "va", "md", "mi", "oh", "co", "az", "or",
        "india", "usa", "uk", "united states", "united kingdom", "germany", "canada", "singapore", 
        "france", "netherlands", "spain", "ireland", "poland", "europe", "australia",
        "bengaluru", "bangalore", "mumbai", "delhi", "ncr", "gurgaon", "gurugram", "noida", 
        "hyderabad", "pune", "chennai", "kolkata", "ahmedabad", "kochi", "coimbatore", "london",
        "karnataka", "maharashtra", "haryana", "telangana", "tamil nadu", "uttar pradesh",
        "remote", "hybrid", "on-site", "onsite"
    }
    if s_lower in location_keywords:
        return False
        
    if "," in s_lower:
        parts = [p.strip() for p in s_lower.split(",")]
        if parts and parts[-1] in location_keywords:
            return False
            
    return True

def clean_company_name(
    company_name: Optional[str], 
    email: Optional[str] = None, 
    poster_name: Optional[str] = None, 
    jd_text: Optional[str] = None
) -> str:
    """Sanitizes and corrects company names, stripping junk and placeholders."""
    if not company_name:
        company_name = ""
        
    # Strip markdown and extra spaces
    name = re.sub(r"[\*\_#`\-\|]+", " ", company_name)
    name = re.sub(r"\s+", " ", name).strip()
    
    # Strip common prefix labels (e.g. "Company: ")
    name = re.sub(r"^(?:company|organization|organisation|employer)\s*[:\-–—]\s*", "", name, flags=re.IGNORECASE)
    
    invalid_patterns = (
        "unknown", "position", "role", "job", "you. apply here", 
        "gmail", "gmail.com", "yahoo", "outlook", "weintern"
    )
    is_invalid = (
        not name or 
        name.lower() in invalid_patterns or 
        any(pat in name.lower() for pat in ("apply here", "looking for you")) or
        not is_valid_company_name(name)
    )
    
    if is_invalid:
        # 1. Try to infer from email domain
        inferred = extract_company_from_email(email)
        if inferred:
            return inferred
            
        # 2. Try to infer from poster name if it has company flags
        if poster_name:
            p_lower = poster_name.lower()
            if any(sig in p_lower for sig in (" inc", " ltd", " llp", " pvt", " technologies", " labs", " solutions", " software", " consulting")):
                clean_p = re.sub(r"\b(recruiter|talent acquisition|hr manager|hiring manager)\b", "", poster_name, flags=re.IGNORECASE)
                clean_p = re.sub(r"\s+", " ", clean_p).strip()
                clean_p = clean_p.strip(" @atAT-–—_")
                if clean_p and is_valid_company_name(clean_p):
                    return clean_p
                    
        # 3. Try parsing from JD text
        if jd_text:
            match = re.search(r"(?:company|organisation|organization|employer)\s*[:\-–—]\s*([A-Za-z0-9 &.,'()\-]{2,50})", jd_text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if candidate.lower() not in invalid_patterns and is_valid_company_name(candidate):
                    return candidate
                    
        return "Unknown"
        
    return name.strip(" .,:;–—-_🔹•▪📍📌🌍💰🏢💻⏳📋✉️")

def clean_job_role(job_role: Optional[str], normalized_role: Optional[str] = None) -> str:
    """Cleans up job roles, trimming sentences and mapping placeholders."""
    if not job_role:
        role = ""
    else:
        role = str(job_role)
        
    # Strip markdown and junk characters
    role = re.sub(r"[\*\_#`\-\|]+", " ", role)
    role = re.sub(r"\s+", " ", role).strip()
    
    # Strip common prefix labels (e.g. "Role: ")
    role = re.sub(r"^(?:job\s+)?role\s*[:\-–—]\s*", "", role, flags=re.IGNORECASE)
    role = re.sub(r"^(?:job\s+)?title\s*[:\-–—]\s*", "", role, flags=re.IGNORECASE)
    role = re.sub(r"^(?:position|opening)\s*[:\-–—]\s*", "", role, flags=re.IGNORECASE)
    
    role = role.strip(" .,:;–—-_🔹•▪📍📌🌍💰🏢💻⏳📋✉️")
    
    # Handle placeholder roles
    if role.lower() in ("position", "role", "job", "hiring", "openings", "we are hiring"):
        if normalized_role and normalized_role.lower() not in ("unknown", "position"):
            n_lower = normalized_role.lower()
            return DISPLAY_ROLE_MAP.get(n_lower, normalized_role.replace("_", " ").title())
        return "Position"
        
    # If the role is too long or contains conversational phrases, clean it up
    if len(role) > 50 or re.search(r"\b(join|looking|hiring|expertise|experienced|strong|passionate|skilled)\b", role, re.IGNORECASE):
        # Try mapping to known roles if possible
        if normalized_role and normalized_role.lower() not in ("unknown", "position"):
            n_lower = normalized_role.lower()
            if n_lower in DISPLAY_ROLE_MAP:
                return DISPLAY_ROLE_MAP[n_lower]
                
        # Clean prefix phrases
        role = re.sub(r"^(?:looking for|hiring|we are looking for|urgent requirement for|opportunity for|seeking|we are hiring|an? experienced|a strong|genuinely passionate and skilled)\s+", "", role, flags=re.IGNORECASE)
        # Clean suffix phrases
        role = re.split(r"\s+(?:to join|with hands\-on|with expertise|for our|internship|part\s*time|full\s*time|contract|remote)\b", role, flags=re.IGNORECASE)[0]
        role = role.strip(" .,:;–—-_🔹•▪📍📌🌍💰🏢💻⏳📋✉️")
        
    if len(role) > 60:
        if normalized_role:
            n_lower = normalized_role.lower()
            return DISPLAY_ROLE_MAP.get(n_lower, normalized_role.replace("_", " ").title())
        return role[:50].strip()
        
    return role.strip(" .,:;–—-_🔹•▪📍📌🌍💰🏢💻⏳📋✉️") or "Position"

def clean_email(email: Optional[str]) -> Optional[str]:
    """Ensures email is clean and properly formatted using strict regex."""
    if not email:
        return None
    cleaned = str(email).lower().strip()
    # Remove trailing/leading punctuation
    cleaned = cleaned.rstrip(".,;:!) ]}")
    cleaned = cleaned.lstrip("([ {")
    
    # Strict regex check
    match = re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", cleaned)
    if match:
        return cleaned
        
    # Embedded search
    search_match = re.search(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", cleaned)
    if search_match:
        return search_match.group(0)
        
    return None

def clean_location(location: Optional[str]) -> str:
    """Cleans the location string."""
    if not location:
        return ""
    cleaned = re.sub(r"[\*\_#`]+", " ", str(location))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    # Strip common prefix labels (e.g. "Location: ")
    cleaned = re.sub(r"^(?:job\s+)?location\s*[:\-–—]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:work\s+)?location\s*[:\-–—]\s*", "", cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip(" .,:;–—-_🔹•▪📍📌🌍💰🏢💻⏳📋✉️")

def clean_jd_text(text: Optional[str]) -> str:
    """Removes unnecessary LinkedIn/social metadata, reaction counts, and action buttons from the JD.
    
    To prevent trimming critical information in the middle of a job posting,
    cleaning is only applied to the top 12 lines and the bottom 12 lines of the text.
    """
    if not text:
        return ""
        
    lines = text.splitlines()
    n_lines = len(lines)
    
    # Sanitization limits (number of lines at top and bottom to clean)
    top_limit = 12
    bottom_limit = 12
    
    cleaned_lines = []
    
    # Compile regexes for matching unwanted lines
    social_buttons = re.compile(r"^\s*(like|comment|repost|send|share|follow|view job|apply|connect|message)\s*$", re.IGNORECASE)
    metrics_patterns = re.compile(r"^\s*\d+\s*(reactions?|comments?|reposts?|shares?)\s*$", re.IGNORECASE)
    number_only = re.compile(r"^\s*\d+\s*$")
    time_posted = re.compile(r"^\s*\d+[hdmw]\s*•?\s*(edited)?\s*•?\s*$", re.IGNORECASE)
    time_ago = re.compile(r"\b\d+\s+(?:hour|day|minute|week|month)s?\s+ago\b", re.IGNORECASE)
    
    # Unwanted metadata phrases to check as substrings
    unwanted_substrings = (
        "actively reviewing applicants",
        "promoted by hirer",
        "responses managed off linkedin",
        "no response insights available",
        "company review time is typically",
        "view details",
        "try premium",
        "linkedin premium",
        "show more",
        "show less",
        "see more",
        "see less",
        "people clicked apply",
        "only connections can comment",
        "you can still react or share",
        "connection degree",
        "poster photo",
        "hiring team"
    )
    
    # Match strings containing applicant stats (e.g. "6 applicants", "over 100 people clicked apply")
    applicant_stats = re.compile(r"(\b\d+\s+applicants?\b|\b\d+\s+people clicked apply\b|\bover\s+\d+\s+people clicked apply\b)", re.IGNORECASE)
    
    for idx, line in enumerate(lines):
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue
            
        # Only clean lines in the top or bottom zones. Preserve middle lines completely.
        is_in_sanitization_zone = (
            n_lines <= (top_limit + bottom_limit) or
            idx < top_limit or
            idx >= (n_lines - bottom_limit)
        )
        
        if is_in_sanitization_zone:
            line_lower = line_strip.lower()
            
            # Check against patterns
            if social_buttons.match(line_strip):
                continue
            if metrics_patterns.match(line_strip):
                continue
            if number_only.match(line_strip):
                continue
            if time_posted.match(line_strip):
                continue
                
            # Check substring matches
            if any(sub in line_lower for sub in unwanted_substrings):
                continue
                
            # Check time ago strings in short metadata lines
            if time_ago.search(line_strip) and len(line_strip) < 80:
                continue
                
            if applicant_stats.search(line_strip):
                # Skip if the entire metadata line is relatively short
                if len(line_strip) < 100:
                    continue
                    
        cleaned_lines.append(line)
        
    # Reconstruct text and trim extra blank lines
    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()

def infer_company_from_layout(jd_text: str, job_role: str) -> Optional[str]:
    """Attempts to parse the company name using LinkedIn details page layout heuristics strictly."""
    if not jd_text or not job_role:
        return None
    lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
    role_lower = job_role.lower().strip()
    
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        
        # Strict match check
        is_strict_match = line_lower == role_lower
        if not is_strict_match and len(role_lower) > 8:
            if (role_lower in line_lower or line_lower in role_lower) and len(line_lower) - len(role_lower) < 15:
                if not any(w in line_lower for w in ("looking", "hiring", "experienced", "join", "team", "client")):
                    is_strict_match = True
                    
        if is_strict_match:
            candidate_after = lines[idx + 1] if idx + 1 < len(lines) else None
            candidate_before = lines[idx - 1] if idx - 1 >= 0 else None
            
            def is_location_like(s: str) -> bool:
                s_lower = s.lower()
                return any(loc in s_lower for loc in ("remote", "on-site", "hybrid", "india", "bengaluru", "bangalore", "mumbai", "delhi", "noida", "gurgaon", "hyderabad", "pune", "united states", "usa"))

            if candidate_before and is_valid_company_name(candidate_before):
                if candidate_after and (is_location_like(candidate_after) or not is_valid_company_name(candidate_after)):
                    return candidate_before
                    
            if candidate_after and is_valid_company_name(candidate_after) and not is_location_like(candidate_after):
                return candidate_after
                
    return None

def infer_location_from_layout(jd_text: str, job_role: str) -> Optional[str]:
    """Attempts to parse the location using LinkedIn details page layout heuristics strictly."""
    if not jd_text or not job_role:
        return None
    lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
    role_lower = job_role.lower().strip()
    
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        
        is_strict_match = line_lower == role_lower
        if not is_strict_match and len(role_lower) > 8:
            if (role_lower in line_lower or line_lower in role_lower) and len(line_lower) - len(role_lower) < 15:
                if not any(w in line_lower for w in ("looking", "hiring", "experienced", "join", "team", "client")):
                    is_strict_match = True
                    
        if is_strict_match:
            candidate_after = lines[idx + 1] if idx + 1 < len(lines) else None
            candidate_before = lines[idx - 1] if idx - 1 >= 0 else None
            
            def is_location_like(s: str) -> bool:
                s_lower = s.lower()
                return any(loc in s_lower for loc in ("remote", "on-site", "hybrid", "india", "bengaluru", "bangalore", "mumbai", "delhi", "noida", "gurgaon", "hyderabad", "pune", "united states", "usa"))

            if candidate_after:
                if is_location_like(candidate_after):
                    return candidate_after
                if idx + 2 < len(lines) and is_location_like(lines[idx + 2]):
                    return lines[idx + 2]
                    
            if candidate_before and is_location_like(candidate_before):
                return candidate_before
                
    return None

def sanitize_job_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitizes an entire job data dictionary."""
    email = clean_email(job.get("email"))
    jd_text = job.get("jd_text")
    raw_role = job.get("job_role")
    
    # 1. Clean email and JD text first
    jd_cleaned = clean_jd_text(jd_text)
    
    # 2. Try inferring company and location from layout before cleaning the role
    inferred_company = None
    inferred_location = None
    if raw_role and jd_cleaned:
        inferred_company = infer_company_from_layout(jd_cleaned, raw_role)
        inferred_location = infer_location_from_layout(jd_cleaned, raw_role)
        
    # 3. Clean company
    company = job.get("company_name")
    if not company or company.lower() in ("unknown", "position", "gmail", "gmail.com", "weintern", "") or not is_valid_company_name(company):
        if inferred_company:
            company = inferred_company
        else:
            company = clean_company_name(
                company, 
                email=email, 
                poster_name=job.get("poster_name"), 
                jd_text=jd_cleaned
            )
    else:
        company = clean_company_name(company, email=email)
        
    # 4. Clean role
    normalized_role = job.get("normalized_role")
    role = clean_job_role(raw_role, normalized_role=normalized_role)
    
    # 5. Clean location
    location = job.get("location")
    if not location or location.lower() in ("unknown", "position", ""):
        if inferred_location:
            location = inferred_location
        else:
            location = clean_location(location)
    else:
        location = clean_location(location)
        
    job["email"] = email
    job["company_name"] = company
    job["job_role"] = role
    job["location"] = location
    job["jd_text"] = jd_cleaned
    
    # Recalculate fingerprint for consistency
    company_clean = re.sub(r'[^a-z0-9]', '', company.lower()) if company else 'unknown'
    role_clean = normalized_role if normalized_role else 'unknown'
    loc_hint = job.get("location_hint") or ""
    loc_clean = loc_hint.lower().strip()[:50]
    job["job_fingerprint"] = f"{company_clean}:{role_clean}:{loc_clean}"
    
    return job
