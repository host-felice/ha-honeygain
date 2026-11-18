import pytest
pytest_plugins = ["pytest_homeassistant_custom_component"]

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def login():
    """Honeygain's login request: accepted, unless a test changes it."""
    from unittest.mock import MagicMock, patch
    answer = MagicMock(status_code=200)
    answer.json.return_value = {"data": {"access_token": "t"}}
    with patch("custom_components.honeygain.requests.post", return_value=answer) as post:
        yield post
