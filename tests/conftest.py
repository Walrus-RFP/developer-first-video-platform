"""
pytest configuration for integration tests.
Skips tests gracefully when services are not running.
"""
import pytest
import requests
import os

CONTROL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
DATA    = os.getenv("DATA_PLANE_URL",    "http://localhost:8001")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_services: mark test as requiring running control+data plane services"
    )


def _service_running(url: str) -> bool:
    try:
        requests.get(url, timeout=3)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def check_services():
    """Warn (not fail) if services are not running; individual tests will skip."""
    control_up = _service_running(CONTROL)
    data_up    = _service_running(DATA)
    if not control_up or not data_up:
        import warnings
        warnings.warn(
            f"\nServices not detected: control={control_up}, data={data_up}. "
            "Start them before running integration tests."
        )
