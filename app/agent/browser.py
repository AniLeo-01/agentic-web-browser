import os
import re
import threading
import time
from io import BytesIO
from time import sleep

import anyio.to_thread
import helium
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from smolagents import CodeAgent, OpenAIModel
from smolagents.agents import ActionStep

from app.agent.prompts import HELIUM_INSTRUCTIONS, TASK_PROMPT_TEMPLATE
from app.agent import tools as _tools_module
from app.agent.tools import close_popups, go_back, query_elements, search_item_ctrl_f
from app.core.config import settings
from app.core.scoring import compute_scores

# Shared thread-local storage — used by both browser.py and tools.py
_thread_local = _tools_module._thread_local

# Limit concurrent browsers to avoid excessive resource usage
_browser_semaphore = threading.Semaphore(3)

# Maximum wall-clock time (seconds) for a single agent task
TASK_TIMEOUT_SECONDS = 300


def _get_thread_driver() -> webdriver.Chrome | None:
    """Get the driver for the current thread."""
    return getattr(_thread_local, "driver", None)


def _set_thread_driver(driver: webdriver.Chrome | None) -> None:
    """Store and activate a driver for the current thread."""
    _thread_local.driver = driver
    if driver is not None:
        helium.set_driver(driver)


def _save_screenshot(memory_step: ActionStep, agent: CodeAgent) -> None:
    """Callback that captures browser screenshots and feeds them to the agent."""
    sleep(1.0)
    driver = _get_thread_driver()
    if driver is None:
        return

    # Re-set helium's global driver to this thread's driver before any helium calls
    helium.set_driver(driver)

    current_step = memory_step.step_number
    for previous_step in agent.memory.steps:
        if (
            isinstance(previous_step, ActionStep)
            and previous_step.step_number <= current_step - 2
        ):
            previous_step.observations_images = None

    png_bytes = driver.get_screenshot_as_png()
    image = Image.open(BytesIO(png_bytes))
    memory_step.observations_images = [image.copy()]

    url_info = f"Current url: {driver.current_url}"
    memory_step.observations = (
        url_info
        if memory_step.observations is None
        else memory_step.observations + "\n" + url_info
    )


def _create_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver and store it in thread-local storage."""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--force-device-scale-factor=1")
    chrome_options.add_argument("--window-size=1000,1350")
    chrome_options.add_argument("--disable-pdf-viewer")
    # Support Chromium in Docker (set via CHROME_BIN / CHROMEDRIVER_PATH env vars)
    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        chrome_options.binary_location = chrome_bin
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
    if chromedriver_path and os.path.isfile(chromedriver_path):
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = helium.start_chrome(headless=True, options=chrome_options)
    _set_thread_driver(driver)
    return driver


def _kill_thread_browser() -> None:
    """Kill the browser for the current thread."""
    driver = _get_thread_driver()
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
        _set_thread_driver(None)


def _count_errors(agent: CodeAgent) -> int:
    """Count steps that had code execution errors."""
    count = 0
    for step in agent.memory.steps:
        if isinstance(step, ActionStep) and step.error is not None:
            count += 1
    return count


def _count_steps(agent: CodeAgent) -> int:
    """Count action steps taken."""
    return sum(1 for s in agent.memory.steps if isinstance(s, ActionStep))


def _extract_step_details(agent: CodeAgent) -> list[dict]:
    """Extract reasoning, code, observations, and errors from each step."""
    steps = []
    for step in agent.memory.steps:
        if not isinstance(step, ActionStep):
            continue
        steps.append({
            "step": step.step_number,
            "reasoning": step.model_output if isinstance(step.model_output, str) else None,
            "code": step.code_action,
            "observations": step.observations,
            "error": str(step.error) if step.error else None,
        })
    return steps


def _parse_confidence(answer: str) -> tuple[float, str]:
    """Parse 'CONFIDENCE: X.X\\n<answer>' format. Returns (confidence, clean_answer)."""
    match = re.match(r"CONFIDENCE:\s*([\d.]+)\s*\n(.*)", answer, re.DOTALL)
    if match:
        try:
            conf = max(0.0, min(1.0, float(match.group(1))))
            return conf, match.group(2).strip()
        except ValueError:
            pass
    # Fallback: no confidence marker found, default to 0.7
    return 0.7, answer


def _run_agent_task_sync(url: str, task: str) -> dict:
    """
    Synchronous agent execution. Called in a background thread.
    Each task gets its own browser instance stored in thread-local storage.

    Returns a dict with keys: found, confidence, answer, error,
    steps_taken, duration_seconds, errors_encountered, scores.
    """
    acquired = _browser_semaphore.acquire(timeout=TASK_TIMEOUT_SECONDS)
    if not acquired:
        scores = compute_scores(
            found=False, confidence=0.0, steps_taken=0,
            max_steps=settings.agent_max_steps,
            duration_seconds=0.0, errors_encountered=1,
        )
        return {
            "found": False, "confidence": 0.0, "answer": None,
            "error": "Timed out waiting for browser slot — too many concurrent tasks",
            "steps_taken": 0, "duration_seconds": 0.0,
            "errors_encountered": 1, "scores": scores, "step_details": [],
        }

    start_time = time.monotonic()
    try:
        driver = _create_driver()
        model = OpenAIModel(
            model_id=settings.model_id,
            api_base=settings.model_base_url,
            api_key=settings.model_api_key,
        )

        agent = CodeAgent(
            tools=[go_back, close_popups, search_item_ctrl_f, query_elements],
            model=model,
            additional_authorized_imports=["helium"],
            step_callbacks=[_save_screenshot],
            max_steps=settings.agent_max_steps,
            verbosity_level=1,
        )

        # Set helium driver right before agent runs
        helium.set_driver(driver)
        agent.python_executor("from helium import *")

        prompt = TASK_PROMPT_TEMPLATE.format(
            url=url, task=task, helium_instructions=HELIUM_INSTRUCTIONS
        )

        result = agent.run(prompt)
        duration = time.monotonic() - start_time
        answer = str(result)
        steps_taken = _count_steps(agent)
        errors_encountered = _count_errors(agent)
        step_details = _extract_step_details(agent)

        if answer.startswith("NOT_FOUND:"):
            found = False
            remainder = answer.removeprefix("NOT_FOUND:").strip()
            confidence, error_msg = _parse_confidence(remainder)
            # If agent didn't include CONFIDENCE in NOT_FOUND, default to 0.5
            if not remainder.startswith("CONFIDENCE:"):
                confidence = 0.5
            final_answer = None
        else:
            found = True
            confidence, final_answer = _parse_confidence(answer)
            error_msg = None

        scores = compute_scores(
            found=found,
            confidence=confidence,
            steps_taken=steps_taken,
            max_steps=settings.agent_max_steps,
            duration_seconds=duration,
            errors_encountered=errors_encountered,
        )

        return {
            "found": found,
            "confidence": confidence,
            "answer": final_answer,
            "error": error_msg,
            "steps_taken": steps_taken,
            "duration_seconds": round(duration, 2),
            "errors_encountered": errors_encountered,
            "scores": scores,
            "step_details": step_details,
        }
    except Exception as e:
        duration = time.monotonic() - start_time
        scores = compute_scores(
            found=False,
            confidence=0.0,
            steps_taken=0,
            max_steps=settings.agent_max_steps,
            duration_seconds=duration,
            errors_encountered=1,
        )
        return {
            "found": False,
            "confidence": 0.0,
            "answer": None,
            "error": str(e),
            "steps_taken": 0,
            "duration_seconds": round(duration, 2),
            "errors_encountered": 1,
            "scores": scores,
            "step_details": [],
        }
    finally:
        _kill_thread_browser()
        _browser_semaphore.release()


async def run_agent_task(url: str, task: str) -> dict:
    """Run agent task asynchronously by offloading to a background thread."""
    return await anyio.to_thread.run_sync(lambda: _run_agent_task_sync(url, task))
