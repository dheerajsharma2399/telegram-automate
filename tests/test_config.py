"""
Unit tests for configuration validation

Tests the fail-fast configuration validation implemented in Phase 1.
"""

import unittest
import os
from unittest.mock import patch


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation logic"""
    
    def setUp(self):
        """Set up test environment"""
        # Store original env vars
        self.original_env = os.environ.copy()

        # Patch load_dotenv to prevent reading actual .env file
        self.patcher = patch('dotenv.load_dotenv')
        self.mock_load_dotenv = self.patcher.start()

    def tearDown(self):
        """Restore original environment"""
        self.patcher.stop()
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_missing_database_url_raises_error(self):
        """Test that missing DATABASE_URL raises ValueError"""
        # Remove DATABASE_URL from environment
        if 'DATABASE_URL' in os.environ:
            del os.environ['DATABASE_URL']
        
        # Set other required vars
        os.environ['TELEGRAM_API_ID'] = '12345'
        os.environ['TELEGRAM_API_HASH'] = 'test_hash'
        os.environ['OPENROUTER_API_KEY'] = 'test_key'
        os.environ['GOOGLE_CREDENTIALS_JSON'] = 'test.json'
        os.environ['SPREADSHEET_ID'] = 'test_id'
        
        with self.assertRaises(ValueError) as context:
            # Import config module (triggers validation)
            import importlib
            import config
            importlib.reload(config)
        
        self.assertIn('DATABASE_URL', str(context.exception))
    
    def test_missing_telegram_api_raises_error(self):
        """Test that missing Telegram API credentials raise ValueError"""
        os.environ['DATABASE_URL'] = 'postgresql://test'
        if 'TELEGRAM_API_ID' in os.environ:
            del os.environ['TELEGRAM_API_ID']
        if 'TELEGRAM_API_HASH' in os.environ:
            del os.environ['TELEGRAM_API_HASH']
        
        with self.assertRaises(ValueError) as context:
            import importlib
            import config
            importlib.reload(config)
        
        self.assertIn('TELEGRAM_API', str(context.exception))
    
    def test_missing_openrouter_key_raises_error(self):
        """Test that missing OpenRouter API key raises ValueError"""
        os.environ['DATABASE_URL'] = 'postgresql://test'
        os.environ['TELEGRAM_API_ID'] = '12345'
        os.environ['TELEGRAM_API_HASH'] = 'test_hash'
        if 'OPENROUTER_API_KEY' in os.environ:
            del os.environ['OPENROUTER_API_KEY']
        
        with self.assertRaises(ValueError) as context:
            import importlib
            import config
            importlib.reload(config)
        
        self.assertIn('OPENROUTER_API_KEY', str(context.exception))
    
    def test_missing_google_credentials_raises_error(self):
        """Test that missing Google credentials raise ValueError"""
        os.environ['DATABASE_URL'] = 'postgresql://test'
        os.environ['TELEGRAM_API_ID'] = '12345'
        os.environ['TELEGRAM_API_HASH'] = 'test_hash'
        os.environ['OPENROUTER_API_KEY'] = 'test_key'
        if 'GOOGLE_CREDENTIALS_JSON' in os.environ:
            del os.environ['GOOGLE_CREDENTIALS_JSON']
        if 'SPREADSHEET_ID' in os.environ:
            del os.environ['SPREADSHEET_ID']
        
        with self.assertRaises(ValueError) as context:
            import importlib
            import config
            importlib.reload(config)
        
        self.assertIn('GOOGLE_CREDENTIALS_JSON', str(context.exception))
    
    def test_valid_configuration_loads_successfully(self):
        """Test that valid configuration loads without errors"""
        os.environ['DATABASE_URL'] = 'postgresql://user:pass@localhost/db'
        os.environ['TELEGRAM_API_ID'] = '12345'
        os.environ['TELEGRAM_API_HASH'] = 'abcdef1234567890'
        os.environ['OPENROUTER_API_KEY'] = 'sk-test-key'
        os.environ['GOOGLE_CREDENTIALS_JSON'] = './test_credentials.json'
        os.environ['SPREADSHEET_ID'] = '1234567890abcdef'
        
        try:
            import importlib
            import config
            importlib.reload(config)
            # If we get here, config loaded successfully
            self.assertTrue(True)
        except ValueError:
            self.fail("Valid configuration should not raise ValueError")
    
    def test_log_level_configuration(self):
        """Test that LOG_LEVEL is configurable"""
        # Set required variables to pass validation
        os.environ['DATABASE_URL'] = 'postgresql://user:pass@localhost/db'
        os.environ['TELEGRAM_API_ID'] = '12345'
        os.environ['TELEGRAM_API_HASH'] = 'abcdef1234567890'
        os.environ['OPENROUTER_API_KEY'] = 'sk-test-key'
        os.environ['GOOGLE_CREDENTIALS_JSON'] = './test_credentials.json'
        os.environ['SPREADSHEET_ID'] = '1234567890abcdef'

        # Set target variable
        os.environ['LOG_LEVEL'] = 'DEBUG'

        import importlib
        import config
        importlib.reload(config)

        self.assertEqual(config.LOG_LEVEL, 'DEBUG')


if __name__ == '__main__':
    unittest.main()
