"""
Unit tests for LLM processor

Tests job parsing, timeout handling, and API error handling.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import aiohttp


class TestLLMProcessor(unittest.TestCase):
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
    def test_api_timeout_configuration(self, mock_session_class):
        """Test that API calls have 60-second timeout"""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            'choices': [{'message': {'content': '[]'}}]
        })
        
        mock_session.post.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Run async test
        async def run_test():
            await self.processor._call_llm_api(
                "test message",
                "test_key",
                "test_model"
            )
            
            # Verify timeout was set
            call_kwargs = mock_session.post.call_args[1]
            self.assertIn('timeout', call_kwargs)
            timeout = call_kwargs['timeout']
            self.assertEqual(timeout.total, 60)
        
        asyncio.run(run_test())
    
    def test_process_job_data_adds_metadata(self):
        """Test that process_job_data adds required metadata"""
        job_data = {
            'company_name': 'Test Corp',
            'job_role': 'Engineer'
        }
        
        result = self.processor.process_job_data(job_data, message_id=123)
        
        self.assertIn('job_id', result)
        self.assertIn('message_id', result)
        self.assertIn('updated_at', result)
        self.assertEqual(result['message_id'], 123)


class TestLLMErrorHandling(unittest.TestCase):
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
    def test_api_key_rotation_on_rate_limit(self, mock_session_class):
        """Test that API keys rotate on rate limit errors"""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 429  # Rate limit
        mock_response.text = AsyncMock(return_value="Rate limit exceeded")
        
        mock_session.post.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Run async test
        async def run_test():
            try:
                await self.processor._call_llm_api(
                    "test message",
                    "test_key",
                    "test_model"
                )
            except Exception:
                pass  # Expected to fail
            
            # Verify multiple attempts were made
            self.assertGreater(mock_session.post.call_count, 1)
        
        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
