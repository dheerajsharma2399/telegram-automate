"""Unit tests for the deduper module."""

import unittest
from unittest.mock import MagicMock, patch
from deduper import make_fingerprint, simhash, hamming_distance, DedupAgent

class TestDeduper(unittest.TestCase):
    
    def test_make_fingerprint(self):
        # Normalization check
        fp1 = make_fingerprint("Google LLC!", "AI Engineer", "Remote, India")
        fp2 = make_fingerprint("google llc", "artificial intelligence engineer", "Remote")
        
        self.assertEqual(fp1, "googlellc:ai_engineer:remote,india")
        self.assertEqual(fp2, "googlellc:ai_engineer:remote")

    def test_simhash_and_hamming_distance(self):
        text_1 = "This is a job description for a backend Python developer with FastAPI experience."
        text_2 = "This is a job description for a backend Python developer with FastAPI experience!"
        text_3 = "We are hiring a front-end React developer with Tailwind CSS expertise."
        
        sim_1 = simhash(text_1)
        sim_2 = simhash(text_2)
        sim_3 = simhash(text_3)
        
        dist_1_2 = hamming_distance(sim_1, sim_2)
        dist_1_3 = hamming_distance(sim_1, sim_3)
        
        # Very similar texts should have Hamming distance < 3 (usually 0 or 1 depending on minor changes)
        self.assertLess(dist_1_2, 3)
        # Very different texts should have larger distance
        self.assertGreater(dist_1_3, 5)

    def test_dedup_agent_fingerprint_match(self):
        mock_db = MagicMock()
        mock_db.jobs.search_by_fingerprint.return_value = {"id": 1, "job_id": "test_1", "company_name": "Google"}
        
        agent = DedupAgent(mock_db)
        candidate = {
            "company_name": "Google",
            "job_role": "AI Engineer",
            "location": "India",
            "job_fingerprint": "google:ai_engineer:india"
        }
        
        matched, method = agent.find_duplicate(candidate)
        self.assertEqual(method, "fingerprint")
        self.assertEqual(matched["job_id"], "test_1")
        mock_db.jobs.search_by_fingerprint.assert_called_once_with("google:ai_engineer:india")

    def test_dedup_agent_email_match(self):
        mock_db = MagicMock()
        mock_db.jobs.search_by_fingerprint.return_value = None
        mock_db.jobs.search_by_email.return_value = {"id": 2, "job_id": "test_2", "email": "hr@google.com"}
        
        agent = DedupAgent(mock_db)
        candidate = {
            "company_name": "Google",
            "job_role": "AI Engineer",
            "location": "India",
            "email": "hr@google.com"
        }
        
        matched, method = agent.find_duplicate(candidate)
        self.assertEqual(method, "email")
        self.assertEqual(matched["job_id"], "test_2")
        mock_db.jobs.search_by_email.assert_called_once_with("hr@google.com")

if __name__ == "__main__":
    unittest.main()
