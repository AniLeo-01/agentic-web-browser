from io import BytesIO
from time import sleep

import anyio.to_thread
import helium
from PIL import Image
from selenium import webdriver

from smolagents import CodeAgent, OpenAIModel
from smolagents.agents import ActionStep

from app.agent.prompts import HELIUM_INSTRUCTIONS, TASK_PROMPT_TEMPLATE
from app.agent.tools import close_popups, go_back, search_item_ctrl_f
from app.core.config import settings


def _save_screenshot(memory_step: ActionStep, agent: CodeAgent) -> None:
    """Callback that captures browser screenshots and feeds them to the agent."""
    sleep(1.0)
    driver = helium.get_driver()
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

    url_info = f"Current url: {driver.current_url}"
    memory_step.observations = (
        url_info
        if memory_step.observations is None
        else memory_step.observations + "\n" + url_info
    )


def _create_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver for server use."""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--force-device-scale-factor=1")
    chrome_options.add_argument("--window-size=1000,1350")
    chrome_options.add_argument("--disable-pdf-viewer")
    return helium.start_chrome(headless=True, options=chrome_options)


def _run_agent_task_sync(url: str, task: str) -> dict:
    """
    Synchronous agent execution. Called in a background thread.

    Returns a dict with keys: found, confidence, answer, error.
    """
    driver = _create_driver()
    try:
        model = OpenAIModel(
            model_id=settings.model_id,
            api_base=settings.model_base_url,
            api_key=settings.model_api_key,
        )

        agent = CodeAgent(
            tools=[go_back, close_popups, search_item_ctrl_f],
            model=model,
            additional_authorized_imports=["helium"],
            step_callbacks=[_save_screenshot],
            max_steps=settings.agent_max_steps,
            verbosity_level=1,
        )
        agent.python_executor("from helium import *")

        prompt = TASK_PROMPT_TEMPLATE.format(
            url=url, task=task, helium_instructions=HELIUM_INSTRUCTIONS
        )

        result = agent.run(prompt)
        answer = str(result)

        if answer.startswith("NOT_FOUND:"):
            return {
                "found": False,
                "confidence": 0.0,
                "answer": None,
                "error": answer.removeprefix("NOT_FOUND:").strip(),
            }

        return {
            "found": True,
            "confidence": 0.8,
            "answer": answer,
            "error": None,
        }
    except Exception as e:
        return {
            "found": False,
            "confidence": 0.0,
            "answer": None,
            "error": str(e),
        }
    finally:
        helium.kill_browser()


async def run_agent_task(url: str, task: str) -> dict:
    """Run agent task asynchronously by offloading to a background thread."""
    return await anyio.to_thread.run_sync(lambda: _run_agent_task_sync(url, task))
