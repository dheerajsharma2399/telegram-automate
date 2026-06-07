"""
Unit tests for LLM processor

Tests job parsing, timeout handling, and API error handling.
"""

import sys
import types
if "aiohttp" in sys.modules and not isinstance(sys.modules["aiohttp"], types.ModuleType):
    del sys.modules["aiohttp"]

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
import aiohttp


class TestLLMProcessor(unittest.IsolatedAsyncioTestCase):
    """Test LLM processor functionality"""

    def setUp(self):
        """Set up test fixtures"""
        from llm_processor import LLMProcessor
        self.processor = LLMProcessor(
            api_keys=['test_key_1', 'test_key_2'],
            models=['test_model'],
            fallback_models=['fallback_model']
        )

    def test_processor_initialization(self):
        """Test that LLM processor initializes correctly"""
        self.assertEqual(len(self.processor.api_keys), 2)
        self.assertEqual(self.processor.models, ['test_model'])
        self.assertEqual(self.processor.fallback_models, ['fallback_model'])

    def test_extract_json_from_response(self):
        """Test JSON extraction from LLM response"""
        test_response = '''
        Here are the jobs:
        ```json
        [
            {
                "company_name": "Test Corp",
                "job_role": "Software Engineer",
                "location": "Remote"
            }
        ]
        ```
        '''

        result = self.processor._extract_json(test_response)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['company_name'], 'Test Corp')

    def test_extract_json_handles_invalid_json(self):
        """Test that invalid JSON returns None"""
        test_response = "This is not JSON"

        result = self.processor._extract_json(test_response)

        self.assertIsNone(result)

    @patch('aiohttp.ClientSession')
    async def test_api_timeout_configuration(self, mock_session_cls):
        """Test that API calls have 60-second timeout"""
        # Mock session object
        mock_session = MagicMock()

        # Setup ClientSession context manager
        # ClientSession() returns an object whose __aenter__ returns the session
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_cls.return_value = mock_session_ctx

        # Mock post response context manager
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': '[]'}}]
        }

        # Setup session.post context manager
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        mock_session.post.return_value = post_ctx

        # Run async test directly
        await self.processor._call_llm(
            "test message",
            "test_model",
            "test_key"
        )

        # Verify timeout was set
        call_kwargs = mock_session.post.call_args[1]
        self.assertIn('timeout', call_kwargs)
        timeout = call_kwargs['timeout']
        self.assertEqual(timeout.total, 60)

    def test_process_job_data_adds_metadata(self):
        """Test that process_job_data adds required metadata"""
        job_data = {
            'company_name': 'Test Corp',
            'job_role': 'Engineer'
        }

        result = self.processor.process_job_data(job_data, raw_message_id=123)

        self.assertIn('job_id', result)
        self.assertIn('raw_message_id', result)
        self.assertIn('updated_at', result)
        self.assertEqual(result['raw_message_id'], 123)

    def test_linkedin_prompt_dispatch_and_metadata_postprocessing(self):
        """LinkedIn source uses LinkedIn prompt and preserves source metadata."""
        from config import LINKEDIN_SYSTEM_PROMPT

        metadata = {
            'poster_name': 'Acme AI Careers',
            'poster_url': 'https://www.linkedin.com/company/acme-ai/',
            'source_url': 'https://www.linkedin.com/activity/1234567890',
            'company_name': 'Acme AI',
        }
        messages = self.processor._build_parse_messages(
            'Hiring Python Developer. Remote India. 0-2 years.',
            source='linkedin',
            source_metadata=metadata,
        )
        self.assertEqual(messages[0]['content'], LINKEDIN_SYSTEM_PROMPT)
        self.assertIn('LinkedIn metadata', messages[1]['content'])

        job = {
            'job_role': 'Python Developer',
            'company_name': None,
            'jd_text': 'Hiring Python Developer. Remote India. 0-2 years.',
        }
        processed = self.processor._apply_linkedin_postprocessing(
            job,
            'Hiring Python Developer. Remote India. 0-2 years.',
            source='linkedin',
            source_metadata=metadata,
        )
        self.assertEqual(processed['poster_name'], 'Acme AI Careers')
        self.assertEqual(processed['poster_url'], 'https://www.linkedin.com/company/acme-ai/')
        self.assertEqual(processed['post_url'], 'https://www.linkedin.com/activity/1234567890')
        self.assertEqual(processed['company_name'], 'Acme AI')
        self.assertEqual(processed['contact_method'], 'linkedin_post')
        self.assertEqual(processed['normalized_role'], 'python_developer')
        self.assertEqual(processed['location_hint'], 'remote,india')
        self.assertEqual(processed['experience_hint'], '0-2 years')
        self.assertEqual(processed['extraction_method'], 'llm_linkedin')
        self.assertGreaterEqual(processed['confidence_score'], 0.5)

    def test_linkedin_post_url_activity_and_dm_contact(self):
        """LinkedIn /activity URLs and DM-only posts are supported."""
        text = 'Hiring Backend Engineer. Message me on LinkedIn. https://www.linkedin.com/activity/1234567890'
        job = {'job_role': 'Backend Engineer'}
        processed = self.processor._apply_linkedin_postprocessing(job, text, source='linkedin')
        self.assertEqual(processed['post_url'], 'https://www.linkedin.com/activity/1234567890')
        self.assertEqual(processed['contact_method'], 'linkedin_dm')


class TestLLMErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test LLM error handling and retry logic"""

    def setUp(self):
        """Set up test fixtures"""
        from llm_processor import LLMProcessor
        self.processor = LLMProcessor(
            api_keys=['key1', 'key2', 'key3'],
            models=['model1'],
            fallback_models=['fallback1']
        )

    @patch('aiohttp.ClientSession')
    async def test_api_key_rotation_on_rate_limit(self, mock_session_cls):
        """Test that API keys rotate on rate limit errors"""
        # Mock session object
        mock_session = MagicMock()

        # Setup ClientSession context manager
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_cls.return_value = mock_session_ctx

        # Mock post response context manager
        mock_response = AsyncMock()
        mock_response.status = 429  # Rate limit
        mock_response.text.return_value = "Rate limit exceeded"

        # Setup session.post context manager
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        mock_session.post.return_value = post_ctx

        # Run async test directly
        # Use _try_pool instead of _call_llm to trigger retry logic
        await self.processor._try_pool(
            self.processor.models,
            "test message",
            max_retries=2,
            pool_name="Test"
        )

        # Verify multiple attempts were made
        # Since max_retries=2, we expect 2 session creations (since _call_llm creates session)
        self.assertEqual(mock_session_cls.call_count, 2)


if __name__ == '__main__':
    unittest.main()
