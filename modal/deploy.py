import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "chromium",
        "chromium-driver",
        "fonts-liberation",
        "libatk-bridge2.0-0",
        "libatk1.0-0",
        "libcups2",
        "libdbus-1-3",
        "libdrm2",
        "libgbm1",
        "libnss3",
        "libxcomposite1",
        "libxdamage1",
        "libxrandr2",
    )
    .pip_install_from_pyproject("pyproject.toml")
    .env({
        "CHROME_BIN": "/usr/bin/chromium",
        "CHROMEDRIVER_PATH": "/usr/bin/chromedriver",
    })
    .add_local_dir("app", "/root/app")
    .add_local_dir("frontend", "/root/frontend")
)

app = modal.App("agentic-web-browser", image=image)
volume = modal.Volume.from_name("awb-data", create_if_missing=True)


@app.function(
    volumes={"/root/data": volume},
    secrets=[modal.Secret.from_name("awb-secrets")],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def web():
    import os
    os.chdir("/root")
    os.environ.setdefault("DATABASE_PATH", "/root/data/browser.duckdb")

    from app.main import app as fastapi_app
    return fastapi_app
