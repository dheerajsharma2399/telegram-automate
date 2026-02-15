"""
Integration tests for end-to-end workflows

Tests the complete message processing pipeline.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import asyncio


class TestMessageProcessingPipeline(unittest.TestCase):
    """Test end-to-end message processing"""
    
    @patch('main.db')
    @patch('main.llm_processor')
    def test_process_jobs_workflow(self, mock_llm, mock_db):
        """Test complete job processing workflow"""
        # Setup mocks
        mock_db.messages.get_unprocessed_messages.return_value = [
            {
                'id': 1,
                'message_text': 'Job posting: Software Engineer at Test Corp'
            }
        ]
        
        mock_llm.parse_jobs = AsyncMock(return_value=[
            {
                'company_name': 'Test Corp',
                'job_role': 'Software Engineer',
                'location': 'Remote'
            }
        ])
        
        mock_llm.process_job_data.return_value = {
            'job_id': 'test_123',
            'company_name': 'Test Corp',
            'job_role': 'Software Engineer',
            'location': 'Remote',
            'application_method': 'link'
        }
        
        mock_db.jobs.find_duplicate_processed_job.return_value = None
        mock_db.jobs.add_processed_job.return_value = 'test_123'
        
        # Run the workflow
        async def run_test():
            from main import process_jobs
            await process_jobs()
            
            # Verify workflow steps
            mock_db.messages.get_unprocessed_messages.assert_called_once()
            mock_db.messages.update_message_status.assert_called()
            mock_llm.parse_jobs.assert_called_once()
            mock_db.jobs.add_processed_job.assert_called_once()
        
        asyncio.run(run_test())


class TestInputValidation(unittest.TestCase):
    """Test input validation for web endpoints"""
    
    @patch('web_server.db')
    @patch('web_server.get_sheets_sync')
    def test_advanced_sync_validates_days_parameter(self, mock_sheets, mock_db):
        """Test that advanced_sync validates days parameter"""
        from web_server import app
        
        with app.test_client() as client:
            # Test invalid type
            response = client.post(
                '/api/sheets/advanced_sync',
                json={'days': 'invalid'}
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn('must be a valid integer', response.get_json()['error'])
            
            # Test out of range (too low)
            response = client.post(
                '/api/sheets/advanced_sync',
                json={'days': 0}
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn('between 1 and 365', response.get_json()['error'])
            
            # Test out of range (too high)
            response = client.post(
                '/api/sheets/advanced_sync',
                json={'days': 400}
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn('between 1 and 365', response.get_json()['error'])


class TestHealthCheckEndpoint(unittest.TestCase):
    """Test health check endpoint"""
    
    @patch('web_server.db')
    @patch('web_server.get_sheets_sync')
    def test_health_check_returns_200_when_healthy(self, mock_sheets, mock_db):
        """Test that health check returns 200 when all systems healthy"""
        from web_server import app
        
        # Mock healthy database
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn
        
        # Mock configured sheets
        mock_sheets_instance = Mock()
        mock_sheets_instance.client = Mock()
        mock_sheets.return_value = mock_sheets_instance
        
        with app.test_client() as client:
            response = client.get('/health')
            
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data['status'], 'healthy')
            self.assertEqual(data['checks']['database'], 'ok')
    
    @patch('web_server.db')
    @patch('web_server.get_sheets_sync')
    def test_health_check_returns_503_when_unhealthy(self, mock_sheets, mock_db):
        """Test that health check returns 503 when database fails"""
        from web_server import app
        
        # Mock database failure
        mock_db.get_connection.side_effect = Exception("Database connection failed")
        
        with app.test_client() as client:
            response = client.get('/health')
            
            self.assertEqual(response.status_code, 503)
            data = response.get_json()
            self.assertEqual(data['status'], 'unhealthy')
            self.assertIn('error', data['checks']['database'])


if __name__ == '__main__':
    unittest.main()
