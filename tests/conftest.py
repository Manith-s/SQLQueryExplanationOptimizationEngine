"""
Pytest configuration and fixtures.
"""

import os
import time
from pathlib import Path

import pytest

# #region agent log
LOG_PATH = Path(__file__).parent.parent / ".cursor" / "debug.log"
# #endregion


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


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Log test setup start."""
    # #region agent log
    try:
        with open(LOG_PATH, "a") as f:
            import json
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "test-setup",
                "hypothesisId": "A",
                "location": f"{item.nodeid}",
                "message": "test_setup_start",
                "data": {"test": item.nodeid, "timestamp": time.time()},
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except Exception:
        pass
    # #endregion


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    """Log test execution start."""
    # #region agent log
    try:
        with open(LOG_PATH, "a") as f:
            import json
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "test-execution",
                "hypothesisId": "B",
                "location": f"{item.nodeid}",
                "message": "test_execution_start",
                "data": {"test": item.nodeid, "timestamp": time.time()},
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except Exception:
        pass
    # #endregion


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item):
    """Log test teardown."""
    # #region agent log
    try:
        with open(LOG_PATH, "a") as f:
            import json
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "test-teardown",
                "hypothesisId": "C",
                "location": f"{item.nodeid}",
                "message": "test_teardown_complete",
                "data": {"test": item.nodeid, "timestamp": time.time()},
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except Exception:
        pass
    # #endregion
