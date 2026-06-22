HELIUM_INSTRUCTIONS = """
You can use helium to access websites. The helium driver is already managed.
We've already ran "from helium import *"

## Navigation
```py
go_to('https://example.com')
```<end_code>

Refresh the current page:
```py
refresh()
```<end_code>

## Clicking
Click by visible text, or use element classes for precision:
```py
click("Top products")
click(Link("Top products"))
click(Button("Submit"))
click(Image(alt="Logo"))
```<end_code>

Double-click and right-click:
```py
doubleclick("item")
rightclick("item")
```<end_code>

Click at specific coordinates:
```py
click(Point(500, 300))
```<end_code>

## Typing & Keyboard
Type into the currently focused field:
```py
write("search query")
```<end_code>

Type into a specific text field:
```py
write("hello", into="Search")
write("hello", into=TextField("Email"))
```<end_code>

Press keys or key combinations:
```py
press(ENTER)
press(TAB)
press(ESCAPE)
press(CONTROL + 'a')
press(CONTROL + 'c')
```<end_code>

## Scrolling
```py
scroll_down(num_pixels=1200)
scroll_up(num_pixels=800)
scroll_left(num_pixels=300)
scroll_right(num_pixels=300)
```<end_code>

## Hover & Drag
Hover over an element to reveal menus or tooltips:
```py
hover("Menu item")
hover(Link("Dropdown"))
```<end_code>

Drag an element to a target:
```py
drag("Source", to="Target")
```<end_code>

## Forms & Dropdowns
Select a value from a dropdown/combobox:
```py
select("Country", "United States")
select(ComboBox("Sort by"), "Price: Low to High")
```<end_code>

Check a checkbox or radio button:
```py
click(CheckBox("I agree"))
click(RadioButton("Monthly"))
```<end_code>

Read form values:
```py
value = TextField("Email").value
is_checked = CheckBox("Remember me").is_checked()
selected = ComboBox("Country").value
options = ComboBox("Country").options
```<end_code>

## File Upload
Attach a file to an upload input:
```py
attach_file("/path/to/file.pdf", to="Upload document")
```<end_code>

## Finding & Checking Elements
All element classes support positional filters: `below`, `above`, `to_right_of`, `to_left_of`.

Check if an element exists:
```py
if Text('Accept cookies?').exists():
    click('I accept')
if Button("Next").exists():
    click(Button("Next"))
```<end_code>

Find all matching elements:
```py
all_links = find_all(Link())
all_items = find_all(ListItem())
all_buttons = find_all(Button())
```<end_code>

Use positional filters to disambiguate:
```py
click(Button("Add", to_right_of="Product A"))
price = Text(below="Premium Plan", to_right_of="Price").value
```<end_code>

Read text content:
```py
heading = S('h1').web_element.text
link_url = Link("Pricing").href
```<end_code>

Use CSS/XPath selectors:
```py
element = S("#main-content")
element = S(".price-tag")
element = S("//div[@class='results']")
```<end_code>

## Waiting
Wait for an element to appear:
```py
wait_until(Text("Loading complete").exists, timeout_secs=15)
wait_until(Button("Download").exists, timeout_secs=10)
```<end_code>

## Alerts / Dialogs
Handle JavaScript alerts:
```py
if Alert().exists():
    alert_text = Alert().text
    Alert().accept()   # click OK
    Alert().dismiss()  # click Cancel
```<end_code>

## Window / Tab Management
Switch between browser windows or tabs:
```py
switch_to("Window Title")
```<end_code>

## Custom tool: Close pop-ups
Close modals and overlays using the built-in tool:
```py
close_popups()
```<end_code>

## Rules
- Proceed step by step. After each code block you write, you will get an updated screenshot.
- Never try to login to a page.
- Don't call kill_browser() or start_chrome() — the browser is managed for you.
- When you have your answer, return it with final_answer("YOUR ANSWER").
"""

TASK_PROMPT_TEMPLATE = (
    "Navigate to {url} and complete this task: {task}\n\n"
    "When you find the answer, rate your confidence from 0.0 to 1.0 based on how certain you are "
    "the information is correct and complete, then return:\n"
    "  final_answer('CONFIDENCE: <number>\\n<your answer>')\n\n"
    "Confidence guidelines:\n"
    "- 0.9-1.0: Information clearly visible on the page, directly matches the task\n"
    "- 0.7-0.8: Information found but may be incomplete or partially inferred\n"
    "- 0.4-0.6: Information is ambiguous, possibly outdated, or required guessing\n"
    "- 0.1-0.3: Very uncertain, could not verify the information\n\n"
    "If you cannot find the information at all, return final_answer('NOT_FOUND: <reason>').\n\n"
    "{helium_instructions}"
)
