import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter

from app.agent.browser import run_agent_task
from app.core.db import delete_all_results, delete_result, get_all_urls, get_dashboard_stats, get_results, get_url_performance, save_result
from app.core.models import TaskRequest

router = APIRouter()

# In-memory job store
_jobs: dict[str, dict] = {}


def _get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


async def _run_job(job_id: str, url: str, tasks: list[str]) -> None:
    """Run all tasks for a job in the background."""
    job = _jobs[job_id]
    for i, task in enumerate(tasks):
        job["current_task"] = i + 1
        try:
            outcome = await run_agent_task(url, task)
            result = {
                "task": task,
                **outcome,
            }
            job["results"].append(result)
            save_result(
                url=url,
                task=task,
                found=outcome["found"],
                confidence=outcome["confidence"],
                answer=outcome["answer"],
                error=outcome["error"],
                steps_taken=outcome["steps_taken"],
                duration_seconds=outcome["duration_seconds"],
                errors_encountered=outcome["errors_encountered"],
                scores=outcome["scores"],
                step_details=outcome.get("step_details"),
            )
        except Exception as e:
            job["results"].append({
                "task": task,
                "found": False,
                "confidence": 0.0,
                "answer": None,
                "error": str(e),
                "steps_taken": 0,
                "duration_seconds": 0.0,
                "errors_encountered": 1,
                "scores": {"completeness": 0, "confidence": 0, "efficiency": 0, "speed": 0, "reliability": 0, "overall": 0},
                "step_details": [],
            })
    job["status"] = "completed"
    job["completed_at"] = datetime.now().isoformat()


@router.post("/browse")
async def browse(request: TaskRequest) -> dict:
    """Submit a browse job. Returns immediately with a job_id."""
    url = str(request.url)
    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "url": url,
        "tasks": request.tasks,
        "status": "running",
        "current_task": 0,
        "results": [],
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }
    _jobs[job_id] = job
    asyncio.create_task(_run_job(job_id, url, request.tasks))
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs")
async def list_jobs() -> list[dict]:
    """List all jobs, newest first."""
    return sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    return job


@router.get("/results")
async def results(url: str | None = None, limit: int = 50) -> list[dict]:
    return get_results(url=url, limit=limit)


@router.get("/dashboard")
async def dashboard() -> dict:
    return get_dashboard_stats()


@router.get("/urls")
async def urls() -> list[str]:
    return get_all_urls()


@router.delete("/results/{result_id}")
async def remove_result(result_id: int) -> dict:
    """Delete a single result by ID."""
    if delete_result(result_id):
        return {"deleted": True, "id": result_id}
    return {"deleted": False, "error": "Result not found"}


@router.delete("/results")
async def remove_all_results() -> dict:
    """Delete all results."""
    count = delete_all_results()
    return {"deleted": True, "count": count}


@router.get("/performance")
async def performance(url: str) -> dict:
    return get_url_performance(url)
