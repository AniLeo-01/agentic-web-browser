import os

import pytest
from fastapi.testclient import TestClient

# Use in-memory DB and dummy model settings for tests
os.environ["DATABASE_PATH"] = ":memory:"
os.environ["MODEL_ID"] = "test-model"
os.environ["MODEL_BASE_URL"] = "http://localhost"
os.environ["MODEL_API_KEY"] = "test-key"

from app.core.db import close_connection
from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c
    close_connection()
