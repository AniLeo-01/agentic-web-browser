import logging
import os
import re
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path
from time import sleep

import anyio.to_thread
import helium
import helium._impl
import imageio.v3 as iio
import numpy as np
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from smolagents import CodeAgent, OpenAIModel
from smolagents.agents import ActionStep

from app.agent.prompts import HELIUM_INSTRUCTIONS, TASK_PROMPT_TEMPLATE
from app.agent import tools as _tools_module
from app.agent.tools import ask_user, close_popups, go_back, go_to_with_retry, query_elements, search_item_ctrl_f
from app.core.config import settings
from app.core.scoring import compute_scores

# Shared thread-local storage — used by both browser.py and tools.py
_thread_local = _tools_module._thread_local

# Limit concurrent browsers to avoid excessive resource usage
_browser_semaphore = threading.Semaphore(3)

# ---------------------------------------------------------------------------
# Monkey-patch helium to isolate concurrent browser sessions.
#
# Problem: helium stores ONE global _API_IMPL, so concurrent threads
# overwrite each other's driver — causing cross-task navigation leaks
# (e.g. an Amazon task ending up on support.apple.com).
#
# Solution: each task registers its own driver → APIImpl pair.  The patched
# _get_api_impl() looks up _thread_local.driver to find the correct APIImpl.
# smolagents' per-execution timeout (ThreadPoolExecutor) is disabled via
# executor_kwargs={"timeout_seconds": None} so agent code runs in the same
# thread as the task, keeping _thread_local accessible.
# ---------------------------------------------------------------------------
_driver_to_api: dict[int, helium._impl.APIImpl] = {}
_driver_to_api_lock = threading.Lock()


def _register_api_impl(driver: webdriver.Chrome) -> helium._impl.APIImpl:
    """Create and register an isolated APIImpl for the given driver."""
    impl = helium._impl.APIImpl()
    from helium._impl import WebDriverWrapper
    impl.driver = WebDriverWrapper(driver)
    with _driver_to_api_lock:
        _driver_to_api[id(driver)] = impl
    return impl


def _unregister_api_impl(driver: webdriver.Chrome) -> None:
    """Remove the APIImpl for a driver being torn down."""
    with _driver_to_api_lock:
        _driver_to_api.pop(id(driver), None)


def _patched_get_api_impl():
    # Look up by current thread's driver (works for task threads)
    driver = getattr(_thread_local, "driver", None)
    if driver is not None:
        with _driver_to_api_lock:
            impl = _driver_to_api.get(id(driver))
        if impl is not None:
            return impl
    # Fallback to original singleton (for non-task contexts like tests)
    if helium._API_IMPL is None:
        helium._API_IMPL = helium._impl.APIImpl()
    return helium._API_IMPL


helium._get_api_impl = _patched_get_api_impl

# Maximum wall-clock time (seconds) for a single agent task
TASK_TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)


def _get_thread_driver() -> webdriver.Chrome | None:
    """Get the driver for the current thread."""
    return getattr(_thread_local, "driver", None)


def _set_thread_driver(driver: webdriver.Chrome | None) -> None:
    """Store a driver reference for the current thread."""
    _thread_local.driver = driver


def _save_screenshot(memory_step: ActionStep, agent: CodeAgent) -> None:
    """Callback that captures browser screenshots, feeds them to the agent, and persists to disk."""
    sleep(1.0)
    driver = _get_thread_driver()
    if driver is None:
        return

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

    # Persist screenshot to disk for later viewing
    media_dir = getattr(_thread_local, "media_dir", None)
    if media_dir is not None:
        screenshot_path = media_dir / f"step_{current_step:03d}.png"
        image.save(screenshot_path, "PNG")

    url_info = f"Current url: {driver.current_url}"
    memory_step.observations = (
        url_info
        if memory_step.observations is None
        else memory_step.observations + "\n" + url_info
    )


def _create_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver, register it, and store in thread-local."""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--force-device-scale-factor=1")
    chrome_options.add_argument("--window-size=1000,1350")
    chrome_options.add_argument("--disable-pdf-viewer")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    # Support Chromium in Docker (set via CHROME_BIN / CHROMEDRIVER_PATH env vars)
    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        chrome_options.binary_location = chrome_bin
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
    if chromedriver_path and os.path.isfile(chromedriver_path):
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
    _set_thread_driver(driver)
    _register_api_impl(driver)
    return driver


def _kill_thread_browser() -> None:
    """Kill the browser for the current thread."""
    driver = _get_thread_driver()
    if driver is not None:
        _unregister_api_impl(driver)
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


def _extract_step_details(agent: CodeAgent, media_dir: Path | None = None) -> list[dict]:
    """Extract reasoning, code, observations, errors, and screenshot paths from each step."""
    steps = []
    for step in agent.memory.steps:
        if not isinstance(step, ActionStep):
            continue
        detail: dict = {
            "step": step.step_number,
            "reasoning": step.model_output if isinstance(step.model_output, str) else None,
            "code": step.code_action,
            "observations": step.observations,
            "error": str(step.error) if step.error else None,
        }
        if media_dir is not None:
            screenshot_file = media_dir / f"step_{step.step_number:03d}.png"
            if screenshot_file.exists():
                detail["screenshot"] = str(screenshot_file.relative_to(settings.media_path))
        steps.append(detail)
    return steps


def _generate_recording(media_dir: Path) -> str | None:
    """Stitch step screenshots into an MP4 video. Returns relative path or None."""
    screenshot_files = sorted(media_dir.glob("step_*.png"))
    if len(screenshot_files) < 2:
        return None

    video_path = media_dir / "recording.mp4"
    try:
        # Read all frames, resize to consistent dimensions
        frames = []
        for f in screenshot_files:
            img = Image.open(f).convert("RGB")
            frames.append(np.array(img))

        # Ensure consistent frame size (use first frame's dimensions)
        h, w = frames[0].shape[:2]
        uniform_frames = []
        for frame in frames:
            if frame.shape[:2] != (h, w):
                img = Image.fromarray(frame).resize((w, h), Image.LANCZOS)
                frame = np.array(img)
            uniform_frames.append(frame)

        # Write video at 1 fps (each step shown for 1 second)
        iio.imwrite(str(video_path), uniform_frames, fps=1, codec="libx264")
        return str(video_path.relative_to(settings.media_path))
    except Exception as e:
        logger.warning("Failed to generate recording: %s", e)
        return None


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


def _run_agent_task_sync(url: str, task: str, task_id: str | None = None) -> dict:
    """
    Synchronous agent execution. Called in a background thread.
    Each task gets its own browser instance stored in thread-local storage.

    Returns a dict with keys: found, confidence, answer, error,
    steps_taken, duration_seconds, errors_encountered, scores.
    """
    # Store task_id for HITL tool
    _thread_local.task_id = task_id

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

    # Set up per-task media directory for screenshots and recording
    run_id = task_id or uuid.uuid4().hex[:12]
    media_dir = Path(settings.media_path) / run_id
    media_dir.mkdir(parents=True, exist_ok=True)
    _thread_local.media_dir = media_dir

    start_time = time.monotonic()
    try:
        driver = _create_driver()
        model = OpenAIModel(
            model_id=settings.model_id,
            api_base=settings.model_base_url,
            api_key=settings.model_api_key,
        )

        agent = CodeAgent(
            tools=[go_back, close_popups, search_item_ctrl_f, query_elements, go_to_with_retry, ask_user],
            model=model,
            additional_authorized_imports=["helium"],
            step_callbacks=[_save_screenshot],
            max_steps=settings.agent_max_steps,
            verbosity_level=1,
            # Disable smolagents' per-execution timeout to keep code running in
            # the same thread as the task (required for thread-local driver
            # isolation). We already enforce TASK_TIMEOUT_SECONDS externally.
            executor_kwargs={"timeout_seconds": None},
        )

        agent.python_executor("from helium import *")

        # Override dangerous helium functions so the agent can't kill/restart the browser
        agent.python_executor(
            "def start_chrome(*a, **kw): raise RuntimeError('start_chrome() is disabled — the browser is managed for you')\n"
            "def kill_browser(*a, **kw): raise RuntimeError('kill_browser() is disabled — the browser is managed for you')\n"
            "def start_firefox(*a, **kw): raise RuntimeError('start_firefox() is disabled — the browser is managed for you')"
        )

        prompt = TASK_PROMPT_TEMPLATE.format(
            url=url, task=task, helium_instructions=HELIUM_INSTRUCTIONS
        )

        result = agent.run(prompt)
        duration = time.monotonic() - start_time
        answer = str(result)
        steps_taken = _count_steps(agent)
        errors_encountered = _count_errors(agent)
        step_details = _extract_step_details(agent, media_dir)
        recording_path = _generate_recording(media_dir)

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
            "recording_path": recording_path,
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
        _thread_local.task_id = None
        _thread_local.media_dir = None


async def run_agent_task(url: str, task: str, task_id: str | None = None) -> dict:
    """Run agent task asynchronously by offloading to a background thread."""
    return await anyio.to_thread.run_sync(lambda: _run_agent_task_sync(url, task, task_id))
