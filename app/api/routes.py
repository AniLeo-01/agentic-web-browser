from fastapi import APIRouter

from app.agent.browser import run_agent_task
from app.core.db import get_results, save_result
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
        )
    return BrowseResponse(url=url, results=results)


@router.get("/results")
async def results(url: str | None = None, limit: int = 50) -> list[dict]:
    return get_results(url=url, limit=limit)
