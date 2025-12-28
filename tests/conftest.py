"""
Pytest configuration and fixtures.
"""

import os

import pytest


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-db-tests",
        action="store_true",
        default=False,
        help="Run database integration tests",
    )


def pytest_configure(config):
    """Configure pytest."""
    # Store the config for access in tests
    config.addinivalue_line(
        "markers",
        "db: marks tests as requiring database (deselect with '-m \"not db\"')",
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on markers."""
    if not config.getoption("--run-db-tests") and not os.environ.get("RUN_DB_TESTS"):
        skip_db = pytest.mark.skip(reason="Requires --run-db-tests or RUN_DB_TESTS=1")
        for item in items:
            if "db" in item.keywords:
                item.add_marker(skip_db)
