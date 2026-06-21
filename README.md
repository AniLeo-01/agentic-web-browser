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
- **Frontend**: Single-file HTML/JS dashboard with Chart.js and anime.js
- **Python**: 3.11+

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

| Variable | Required | Default | Description |
|---|---|---|---|
| `MODEL_ID` | Yes | `gpt-5.4-mini` | Model identifier for the VLM |
| `MODEL_API_KEY` | Yes | — | API key for the model endpoint |
| `MODEL_BASE_URL` | No | `https://api.openai.com/v1` | Base URL of the OpenAI-compatible API |
| `DATABASE_PATH` | No | `data/browser.duckdb` | Path to the DuckDB database file |
| `AGENT_MAX_STEPS` | No | `20` | Maximum steps the agent can take per task |
| `DEBUG` | No | `false` | Enable FastAPI debug mode |

### Run

```bash
uv run uvicorn app.main:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) to access the dashboard.

### Testing

```bash
uv run pytest tests/ -v                                    # all tests
uv run pytest tests/test_api.py -v                         # single file
uv run pytest tests/test_api.py::test_browse_endpoint -v   # single test
```

Tests use an in-memory DuckDB and mock the agent, so no Chrome or model endpoint is needed.

## Architecture

### Project Structure

```
app/
├── main.py               # FastAPI app with lifespan (DB init/cleanup)
├── agent/
│   ├── browser.py         # Agent setup, Chrome driver, async task runner
│   ├── tools.py           # Custom browser tools (search, go_back, close_popups)
│   └── prompts.py         # Agent instructions and prompt templates
├── api/
│   └── routes.py          # API endpoints and async job queue
└── core/
    ├── config.py          # Settings from .env (pydantic-settings)
    ├── db.py              # DuckDB singleton connection and all queries
    ├── models.py          # Pydantic request/response models
    └── scoring.py         # Scoring formulas and weights
frontend/
├── index.html             # Dashboard UI (3 tabs: New Run, Dashboard, History)
├── app.js                 # Frontend logic, polling, charts, animations
└── style.css              # Dark theme with glassmorphism styling
tests/
├── conftest.py            # TestClient fixture with in-memory DB
└── test_api.py            # API endpoint tests
```

### Request Flow

1. **Submit** — `POST /api/browse` accepts a URL + list of tasks, creates an in-memory job, and spawns a background `asyncio.create_task`. Returns a `job_id` immediately.
2. **Execute** — Each task calls `run_agent_task()` which offloads to a thread via `anyio.to_thread.run_sync`. The sync runner acquires a `threading.Lock`, spins up a headless Chrome instance, and builds a `CodeAgent` with three custom Helium tools.
3. **Observe** — After each agent step, a screenshot callback captures the browser state and feeds it back to the VLM as an image observation.
4. **Parse** — Agent output is parsed: a `NOT_FOUND:` prefix means failure; otherwise `CONFIDENCE: X.X\n<answer>` is extracted. If no confidence marker is found, it defaults to 0.7.
5. **Score** — `compute_scores()` evaluates the run across 5 weighted dimensions.
6. **Persist** — Results (including per-step details) are saved to DuckDB. The frontend polls `/api/jobs/{id}` for live progress.

### Architecture Decisions

**Why smolagents `CodeAgent` instead of function-calling agents?** The CodeAgent generates and executes Python code at each step, which gives it the flexibility to compose Helium browser commands arbitrarily (click, scroll, type, check elements) rather than being limited to a fixed set of tool signatures. This is critical for navigating diverse, unpredictable web pages.

**Why Helium over raw Selenium?** Helium provides a high-level API that maps closely to how humans describe browser interactions ("click the button that says 'Pricing'"). This makes the agent's generated code more readable and reduces the prompt engineering needed to teach element selection.

**Why `anyio.to_thread` instead of async Selenium?** Selenium and Helium are synchronous libraries. Rather than introducing an async Selenium wrapper (which adds complexity and potential compatibility issues), the agent runs synchronously in a background thread. The FastAPI async layer handles concurrent HTTP requests while the browser work happens in its own thread.

**Why DuckDB over SQLite/Postgres?** DuckDB is embedded (zero configuration), handles analytical queries well (aggregations for the dashboard), and works as a single file. No database server to manage. The trade-off is no concurrent write access, but this is acceptable since browser tasks are already serialized.

**Why an in-memory job queue instead of Celery/Redis?** The app runs a single browser at a time, so a simple `dict` + `asyncio.create_task` is sufficient. Adding a task queue would introduce infrastructure dependencies without meaningful benefit at this scale.

**Why a single-file frontend?** The dashboard is intentionally simple — three tabs, a few charts, and a results table. A full SPA framework would be overkill. The single HTML file with vanilla JS, Chart.js for visualizations, and anime.js for animations keeps the deployment footprint minimal.

### Assumptions

- **One browser at a time** — The system assumes a single shared Chrome instance. All tasks are serialized via a `threading.Lock`. This simplifies resource management but means throughput is limited.
- **OpenAI-compatible API** — The model endpoint must support the OpenAI chat completions API format. Any VLM provider that exposes this interface (OpenAI, HuggingFace TGI, vLLM, Ollama) will work.
- **Vision model** — The model must support image inputs. The agent sends screenshots at each step and relies on the model's ability to interpret visual content.
- **Public pages only** — The agent is prompted to never log in. All tasks assume the target content is publicly accessible without authentication.
- **Honest confidence** — The scoring system trusts the model's self-reported confidence. There is no independent verification of answer correctness.
- **Chrome available** — The host machine (or Docker container) must have Chrome/Chromium installed and accessible to Selenium.

## API

### `POST /api/browse`

Submit a URL and a list of tasks (max 10) for the agent to perform. Returns immediately with a `job_id` — tasks run asynchronously in the background.

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

Poll for job status and results. Status is `running` or `completed`.

### `GET /api/jobs`

List all jobs, newest first. Jobs are stored in-memory and do not persist across server restarts.

### `GET /api/results`

Query persisted results from DuckDB. Optionally filter by URL.

```
GET /api/results?url=https://www.netflix.com/&limit=10
```

### `DELETE /api/results/{result_id}`

Delete a single result by ID.

### `DELETE /api/results`

Delete all results.

### `GET /api/dashboard`

Aggregated stats across all runs: average scores, per-URL breakdown, top issues, and recommendations.

### `GET /api/performance?url=...`

Detailed performance breakdown for a single URL, including all individual runs with step-level details.

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

## Known Limitations

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

### Cookie Consent Banners

The `close_popups` tool handles modals and pop-ups via common CSS selectors, but cookie consent banners vary widely across sites. Some banners may obscure page content and not be dismissed, reducing the agent's ability to read the page.

### No Persistent Job Queue

In-memory jobs are lost on server restart. Only scored results in DuckDB survive restarts; the job status and metadata do not.

## Future Improvements

- **Browser pool** — Run multiple headless Chrome instances in parallel to increase throughput and remove the single-browser bottleneck.
- **Independent answer verification** — Cross-check agent answers against a second model or heuristic to reduce reliance on self-reported confidence.
- **Cookie banner handling** — Integrate a dedicated cookie consent library (e.g., "I don't care about cookies" browser extension) to automatically dismiss consent banners before the agent starts navigating.
- **Persistent job queue** — Replace the in-memory job store with a durable queue (e.g., backed by DuckDB or Redis) so jobs survive server restarts.
- **Streaming progress** — Replace polling with WebSocket or SSE to push live agent step updates to the frontend in real time.
- **Screenshot gallery** — Store and display the screenshot captured at each step, so users can visually trace the agent's navigation path.
- **Comparative runs** — Run the same task across multiple URLs side-by-side to benchmark agent readiness across competing sites.
- **Configurable scoring weights** — Allow users to adjust dimension weights per run or globally, depending on what matters most for their use case.

## Deployment

### Docker

```bash
docker build -t agentic-web-browser .
docker run -p 7860:7860 \
  -e MODEL_ID=google/gemma-4-31B-it \
  -e MODEL_API_KEY=your_api_key \
  -e MODEL_BASE_URL=https://your-model-endpoint/v1 \
  agentic-web-browser
```

To persist DuckDB data across restarts, mount the data directory:

```bash
docker run -p 7860:7860 -v $(pwd)/data:/app/data \
  -e MODEL_ID=... -e MODEL_API_KEY=... -e MODEL_BASE_URL=... \
  agentic-web-browser
```
