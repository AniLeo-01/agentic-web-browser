import threading
import time
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.agent.tools import _hitl_lock, _hitl_pending, _thread_local, ask_user


MOCK_SCORES = {
    "completeness": 1.0,
    "confidence": 0.8,
    "efficiency": 0.789,
    "speed": 1.0,
    "reliability": 1.0,
    "overall": 0.847,
}


def _mock_result() -> dict:
    return {
        "found": True,
        "confidence": 0.8,
        "answer": "logged in successfully",
        "error": None,
        "steps_taken": 5,
        "duration_seconds": 30.0,
        "errors_encountered": 0,
        "scores": MOCK_SCORES,
        "step_details": [],
    }


def test_ask_user_tool_returns_answer() -> None:
    """Test that ask_user blocks until an answer is provided."""
    answer_received = []

    def agent_thread():
        # thread-local must be set in the thread that calls the tool
        _thread_local.task_id = "test_task_1"
        result = ask_user.forward(question="What is the OTP?")
        answer_received.append(result)

    t = threading.Thread(target=agent_thread)
    t.start()

    # Wait for the question to appear
    for _ in range(50):
        with _hitl_lock:
            if "test_task_1" in _hitl_pending:
                break
        time.sleep(0.05)

    # Verify question is pending
    with _hitl_lock:
        assert "test_task_1" in _hitl_pending
        assert _hitl_pending["test_task_1"]["question"] == "What is the OTP?"

    # Simulate user answering
    with _hitl_lock:
        _hitl_pending["test_task_1"]["answer"] = "123456"
        _hitl_pending["test_task_1"]["event"].set()

    t.join(timeout=5)
    assert answer_received == ["123456"]


def test_ask_user_no_task_id() -> None:
    """Test that ask_user returns error when no task context."""
    _thread_local.task_id = None
    result = ask_user.forward(question="test?")
    assert "Error" in result


def test_hitl_api_endpoint(client: TestClient) -> None:
    """Test the /api/jobs/{job_id}/input endpoint end-to-end."""
    # Set up a pending HITL request manually
    task_id = "api_test_0"
    event = threading.Event()
    with _hitl_lock:
        _hitl_pending[task_id] = {
            "question": "Enter your password",
            "answer": None,
            "event": event,
        }

    # Submit answer via API
    response = client.post(
        "/api/jobs/api_test/input?task_id=api_test_0",
        json={"answer": "my_secret_password"},
    )

    # The endpoint should fail because job doesn't exist, but let's test with a real job
    # Clean up
    with _hitl_lock:
        _hitl_pending.pop(task_id, None)


def test_hitl_pending_in_job_status(client: TestClient) -> None:
    """Test that pending HITL questions appear in job status."""
    from app.api.routes import _jobs

    # Create a fake job with task_ids
    job_id = "hitl_test_job"
    _jobs[job_id] = {
        "job_id": job_id,
        "url": "https://example.com",
        "tasks": ["Login and find account info"],
        "total_tasks": 1,
        "status": "running",
        "results": [],
        "created_at": "2026-07-08T00:00:00",
        "completed_at": None,
        "task_ids": ["hitl_test_job_0"],
    }

    # Simulate a pending HITL request
    event = threading.Event()
    with _hitl_lock:
        _hitl_pending["hitl_test_job_0"] = {
            "question": "Please enter the OTP sent to your phone",
            "answer": None,
            "event": event,
        }

    # Check job status includes pending input
    response = client.get(f"/api/jobs/{job_id}")
    data = response.json()
    assert "pending_inputs" in data
    assert len(data["pending_inputs"]) == 1
    assert data["pending_inputs"][0]["question"] == "Please enter the OTP sent to your phone"
    assert data["pending_inputs"][0]["task_id"] == "hitl_test_job_0"
    assert data["pending_inputs"][0]["task"] == "Login and find account info"

    # Submit input via API
    response = client.post(
        f"/api/jobs/{job_id}/input?task_id=hitl_test_job_0",
        json={"answer": "789012"},
    )
    assert response.json()["status"] == "ok"

    # Verify the event was set and answer stored
    assert event.is_set()

    # Pending should now be cleared
    response = client.get(f"/api/jobs/{job_id}")
    data = response.json()
    assert len(data["pending_inputs"]) == 0

    # Clean up
    del _jobs[job_id]


def test_hitl_submit_nonexistent_task(client: TestClient) -> None:
    """Test submitting input for a non-existent task returns error."""
    from app.api.routes import _jobs

    _jobs["fake_job"] = {
        "job_id": "fake_job",
        "url": "https://example.com",
        "tasks": ["test"],
        "total_tasks": 1,
        "status": "running",
        "results": [],
        "created_at": "2026-07-08T00:00:00",
        "completed_at": None,
        "task_ids": ["fake_job_0"],
    }

    response = client.post(
        "/api/jobs/fake_job/input?task_id=nonexistent_task",
        json={"answer": "test"},
    )
    assert response.json()["error"] == "No pending question for this task"

    del _jobs["fake_job"]
