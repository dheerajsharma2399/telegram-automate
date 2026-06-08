import unittest
from sanitizer import (
    clean_email,
    clean_location,
    clean_company_name,
    clean_job_role,
    extract_company_from_email,
    clean_jd_text,
    infer_company_from_layout,
    infer_location_from_layout,
    is_valid_company_name,
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
        self.assertEqual(clean_location("📍 Mumbai"), "Mumbai")
        self.assertEqual(clean_location("Location: Hitec City, Hyderabad"), "Hitec City, Hyderabad")

    def test_extract_company_from_email(self):
        self.assertEqual(extract_company_from_email("hr@techcorp.com"), "Techcorp")
        self.assertEqual(extract_company_from_email("recruiter@sub.domain.co.in"), "Domain")
        self.assertEqual(extract_company_from_email("user@gmail.com"), None)
        self.assertEqual(extract_company_from_email(None), None)

    def test_is_valid_company_name(self):
        self.assertTrue(is_valid_company_name("Google Inc"))
        self.assertTrue(is_valid_company_name("Meta Platforms"))
        self.assertTrue(is_valid_company_name("HELM Talent"))
        self.assertFalse(is_valid_company_name("- Machine learning & model development"))
        self.assertFalse(is_valid_company_name("🔹 Key Skills:"))
        self.assertFalse(is_valid_company_name("Location: San Diego, California"))
        self.assertFalse(is_valid_company_name("Atlanta, Georgia"))
        self.assertFalse(is_valid_company_name("apply here"))
        self.assertFalse(is_valid_company_name("Talent Acquisition"))

    def test_clean_company_name(self):
        # Normal cleaning
        self.assertEqual(clean_company_name("**Google** Inc."), "Google Inc")
        # Emoji / bullet stripping
        self.assertEqual(clean_company_name("🏢 Google Inc."), "Google Inc")
        # Label prefix stripping
        self.assertEqual(clean_company_name("Company: Google"), "Google")
        # Replaces invalid/unknown placeholder with email domain
        self.assertEqual(clean_company_name("gmail", email="contact@microsoft.com"), "Microsoft")
        # Inferred from poster name
        self.assertEqual(clean_company_name("unknown", poster_name="Talent Acquisition @ Oracle Labs"), "Oracle Labs")
        # Inferred from JD text
        self.assertEqual(
            clean_company_name("Position", jd_text="Apply directly at our website. Company: Meta platforms"), 
            "Meta platforms"
        )
        # Fallback to Unknown for bullet points or locations
        self.assertEqual(clean_company_name("- Machine learning & model development"), "Unknown")
        self.assertEqual(clean_company_name("you. apply here", email="test@gmail.com"), "Unknown")

    def test_clean_job_role(self):
        # Standard cleaning
        self.assertEqual(clean_job_role("  **AI Engineer**  "), "AI Engineer")
        # Emojis and bullet points stripping
        self.assertEqual(clean_job_role("🔹 Python Developer"), "Python Developer")
        self.assertEqual(clean_job_role("• AI Intern"), "AI Intern")
        # Label prefix stripping
        self.assertEqual(clean_job_role("Role: Front End Developer"), "Front End Developer")
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
            "Send\n"
            "Promoted by hirer · Responses managed off LinkedIn\n"
            "Company review time is typically 1 week\n"
            "Only connections can comment on this post. You can still react or share it.\n"
            "Bengaluru South, Karnataka, India · 2 hours ago · 22 people clicked apply\n"
            "Try Premium free"
        )
        expected = (
            "Delfi\n"
            "We are hiring a Software Engineer!\n"
            "React and Python required."
        )
        self.assertEqual(clean_jd_text(raw_jd), expected)

    def test_clean_jd_text_middle_preserved(self):
        # Long JD with 26 lines total.
        # Top 12 lines and bottom 12 lines are sanitised.
        # Lines 13 and 14 (indices 12 and 13) are middle lines and should be preserved.
        lines = [
            "Follow", # Top line - should be cleaned
            "We are hiring!",
            "Line 3", "Line 4", "Line 5", "Line 6", "Line 7", "Line 8", "Line 9", "Line 10", "Line 11", "Line 12",
            "This is a middle line that contains the word like and apply.", # Index 12 - should NOT be cleaned
            "Another middle line with comment and repost.", # Index 13 - should NOT be cleaned
            "Line 15", "Line 16", "Line 17", "Line 18", "Line 19", "Line 20", "Line 21", "Line 22", "Line 23", "Line 24",
            "Try Premium free", # Bottom line - should be cleaned
            "Like" # Bottom line - should be cleaned
        ]
        raw_jd = "\n".join(lines)
        cleaned = clean_jd_text(raw_jd)
        
        # Verify that "Follow", "Try Premium free", and "Like" were removed
        self.assertNotIn("Follow", cleaned)
        self.assertNotIn("Try Premium free", cleaned)
        self.assertNotIn("Like", cleaned)
        
        # Verify that the middle lines containing "like", "apply", "comment" were preserved intact
        self.assertIn("This is a middle line that contains the word like and apply.", cleaned)
        self.assertIn("Another middle line with comment and repost.", cleaned)


    def test_infer_company_from_layout(self):
        jd1 = (
            "Engineering challenges? Apply here 👇\n"
            "Software Developer III (Full Stack)\n"
            "HighLevel\n"
            "Delhi (Remote)"
        )
        self.assertEqual(infer_company_from_layout(jd1, "Software Developer III (Full Stack)"), "HighLevel")

        jd2 = (
            "Meta\n"
            "Research Scientist\n"
            "London, UK (On-site)"
        )
        self.assertEqual(infer_company_from_layout(jd2, "Research Scientist"), "Meta")
        
        # Test false positive check
        jd3 = (
            "Looking for a strong AI Engineer with experience across:\n"
            "- Machine learning & model development"
        )
        self.assertEqual(infer_company_from_layout(jd3, "AI Engineer"), None)

    def test_infer_location_from_layout(self):
        jd = (
            "Engineering challenges? Apply here 👇\n"
            "Software Developer III (Full Stack)\n"
            "HighLevel\n"
            "Delhi (Remote)"
        )
        self.assertEqual(infer_location_from_layout(jd, "Software Developer III (Full Stack)"), "Delhi (Remote)")

    def test_sanitize_job_record(self):
        job = {
            "company_name": "you. apply here",
            "job_role": "Software Developer III (Full Stack)",
            "email": "Hr@Techcorp.com.",
            "location": "unknown",
            "jd_text": "Software Developer III (Full Stack)\nHighLevel\nDelhi (Remote)",
            "normalized_role": "fullstack_developer",
            "location_hint": "remote"
        }
        sanitized = sanitize_job_record(job)
        self.assertEqual(sanitized["company_name"], "HighLevel")
        self.assertEqual(sanitized["job_role"], "Software Developer III (Full Stack)")
        self.assertEqual(sanitized["email"], "hr@techcorp.com")
        self.assertEqual(sanitized["location"], "Delhi (Remote)")
        self.assertEqual(sanitized["job_fingerprint"], "highlevel:fullstack_developer:remote")
UnitTestsRun = True
