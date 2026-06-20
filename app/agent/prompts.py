HELIUM_INSTRUCTIONS = """
You can use helium to access websites. The helium driver is already managed.
We've already ran "from helium import *"

Navigate to pages:
```py
go_to('https://example.com')
```<end_code>

Click elements by their visible text:
```py
click("Top products")
```<end_code>

Click links:
```py
click(Link("Top products"))
```<end_code>

Scroll the page:
```py
scroll_down(num_pixels=1200)
```<end_code>

Close pop-ups using the built-in tool:
```py
close_popups()
```<end_code>

Check if an element exists:
```py
if Text('Accept cookies?').exists():
    click('I accept')
```<end_code>

Proceed step by step. After each code block you write, you will get an updated screenshot.
Never try to login to a page. Don't kill the browser.
When you have your answer, return it with final_answer("YOUR ANSWER").
"""

TASK_PROMPT_TEMPLATE = (
    "Navigate to {url} and complete this task: {task}\n\n"
    "When you find the answer, return it with final_answer(). "
    "If you cannot find the information, return final_answer('NOT_FOUND: <reason>').\n\n"
    "{helium_instructions}"
)
