import random
import threading
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import ElementNotInteractableException, TimeoutException
from selenium import webdriver

from smolagents import tool

# Shared thread-local storage with browser.py
_thread_local = threading.local()

# HITL (Human-in-the-Loop) coordination
# Maps task_id -> {"question": str, "answer": str | None, "event": threading.Event}
_hitl_pending: dict[str, dict] = {}
_hitl_lock = threading.Lock()


def _get_driver():
    """Get the driver for the current thread, falling back to helium's global."""
    driver = getattr(_thread_local, "driver", None)
    if driver is not None:
        return driver
    import helium
    return helium.get_driver()


@tool
def search_item_ctrl_f(text: str, nth_result: int = 1) -> str:
    """
    Searches for text on the current page via Ctrl + F and jumps to the nth occurrence.
    Args:
        text: The text to search for
        nth_result: Which occurrence to jump to (default: 1)
    """
    driver = _get_driver()
    # Escape single quotes in text to prevent XPath injection
    if "'" in text:
        escaped = "concat('" + text.replace("'", "',\"'\",'") + "')"
    else:
        escaped = f"'{text}'"
    elements = driver.find_elements(By.XPATH, f"//*[contains(text(), {escaped})]")
    if nth_result > len(elements):
        raise Exception(f"Match n°{nth_result} not found (only {len(elements)} matches found)")
    result = f"Found {len(elements)} matches for '{text}'."
    elem = elements[nth_result - 1]
    driver.execute_script("arguments[0].scrollIntoView(true);", elem)
    result += f" Focused on element {nth_result} of {len(elements)}"
    return result


@tool
def query_elements(selector: str, limit: int = 20) -> str:
    """
    Finds all elements matching a CSS selector and returns their text content.
    Use this to extract lists of items (comments, prices, product names, etc.).
    Args:
        selector: CSS selector string (e.g. '.price', '#comments .text', 'h2')
        limit: Maximum number of elements to return (default: 20)
    """
    driver = _get_driver()
    elements = driver.find_elements(By.CSS_SELECTOR, selector)
    if not elements:
        return f"No elements found matching '{selector}'"
    texts = []
    for i, el in enumerate(elements[:limit]):
        text = el.text.strip()
        if text:
            texts.append(f"{i + 1}. {text}")
    if not texts:
        return f"Found {len(elements)} elements matching '{selector}' but none had visible text"
    return f"Found {len(elements)} elements matching '{selector}':\n" + "\n".join(texts)


@tool
def go_back() -> None:
    """Goes back to the previous page."""
    driver = _get_driver()
    driver.back()


@tool
def go_to_with_retry(url: str, max_retries: int = 3) -> str:
    """
    Navigates to a URL with automatic retry on 429 (Too Many Requests) errors.
    Use this instead of go_to() when a website is rate-limiting you.
    Args:
        url: The URL to navigate to
        max_retries: Maximum number of retries (default: 3)
    """
    driver = _get_driver()
    for attempt in range(1, max_retries + 1):
        driver.get(url)
        # Check for 429 responses by inspecting page content
        title = (driver.title or "").lower()
        body = ""
        try:
            body = driver.find_element(By.TAG_NAME, "body").text[:500].lower()
        except Exception:
            pass
        is_429 = "429" in title or "too many requests" in title or "too many requests" in body or "rate limit" in body
        if not is_429:
            return f"Navigated to {url}"
        if attempt < max_retries:
            delay = min(10 * (2 ** (attempt - 1)), 60) + random.uniform(1, 5)
            time.sleep(delay)
    return f"Warning: page at {url} may still be rate-limited after {max_retries} retries"


@tool
def close_popups() -> str:
    """
    Closes any visible modal or pop-up on the page. Use this to dismiss pop-up windows.
    This does not work on cookie consent banners.
    """
    driver = _get_driver()
    modal_selectors = [
        "button[class*='close']",
        "[class*='modal'] button",
        "[class*='CloseButton']",
        "[aria-label*='close']",
        ".modal-close",
        ".close-modal",
        ".modal .close",
    ]

    wait = WebDriverWait(driver, timeout=0.5)

    for selector in modal_selectors:
        try:
            elements = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
            )
            for element in elements:
                if element.is_displayed():
                    try:
                        driver.execute_script("arguments[0].click();", element)
                    except ElementNotInteractableException:
                        element.click()
        except TimeoutException:
            continue

    # Fallback: press Escape
    webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    return "Modals closed"


@tool
def ask_user(question: str) -> str:
    """
    Ask the human user a question and wait for their response.
    Use this when you need information only the user can provide, such as:
    - OTP / verification codes sent to their phone or email
    - Login credentials (username, password)
    - CAPTCHA solutions
    - Any other information that requires human input

    The agent will pause until the user responds.

    Args:
        question: The question to ask the user (be specific about what you need)
    """
    task_id = getattr(_thread_local, "task_id", None)
    if task_id is None:
        return "Error: HITL not available — no task context found"

    event = threading.Event()
    with _hitl_lock:
        _hitl_pending[task_id] = {"question": question, "answer": None, "event": event}

    # Block until user responds (timeout after 5 minutes)
    answered = event.wait(timeout=300)

    with _hitl_lock:
        entry = _hitl_pending.pop(task_id, None)

    if not answered or entry is None or entry["answer"] is None:
        return "Error: Timed out waiting for user response"

    return entry["answer"]
