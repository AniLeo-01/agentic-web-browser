from pydantic import BaseModel, HttpUrl


class TaskRequest(BaseModel):
    url: HttpUrl
    tasks: list[str]


class TaskResult(BaseModel):
    task: str
    found: bool
    confidence: float
    answer: str | None = None
    error: str | None = None


class BrowseResponse(BaseModel):
    url: str
    results: list[TaskResult]
