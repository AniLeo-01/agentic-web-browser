# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An agentic web browser that accepts a website URL and simulates common agent tasks (finding pricing, product features, documentation, contact info). For each task, it determines whether the information was found, confidence level, and failure reasons. Think of it as **User Testing → Agent Testing**.

## Tech Stack

- **Agent**: smolagents `CodeAgent` with a vision-language model via `OpenAIModel` ([docs](https://huggingface.co/docs/smolagents/examples/web_browser))
- **Browser**: Selenium + Helium (headless Chrome) — agent writes/executes Python code to interact with pages
- **Backend**: FastAPI (async via `anyio.to_thread`)
- **Database**: DuckDB (single-file, persists all task results)
- **Python**: 3.11 (managed via `.python-version`)
- **Package manager**: uv (`uv sync` to install)

## Common Commands

```bash
uv run uvicorn app.main:app --reload   # dev server
uv run pytest tests/ -v                # run all tests
uv run pytest tests/test_api.py -v     # run a single test file
uv run pytest tests/test_api.py::test_browse_endpoint -v  # run a single test
```

## Architecture

### Request Flow

1. `POST /api/browse` (in `app/api/routes.py`) accepts a URL + list of tasks, creates an in-memory job, and spawns a background `asyncio.create_task`
2. Each task calls `run_agent_task()` (in `app/agent/browser.py`) which offloads to a thread via `anyio.to_thread.run_sync`
3. The sync runner acquires `_browser_lock` (only one browser at a time), creates a headless Chrome driver, builds a `CodeAgent` with Helium tools, and runs the prompt
4. Agent output is parsed: `NOT_FOUND:` prefix means failure; otherwise `CONFIDENCE: X.X\n<answer>` is extracted
5. `compute_scores()` (in `app/core/scoring.py`) evaluates the run across 5 weighted dimensions, result is persisted to DuckDB

### Key Modules

- **`app/agent/browser.py`** — Core agent orchestration. Creates Chrome driver, configures `CodeAgent`, handles screenshot callbacks, parses results. The `_browser_lock` ensures serial browser access.
- **`app/agent/tools.py`** — Custom smolagents `@tool` functions: `search_item_ctrl_f`, `go_back`, `close_popups`
- **`app/agent/prompts.py`** — Prompt templates including `HELIUM_INSTRUCTIONS` and `TASK_PROMPT_TEMPLATE`
- **`app/api/routes.py`** — All API endpoints. Jobs are stored in an in-memory `_jobs` dict (not persisted across restarts). Endpoints: `/api/browse`, `/api/jobs`, `/api/jobs/{id}`, `/api/results`, `/api/dashboard`, `/api/urls`, `/api/performance`
- **`app/core/scoring.py`** — Scoring weights: completeness (30%), confidence (25%), reliability (20%), efficiency (15%), speed (10%)
- **`app/core/db.py`** — DuckDB singleton connection, table init, all query functions including dashboard analytics and issue identification
- **`app/core/config.py`** — `pydantic-settings` `Settings` class, reads from `.env`. Key vars: `MODEL_ID`, `MODEL_API_KEY`, `MODEL_BASE_URL`, `DATABASE_PATH`, `AGENT_MAX_STEPS`
- **`app/core/models.py`** — Pydantic models: `TaskRequest`, `TaskResult`, `ScoreBreakdown`, `StepDetail`, `BrowseResponse`
- **`frontend/index.html`** — Single-file frontend served at `/`, static files at `/static`

### Concurrency Model

Browser access is serialized via `threading.Lock` — only one agent task runs at a time. Concurrent requests queue with a 5-minute timeout. The browser is always killed in a `finally` block.

### Testing

Tests use an in-memory DuckDB (`:memory:`) and mock the agent — no Chrome or model endpoint needed. Fixtures are in `tests/conftest.py`.

## Configuration

Create a `.env` file:

```env
MODEL_ID=google/gemma-4-31B-it
MODEL_API_KEY=your_api_key
MODEL_BASE_URL=https://your-model-endpoint/v1
DATABASE_PATH=data/browser.duckdb
AGENT_MAX_STEPS=20
DEBUG=true
```

## Standards

- Type hints required on all functions
- pytest for testing (fixtures in `tests/conftest.py`)
- PEP 8 with 100 character lines
