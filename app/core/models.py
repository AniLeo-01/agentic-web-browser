from pydantic import BaseModel, HttpUrl, field_validator


class TaskRequest(BaseModel):
    url: HttpUrl
    tasks: list[str]

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one task is required")
        if len(v) > 10:
            raise ValueError("Maximum 10 tasks per request")
        for task in v:
            if not task.strip():
                raise ValueError("Task cannot be empty")
        return [t.strip() for t in v]


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
