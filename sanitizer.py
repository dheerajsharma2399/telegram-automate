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
    
    invalid_patterns = (
        "unknown", "position", "role", "job", "you. apply here", 
        "gmail", "gmail.com", "yahoo", "outlook", "weintern"
    )
    is_invalid = not name or name.lower() in invalid_patterns or any(pat in name.lower() for pat in ("apply here", "looking for you"))
    
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
                if clean_p:
                    return clean_p
                    
        # 3. Try parsing from JD text
        if jd_text:
            match = re.search(r"(?:company|organisation|organization|employer)\s*[:\-–—]\s*([A-Za-z0-9 &.,'()\-]{2,50})", jd_text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if candidate.lower() not in invalid_patterns:
                    return candidate
                    
        return "Unknown"
        
    return name.strip(" .,:;–—-_")

def clean_job_role(job_role: Optional[str], normalized_role: Optional[str] = None) -> str:
    """Cleans up job roles, trimming sentences and mapping placeholders."""
    if not job_role:
        role = ""
    else:
        role = str(job_role)
        
    # Strip markdown and junk characters
    role = re.sub(r"[\*\_#`\-\|]+", " ", role)
    role = re.sub(r"\s+", " ", role).strip()
    
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
        role = role.strip(" .,:;–—-_")
        
    if len(role) > 60:
        if normalized_role:
            n_lower = normalized_role.lower()
            return DISPLAY_ROLE_MAP.get(n_lower, normalized_role.replace("_", " ").title())
        return role[:50].strip()
        
    return role.strip(" .,:;–—-_") or "Position"

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
    return re.sub(r"\s+", " ", cleaned).strip().strip(" .,:;–—-_")

def clean_jd_text(text: Optional[str]) -> str:
    """Removes unnecessary LinkedIn/social metadata, reaction counts, and action buttons from the JD."""
    if not text:
        return ""
        
    lines = text.splitlines()
    cleaned_lines = []
    
    # Compile regexes for matching unwanted lines
    social_buttons = re.compile(r"^\s*(like|comment|repost|send|share|follow|view job|apply)\s*$", re.IGNORECASE)
    metrics_patterns = re.compile(r"^\s*\d+\s*(reactions?|comments?|reposts?|shares?)\s*$", re.IGNORECASE)
    number_only = re.compile(r"^\s*\d+\s*$")
    time_posted = re.compile(r"^\s*\d+[hdmw]\s*•?\s*(edited)?\s*•?\s*$", re.IGNORECASE)
    applicant_metadata = re.compile(r"^\s*(actively reviewing applicants|promoted by hirer|responses managed off linkedin|no response insights available|company review time is typically|view details)\s*$", re.IGNORECASE)
    
    # Match strings containing applicant stats (e.g. "6 applicants", "over 100 people clicked apply", "India · 40 minutes ago · 6 applicants")
    applicant_stats = re.compile(r"(\b\d+\s+applicants?\b|\bover\s+\d+\s+(?:applicants|people clicked apply)\b)", re.IGNORECASE)
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue
            
        # Check against patterns
        if social_buttons.match(line_strip):
            continue
        if metrics_patterns.match(line_strip):
            continue
        if number_only.match(line_strip):
            continue
        if time_posted.match(line_strip):
            continue
        if applicant_metadata.match(line_strip):
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

def sanitize_job_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitizes an entire job data dictionary."""
    email = clean_email(job.get("email"))
    company = clean_company_name(
        job.get("company_name"), 
        email=email, 
        poster_name=job.get("poster_name"), 
        jd_text=job.get("jd_text")
    )
    normalized_role = job.get("normalized_role")
    role = clean_job_role(job.get("job_role"), normalized_role=normalized_role)
    location = clean_location(job.get("location"))
    jd_cleaned = clean_jd_text(job.get("jd_text"))
    
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
