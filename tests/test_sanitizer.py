import unittest
from sanitizer import (
    clean_email,
    clean_location,
    clean_company_name,
    clean_job_role,
    extract_company_from_email,
    clean_jd_text,
    sanitize_job_record
)

class TestSanitizer(unittest.TestCase):
    def test_clean_email(self):
        self.assertEqual(clean_email(" hr@techcorp.com. "), "hr@techcorp.com")
        self.assertEqual(clean_email("Email: test@gmail.com;"), "test@gmail.com")  # Extracted from text
        self.assertEqual(clean_email("test@gmail.com"), "test@gmail.com")
        self.assertEqual(clean_email("no email here"), None)
        self.assertEqual(clean_email(None), None)

    def test_clean_location(self):
        self.assertEqual(clean_location("  Bangalore, India  "), "Bangalore, India")
        self.assertEqual(clean_location("**Remote**"), "Remote")
        self.assertEqual(clean_location(None), "")

    def test_extract_company_from_email(self):
        self.assertEqual(extract_company_from_email("hr@techcorp.com"), "Techcorp")
        self.assertEqual(extract_company_from_email("recruiter@sub.domain.co.in"), "Domain")
        self.assertEqual(extract_company_from_email("user@gmail.com"), None)
        self.assertEqual(extract_company_from_email(None), None)

    def test_clean_company_name(self):
        # Normal cleaning
        self.assertEqual(clean_company_name("**Google** Inc."), "Google Inc")
        # Replaces invalid/unknown placeholder with email domain
        self.assertEqual(clean_company_name("gmail", email="contact@microsoft.com"), "Microsoft")
        # Inferred from poster name
        self.assertEqual(clean_company_name("unknown", poster_name="Talent Acquisition @ Oracle Labs"), "Oracle Labs")
        # Inferred from JD text
        self.assertEqual(
            clean_company_name("Position", jd_text="Apply directly at our website. Company: Meta platforms"), 
            "Meta platforms"
        )
        # Fallback to Unknown
        self.assertEqual(clean_company_name("you. apply here", email="test@gmail.com"), "Unknown")

    def test_clean_job_role(self):
        # Standard cleaning
        self.assertEqual(clean_job_role("  **AI Engineer**  "), "AI Engineer")
        # Too long conversational roles mapped using normalized_role
        self.assertEqual(
            clean_job_role(
                "an experienced Python Developer with strong expertise in Django and Flask to join us.", 
                normalized_role="python_developer"
            ),
            "Python Developer"
        )
        # Placeholder roles mapped using normalized_role
        self.assertEqual(clean_job_role("Position", normalized_role="ml_engineer"), "Machine Learning Engineer")
        # Clean generic prefix/suffix
        self.assertEqual(clean_job_role("Looking for Frontend Developer to join our team"), "Frontend Developer")
        self.assertEqual(clean_job_role("Software Engineer with expertise in AWS"), "Software Engineer")
        # Default placeholder fallback
        self.assertEqual(clean_job_role("Job", normalized_role=None), "Position")

    def test_clean_jd_text(self):
        raw_jd = (
            "Delfi\n"
            "3h • Edited • \n"
            "Follow\n"
            "We are hiring a Software Engineer!\n"
            "React and Python required.\n"
            "Actively reviewing applicants\n"
            "35 reactions\n"
            "35\n"
            "1 comment\n"
            "Like\n"
            "Comment\n"
            "Repost\n"
            "Send"
        )
        expected = (
            "Delfi\n\n"
            "We are hiring a Software Engineer!\n"
            "React and Python required."
        )
        self.assertEqual(clean_jd_text(raw_jd), expected)

    def test_sanitize_job_record(self):
        job = {
            "company_name": "you. apply here",
            "job_role": "genuinely passionate Backend Developer",
            "email": "Hr@Techcorp.com.",
            "location": "  Remote  ",
            "jd_text": "We are hiring!\nLike\nComment",
            "normalized_role": "backend_developer",
            "location_hint": "remote"
        }
        sanitized = sanitize_job_record(job)
        self.assertEqual(sanitized["company_name"], "Techcorp")
        self.assertEqual(sanitized["job_role"], "Backend Developer")
        self.assertEqual(sanitized["email"], "hr@techcorp.com")
        self.assertEqual(sanitized["location"], "Remote")
        self.assertEqual(sanitized["jd_text"], "We are hiring!")
        self.assertEqual(sanitized["job_fingerprint"], "techcorp:backend_developer:remote")
