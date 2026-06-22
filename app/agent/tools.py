import threading

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import ElementNotInteractableException, TimeoutException
from selenium import webdriver

from smolagents import tool

# Shared thread-local storage with browser.py
_thread_local = threading.local()


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
