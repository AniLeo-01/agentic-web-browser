from pydantic import BaseModel, HttpUrl


class TaskRequest(BaseModel):
    url: HttpUrl
    tasks: list[str]


class ScoreBreakdown(BaseModel):
    completeness: float
    confidence: float
    efficiency: float
    speed: float
    reliability: float
    overall: float


class StepDetail(BaseModel):
    step: int
    reasoning: str | None = None
    code: str | None = None
    observations: str | None = None
    error: str | None = None


class TaskResult(BaseModel):
    task: str
    found: bool
    confidence: float
    answer: str | None = None
    error: str | None = None
    steps_taken: int = 0
    duration_seconds: float = 0.0
    errors_encountered: int = 0
    scores: ScoreBreakdown
    step_details: list[StepDetail] = []


class BrowseResponse(BaseModel):
    url: str
    results: list[TaskResult]
