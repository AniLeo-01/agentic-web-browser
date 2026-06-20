from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_browse(client: TestClient) -> None:
    mock_result = {
        "found": True,
        "confidence": 0.8,
        "answer": "$99/month",
        "error": None,
    }
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
        response = client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find pricing"]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/"
    assert len(data["results"]) == 1
    assert data["results"][0]["found"] is True
    assert data["results"][0]["answer"] == "$99/month"
    assert data["results"][0]["task"] == "Find pricing"


def test_browse_not_found(client: TestClient) -> None:
    mock_result = {
        "found": False,
        "confidence": 0.0,
        "answer": None,
        "error": "Could not locate pricing page",
    }
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
        response = client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find pricing"]},
        )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["found"] is False
    assert result["error"] == "Could not locate pricing page"


def test_browse_saves_to_db(client: TestClient) -> None:
    mock_result = {
        "found": True,
        "confidence": 0.9,
        "answer": "support@example.com",
        "error": None,
    }
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
        client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find contact email"]},
        )

    response = client.get("/api/results")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert results[0]["answer"] == "support@example.com"
    assert results[0]["task"] == "Find contact email"


def test_results_filter_by_url(client: TestClient) -> None:
    mock_result = {
        "found": True,
        "confidence": 0.7,
        "answer": "Some answer",
        "error": None,
    }
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
        client.post(
            "/api/browse",
            json={"url": "https://a.com", "tasks": ["task1"]},
        )
        client.post(
            "/api/browse",
            json={"url": "https://b.com", "tasks": ["task2"]},
        )

    response = client.get("/api/results", params={"url": "https://a.com/"})
    results = response.json()
    assert all(r["url"] == "https://a.com/" for r in results)
