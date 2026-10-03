"""
Catalog of the step actions a test may contain, with what each one needs.

One list for everything that is not the executor itself: the UI step form
(GET /api/step_actions), the validation agent and the confidence scorer. The executor
stays the source of truth: TestRunner.execute_step runs these actions, and
api/step_action_endpoints.py checks the list against TestRunner.VALID_ACTIONS at startup.
"""


def _ui(name, label, group, description, needs_locator=True, needs_value="none", value_hint=None):
    return dict(name=name, label=label, group=group, description=description,
                needs_locator=needs_locator, needs_value=needs_value, value_hint=value_hint,
                test_types=["ui"])


# Keep in step with the branches of TestRunner.execute_step and the prompts in Utils/AIHelper
STEP_ACTIONS = [
    _ui("click", "Click", "Interaction", "Click the element"),
    _ui("type", "Type", "Interaction", "Type text into the element", needs_value="required",
        value_hint="Text, or a placeholder like %login% or %random_email%"),
    _ui("clear", "Clear", "Interaction", "Clear the input field"),
    _ui("select", "Select option", "Interaction", "Select an option of a <select> by its value attribute",
        needs_value="required", value_hint="Option value"),
    _ui("hover", "Hover", "Interaction", "Move the mouse over the element"),
    _ui("press_key", "Press key", "Interaction", "Press a keyboard key in the element",
        needs_value="required", value_hint="enter, tab, escape, backspace, delete, space, up, down, left, right"),
    _ui("drag_and_drop", "Drag and drop", "Interaction", "Drag the element onto another element",
        needs_value="required", value_hint="XPath of the drop target, e.g. //div[@id='droppable']"),
    _ui("upload_file", "Upload file", "Interaction", "Put a sample file into an <input type=\"file\">",
        needs_value="required", value_hint="Name of a sample file"),

    _ui("navigate", "Navigate", "Navigation", "Open a URL", needs_locator=False,
        needs_value="required", value_hint="URL, e.g. %base_url%/login"),
    _ui("switch_tab", "Switch tab", "Navigation", "Switch to another browser tab or window", needs_locator=False,
        needs_value="required", value_hint="new, main, a tab number, or a part of the tab title or URL"),

    _ui("wait", "Wait for element", "Wait", "Wait until the element is present in the page"),
    _ui("wait_for_element_to_be_visible", "Wait until visible", "Wait", "Wait until the element is visible"),
    _ui("wait_for_clickable", "Wait until clickable", "Wait", "Wait until the element is visible and enabled"),
    _ui("wait_for_modal", "Wait for modal", "Wait", "Wait until a modal dialog is visible"),

    _ui("assert", "Assert element", "Assertion", "Check the element exists; with a value, check a condition",
        needs_value="optional",
        value_hint="Empty = element exists; or text=..., value=..., visible=true, enabled=false, current_url_contains=..."),
    _ui("assert_text", "Assert text", "Assertion", "Check the element text is exactly the value",
        needs_value="required", value_hint="Exact text"),
    _ui("assert_text_contains", "Assert text contains", "Assertion", "Check the element text contains the value",
        needs_value="required", value_hint="Part of the text"),
    _ui("assert_attribute", "Assert attribute", "Assertion", "Check an attribute of the element",
        needs_value="required", value_hint="attribute=expected, e.g. aria-valuenow=0 or disabled=false"),

    _ui("accept_alert", "Accept alert", "Alert", "Press OK in a native alert, confirm or prompt", needs_locator=False,
        needs_value="optional", value_hint="For a prompt: the text to type before OK"),
    _ui("dismiss_alert", "Dismiss alert", "Alert", "Press Cancel in a native confirm or prompt", needs_locator=False),
    _ui("assert_alert_text", "Assert alert text", "Alert", "Check the exact text of the native alert; it stays open",
        needs_locator=False, needs_value="required", value_hint="Exact alert text"),
]

# The request of an api_request step is JSON in the value. Generated API tests keep it in the
# description instead; the API executor reads both.
STEP_ACTIONS.append(dict(
    name="api_request", label="API request", group="API",
    description="Send an HTTP request from the test; variables extracted from the response work in later steps as %name%",
    needs_locator=False, needs_value="optional",
    value_hint='{"method": "GET", "endpoint": "/path or full URL", "headers": {}, "body": {}, "expected_status": 200, '
               '"extract_variables": {"item_id": "$.id"}}',
    test_types=["ui", "api"]))

_API_ACTIONS = ["api_auth", "api_get", "api_post", "api_put", "api_delete", "api_patch",
                "response_validation", "validation"]
STEP_ACTIONS += [
    dict(name=name, label=name.replace("_", " "), group="API", description="Step of an API test",
         needs_locator=False, needs_value="optional", value_hint=None, test_types=["api"])
    for name in _API_ACTIONS
]



_BY_NAME = {action["name"]: action for action in STEP_ACTIONS}


def action_names():
    """Names of all catalogued actions."""
    return set(_BY_NAME)


def needs_locator(action):
    """Whether the action works on a page element. Unknown actions are assumed to."""
    meta = _BY_NAME.get((action or "").strip())
    return True if meta is None else meta["needs_locator"]
