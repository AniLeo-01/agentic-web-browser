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
│   └── routes.py          # POST /api/browse, GET /api/results, dashboard endpoints
└── core/
    ├── config.py          # Settings from .env (pydantic-settings)
    ├── db.py              # DuckDB connection and queries
    ├── models.py          # Pydantic request/response models
    └── scoring.py         # Scoring formulas and weights
frontend/
└── index.html             # Single-file dashboard UI
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

Then open [http://localhost:8000](http://localhost:8000) to access the dashboard.

## API

### `POST /api/browse`

Submit a URL and a list of tasks for the agent to perform. Returns immediately with a `job_id` — tasks run asynchronously in the background.

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
  "job_id": "a1b2c3d4e5f6",
  "status": "running"
}
```

### `GET /api/jobs/{job_id}`

Poll for job status and results.

### `GET /api/jobs`

List all jobs, newest first.

### `GET /api/results`

Query stored results. Optionally filter by URL.

```
GET /api/results?url=https://www.netflix.com/&limit=10
```

### `GET /api/dashboard`

Aggregated stats across all runs: average scores, per-URL breakdown, top issues, and recommendations.

### `GET /api/performance?url=...`

Detailed performance breakdown for a single URL, including all individual runs.

### `GET /api/urls`

List all distinct URLs that have been tested.

### `GET /health`

Health check endpoint.

## Scoring

Each agent run produces an **Agent Readiness Score** — a composite metric reflecting how well an agent can navigate and extract information from the target site. The score is computed across five dimensions, each rated 0.0–1.0, then combined via weighted average.

### Dimensions

| Dimension | Weight | Formula |
|---|---|---|
| **Completeness** | 30% | `1.0` if the information was found, `0.0` otherwise. |
| **Confidence** | 25% | The agent's self-reported certainty (0.0–1.0), clamped to that range. |
| **Efficiency** | 15% | `1.0 - (steps_taken - 1) / (max_steps - 1)`. 1 step = perfect, max steps = 0. |
| **Speed** | 10% | `1.0` if under 60s. Above 60s, scales linearly to `0.0` at 300s. |
| **Reliability** | 20% | `1.0 - (errors * 0.25)`. Each code execution error costs 0.25. Capped at 0.5 if the task failed. |

**Overall Score** = `0.30 * completeness + 0.25 * confidence + 0.20 * reliability + 0.15 * efficiency + 0.10 * speed`

### Confidence Scoring

The confidence score is self-reported by the LLM. The agent is prompted to rate its certainty based on how clearly the information was visible on the page:

| Range | Meaning |
|---|---|
| 0.9–1.0 | Information clearly visible, directly matches the task |
| 0.7–0.8 | Information found but may be incomplete or partially inferred |
| 0.4–0.6 | Information is ambiguous, possibly outdated, or required guessing |
| 0.1–0.3 | Very uncertain, could not verify the information |

If the agent cannot find the information at all, it returns `NOT_FOUND` with a reason, and the run scores 0 for both completeness and confidence.

### Dashboard Insights

The dashboard automatically analyzes run data to surface:

- **Overall Agent Readiness Score**: The composite weighted score across all runs.
- **Top Issues Identified**: Key friction points like high failure rates, low confidence, excessive steps, slow runs, or frequent code errors — ranked by severity (high/medium/low).
- **Recommendations for Improvement**: Actionable suggestions based on the identified issues, such as improving task prompts, testing on simpler pages first, or addressing agent-unfriendly page patterns.
- **Per-URL Performance**: Select any tested URL to see its score breakdown, radar chart, and individual run details with expandable step-by-step agent reasoning.

### Step-Level Traceability

Each run stores per-step details: the agent's reasoning, the code it executed, its observations, and any errors. This enables debugging why a particular run failed or scored low.

## Concurrency & Safety

- **Browser lock**: Only one agent task runs at a time. Concurrent requests queue with a 5-minute timeout to prevent resource conflicts on the shared headless Chrome instance.
- **Request validation**: Maximum 10 tasks per request, no empty tasks allowed.
- **Timeout**: Agent tasks are bounded by `AGENT_MAX_STEPS` (default 20) and a 300-second wall-clock limit.
- **Browser crash recovery**: The browser is always killed in a `finally` block, with exception handling to prevent cleanup failures from propagating.

## Limitations

### CAPTCHAs and Bot Detection

The agent runs in a headless Chrome browser and **cannot solve CAPTCHAs** (reCAPTCHA, hCaptcha, Cloudflare Turnstile, etc.). Sites that gate content behind CAPTCHAs will cause the agent to fail or return `NOT_FOUND`. Similarly, aggressive bot-detection mechanisms (browser fingerprinting, Cloudflare "checking your browser" interstitials) may block the agent before it can interact with the page at all.

### Login-Protected Content

The agent is explicitly instructed not to log in to websites. Any content behind authentication walls — account dashboards, gated pricing pages, members-only documentation — is inaccessible.

### Dynamic and JavaScript-Heavy Pages

While the agent uses a full browser and can handle JavaScript rendering, heavily dynamic pages (single-page apps with complex client-side routing, infinite scroll, lazy-loaded content) may reduce confidence and efficiency. The agent relies on screenshots and visible text, so content that requires specific user interactions to reveal (hover menus, accordion panels) may be missed.

### Single-Browser Bottleneck

Only one agent task runs at a time due to the shared headless Chrome instance. Submitting many tasks or URLs will result in serial execution. Tasks queued for more than 5 minutes will time out.

### Confidence Is Self-Reported

The confidence score comes from the LLM's own assessment, not from an independent verification. The agent may be overconfident about incorrect answers or underconfident about correct ones.

## Testing

```bash
uv run pytest tests/ -v
```

Tests use an in-memory DuckDB and mock the agent, so no Chrome or model endpoint is needed.
