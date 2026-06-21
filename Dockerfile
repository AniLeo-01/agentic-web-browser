FROM python:3.11-slim

# Install Chromium (much faster than google-chrome-stable, ~150MB vs ~400MB)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    # Minimal runtime deps for headless Chromium
    fonts-liberation libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libnss3 libxcomposite1 libxdamage1 libxrandr2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Tell Selenium/Helium to use the Chromium binary
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies (cached layer — only rebuilds when pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --no-dev --frozen

# Copy application code
COPY app/ app/
COPY frontend/ frontend/

# Create data directory for DuckDB
RUN mkdir -p data

EXPOSE 7860

# Run directly from the venv instead of `uv run` (avoids re-resolution overhead)
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
