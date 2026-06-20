# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An agentic web browser that accepts a website URL and simulates common agent tasks (finding pricing, product features, documentation, contact info). For each task, it determines whether the information was found, confidence level, and failure reasons.

## Tech Stack

- **Agent**: smolagents + vision model ([docs](https://huggingface.co/docs/smolagents/examples/web_browser), [blog](https://huggingface.co/blog/smolagents-can-see#how-to-create-a-web-browsing-agent-with-vision))
- **Backend**: FastAPI
- **Database**: DuckDB
- **Python**: 3.11 (managed via `.python-version`)
- **Package manager**: uv (see `pyproject.toml`)

## Planned Architecture

- `app/agent/` - smolagents backend
- `app/api/` - FastAPI route handlers
- `app/core/` - configuration and utilities

## Common Commands

```bash
uvicorn app.main:app --reload  # dev server
pytest tests/ -v               # run tests
```

## Standards

- Type hints required on all functions
- pytest for testing (fixtures in `tests/conftest.py`)
- PEP 8 with 100 character lines
