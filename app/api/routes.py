from fastapi import APIRouter

from app.agent.browser import run_agent_task
from app.core.db import get_all_urls, get_dashboard_stats, get_results, get_url_performance, save_result
from app.core.models import BrowseResponse, TaskRequest, TaskResult

router = APIRouter()


@router.post("/browse", response_model=BrowseResponse)
async def browse(request: TaskRequest) -> BrowseResponse:
    url = str(request.url)
    results = []
    for task in request.tasks:
        outcome = await run_agent_task(url, task)
        task_result = TaskResult(task=task, **outcome)
        results.append(task_result)
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
    return BrowseResponse(url=url, results=results)


@router.get("/results")
async def results(url: str | None = None, limit: int = 50) -> list[dict]:
    return get_results(url=url, limit=limit)


@router.get("/dashboard")
async def dashboard() -> dict:
    return get_dashboard_stats()


@router.get("/urls")
async def urls() -> list[str]:
    return get_all_urls()


@router.get("/performance")
async def performance(url: str) -> dict:
    return get_url_performance(url)
