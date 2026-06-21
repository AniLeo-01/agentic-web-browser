from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


MOCK_SCORES = {
    "completeness": 1.0,
    "confidence": 0.8,
    "efficiency": 0.789,
    "speed": 1.0,
    "reliability": 1.0,
    "overall": 0.847,
}


def _mock_result(found: bool = True, answer: str | None = "$99/month", error: str | None = None) -> dict:
    return {
        "found": found,
        "confidence": 0.8 if found else 0.0,
        "answer": answer,
        "error": error,
        "steps_taken": 5,
        "duration_seconds": 30.0,
        "errors_encountered": 0,
        "scores": MOCK_SCORES if found else {
            "completeness": 0.0,
            "confidence": 0.0,
            "efficiency": 0.789,
            "speed": 1.0,
            "reliability": 0.75,
            "overall": 0.268,
        },
        "step_details": [
            {"step": 1, "reasoning": "Navigate to URL", "code": "go_to('https://example.com')", "observations": "Page loaded", "error": None},
            {"step": 2, "reasoning": "Look for pricing", "code": "click('Pricing')", "observations": "Found pricing page", "error": None},
        ] if found else [],
    }


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_browse(client: TestClient) -> None:
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=_mock_result()):
        response = client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find pricing"]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/"
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["found"] is True
    assert result["answer"] == "$99/month"
    assert result["scores"]["overall"] == 0.847
    assert result["steps_taken"] == 5


def test_browse_not_found(client: TestClient) -> None:
    mock = _mock_result(found=False, answer=None, error="Could not locate pricing page")
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=mock):
        response = client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find pricing"]},
        )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["found"] is False
    assert result["error"] == "Could not locate pricing page"
    assert result["scores"]["completeness"] == 0.0


def test_browse_saves_to_db(client: TestClient) -> None:
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=_mock_result(answer="support@example.com")):
        client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find contact email"]},
        )

    response = client.get("/api/results")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert results[0]["answer"] == "support@example.com"
    assert results[0]["score_overall"] == 0.847


def test_dashboard(client: TestClient) -> None:
    with patch("app.api.routes.run_agent_task", new_callable=AsyncMock, return_value=_mock_result()):
        client.post(
            "/api/browse",
            json={"url": "https://example.com", "tasks": ["Find pricing"]},
        )

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] >= 1
    assert "avg_scores" in data
    assert "by_url" in data
