"""
Test runner for Telegram Job Scraper

Runs all unit tests and integration tests, generates coverage report.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --unit             # Run only unit tests
    python run_tests.py --integration      # Run only integration tests
    python run_tests.py --coverage         # Run with coverage report
"""

import unittest
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def run_all_tests(test_type='all', with_coverage=False):
    """Run test suite"""
    
    # Discover tests
    loader = unittest.TestLoader()
    
    if test_type == 'unit':
        # Run only unit tests
        suite = unittest.TestSuite()
        suite.addTests(loader.loadTestsFromName('tests.test_config'))
        suite.addTests(loader.loadTestsFromName('tests.test_database'))
        suite.addTests(loader.loadTestsFromName('tests.test_llm_processor'))
    elif test_type == 'integration':
        # Run only integration tests
        suite = loader.loadTestsFromName('tests.test_integration')
    else:
        # Run all tests
        suite = loader.discover('tests', pattern='test_*.py')
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print("="*70)
    
    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Telegram Job Scraper tests')
    parser.add_argument('--unit', action='store_true', help='Run only unit tests')
    parser.add_argument('--integration', action='store_true', help='Run only integration tests')
    parser.add_argument('--coverage', action='store_true', help='Run with coverage report')
    
    args = parser.parse_args()
    
    # Determine test type
    if args.unit:
        test_type = 'unit'
    elif args.integration:
        test_type = 'integration'
    else:
        test_type = 'all'
    
    # Run tests
    exit_code = run_all_tests(test_type, args.coverage)
    sys.exit(exit_code)
