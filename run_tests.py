#!/usr/bin/env python3
"""
Automated Test Runner for Code Quality Analyzer.
Discovers and runs all test suites in the tests/ directory.
"""
import unittest
import sys

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
