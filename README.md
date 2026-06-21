# Agentic Web Browser

An AI-powered web browsing agent that accepts a website URL and performs user-defined tasks — like finding pricing information, product features, or contact details. For each task, the agent reports whether the information was found, its confidence level, and the extracted answer.

Think of it as **User Testing → Agent Testing**.

## How It Works

The agent uses a vision-language model combined with a headless Chrome browser (via Selenium + Helium) to navigate websites, take screenshots at each step, and reason about what it sees. The smolagents `CodeAgent` writes and executes Python code to interact with pages — clicking elements, scrolling, searching for text — and returns structured results.

## Tech Stack

- **Agent**: [smolagents](https://huggingface.co/docs/smolagents/examples/web_browser) with a vision-language model
- **Backend**: FastAPI (async via `anyio.to_thread`)
- **Database**: DuckDB (persists all task results)
- **Browser**: Selenium + Helium (headless Chrome)
- **Python**: 3.11+

## Project Structure

```
app/
├── main.py               # FastAPI app with lifespan (DB init/cleanup)
├── agent/
│   ├── browser.py         # Agent setup, Chrome driver, async task runner
│   ├── tools.py           # Browser tools (search, go_back, close_popups)
│   └── prompts.py         # Agent instructions and prompt templates
├── api/
│   └── routes.py          # POST /api/browse, GET /api/results
└── core/
    ├── config.py          # Settings from .env (pydantic-settings)
    ├── db.py              # DuckDB connection and queries
    └── models.py          # Pydantic request/response models
tests/
├── conftest.py            # TestClient fixture with in-memory DB
└── test_api.py            # API endpoint tests
```

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Chrome/Chromium installed
- An OpenAI-compatible VLM endpoint (or HuggingFace Inference API)

### Install

```bash
uv sync
```

### Configure

Create a `.env` file in the project root:

```env
MODEL_ID=google/gemma-4-31B-it
MODEL_API_KEY=your_api_key
MODEL_BASE_URL=https://your-model-endpoint/v1

DEBUG=true
DATABASE_PATH=data/browser.duckdb
AGENT_MAX_STEPS=20
```

### Run

```bash
uv run uvicorn app.main:app --reload
```

## API

### `POST /api/browse`

Submit a URL and a list of tasks for the agent to perform.

**Request:**
```json
{
  "url": "https://www.netflix.com",
  "tasks": ["Find the available subscription plans and their prices"]
}
```

**Response:**
```json
{
  "url": "https://www.netflix.com/",
  "results": [
    {
      "task": "Find the available subscription plans and their prices",
      "found": true,
      "confidence": 0.8,
      "answer": "Mobile (₹149/month), Basic (₹199/month), Standard (₹499/month), Premium (₹649/month)",
      "error": null
    }
  ]
}
```

### `GET /api/results`

Query stored results. Optionally filter by URL.

```
GET /api/results?url=https://www.netflix.com/&limit=10
```

### `GET /health`

Health check endpoint.

## Scoring

Each agent run is evaluated across five dimensions (0.0–1.0), combined into a weighted overall score:

| Dimension | Weight | Description |
|---|---|---|
| **Completeness** | 30% | Was the information found? Binary: 1.0 if found, 0.0 otherwise. |
| **Confidence** | 25% | Agent's self-reported confidence in its answer (0.0–1.0). |
| **Efficiency** | 15% | Fewer steps = better. 1 step = 1.0, scales linearly to 0.0 at max steps. |
| **Speed** | 10% | Under 60s = 1.0, scales linearly to 0.0 at 300s (5x baseline). |
| **Reliability** | 20% | No errors = 1.0, each code execution error reduces by 0.25. |

**Overall Score** = weighted average of all five dimensions.

The confidence score is self-reported by the LLM — the agent is prompted to rate its certainty from 0.0–1.0 based on how clearly the information was visible on the page.

### Dashboard Insights

The dashboard automatically analyzes run data to surface:

- **Top Issues Identified**: Key friction points like high failure rates, low confidence, excessive steps, slow runs, or frequent code errors — ranked by severity (high/medium/low).
- **Recommendations for Improvement**: Actionable suggestions based on the identified issues, such as improving task prompts, testing on simpler pages first, or addressing agent-unfriendly page patterns (login walls, CAPTCHAs, infinite scroll).
- **Per-URL Performance**: Select any tested URL to see its score breakdown, radar chart, and individual run details with expandable step-by-step agent reasoning.

### Step-Level Traceability

Each run stores per-step details: the agent's reasoning, the code it executed, its observations, and any errors. This enables debugging why a particular run failed or scored low.

## Concurrency & Safety

- **Browser lock**: Only one agent task runs at a time. Concurrent requests queue with a 5-minute timeout to prevent resource conflicts on the shared headless Chrome instance.
- **Request validation**: Maximum 10 tasks per request, no empty tasks allowed.
- **Timeout**: Agent tasks are bounded by `AGENT_MAX_STEPS` (default 20) and a 300-second wall-clock limit.
- **Browser crash recovery**: The browser is always killed in a `finally` block, with exception handling to prevent cleanup failures from propagating.

## Testing

```bash
uv run pytest tests/ -v
```

Tests use an in-memory DuckDB and mock the agent, so no Chrome or model endpoint is needed.
