# Test Suite for Telegram Job Scraper

This directory contains all tests for the Telegram Job Scraper application.

## Test Structure

```
tests/
├── __init__.py                 # Package initialization
├── test_config.py              # Configuration validation tests
├── test_database.py            # Database operations tests
├── test_llm_processor.py       # LLM job parsing tests
├── test_integration.py         # End-to-end integration tests
├── test_extraction_logic.py    # Job extraction logic tests (legacy)
├── test_link_extraction.py     # Link extraction tests (legacy)
├── test_pipeline.py            # Pipeline tests (legacy)
├── test_sheets_sync.py         # Sheets sync tests (legacy)
└── test_sync_fixes.py          # Sync fixes tests (legacy)
```

## Running Tests

### Run All Tests
```bash
python run_tests.py
```

### Run Only Unit Tests
```bash
python run_tests.py --unit
```

### Run Only Integration Tests
```bash
python run_tests.py --integration
```

### Run with Coverage
```bash
python run_tests.py --coverage
```

## Test Coverage

### Unit Tests
- **test_config.py**: Tests configuration validation (Phase 1)
  - Missing DATABASE_URL raises error
  - Missing Telegram API credentials raise error
  - Missing OpenRouter API key raises error
  - Missing Google credentials raise error
  - Valid configuration loads successfully
  - LOG_LEVEL is configurable

- **test_database.py**: Tests database operations (Phase 1 & 3)
  - Connection pool initialization with correct parameters
  - Connection pool exhaustion handling
  - Transaction rollback on errors
  - Successful transaction commits
  - Repository methods with rollback

- **test_llm_processor.py**: Tests LLM processing (Phase 4)
  - Processor initialization
  - JSON extraction from responses
  - Invalid JSON handling
  - API timeout configuration (60 seconds)
  - Job data metadata addition
  - API key rotation on rate limits

### Integration Tests
- **test_integration.py**: Tests end-to-end workflows (Phase 3)
  - Complete message processing pipeline
  - Input validation for web endpoints
  - Health check endpoint (200 when healthy, 503 when unhealthy)

## Writing New Tests

### Unit Test Template
```python
import unittest
from unittest.mock import Mock, patch

class TestYourFeature(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        pass
    
    def tearDown(self):
        """Clean up after tests"""
        pass
    
    def test_your_feature(self):
        """Test description"""
        # Arrange
        # Act
        # Assert
        pass

if __name__ == '__main__':
    unittest.main()
```

### Integration Test Template
```python
import unittest
from unittest.mock import patch
import asyncio

class TestYourIntegration(unittest.TestCase):
    @patch('module.dependency')
    def test_integration_workflow(self, mock_dep):
        """Test end-to-end workflow"""
        async def run_test():
            # Setup
            # Execute workflow
            # Verify results
            pass
        
        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
```

## Test Requirements

Tests use the following packages:
- `unittest` (built-in)
- `unittest.mock` (built-in)
- `asyncio` (built-in)

No additional test dependencies required!

## CI/CD Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run tests
  run: python run_tests.py

- name: Run tests with coverage
  run: python run_tests.py --coverage
```

## Test Maintenance

- Update tests when adding new features
- Ensure all critical paths are covered
- Keep tests independent and isolated
- Use mocks for external dependencies
- Follow AAA pattern (Arrange, Act, Assert)
