import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        app_name="AlaiLink",
        environment="test",
        llm_api_key=None,
        llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
