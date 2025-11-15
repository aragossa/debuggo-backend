# Element Not Found Error Handling

## Problem Overview

When running UI tests, you may encounter "Element not found" errors where the automation cannot locate an element on the page, particularly with modal dialogs.

### Common Error Messages

```
Element not clickable within timeout
→ Element not found: //button[text()='Delete']
→ 'NoneType' object has no attribute 'click'
```

### Root Causes

1. **Modal Not Yet Visible**: Modal dialog hasn't appeared or animation incomplete
2. **Incorrect Locator**: XPath/CSS selector doesn't match any element
3. **Timing Issues**: Element loads after timeout expires
4. **Dynamic Content**: Element added/removed by JavaScript
5. **Wrong Context**: Element in iframe or shadow DOM

---

## Solutions Implemented

### ✅ Solution 1: Fixed Silent Failures

**Problem**: `find_element` was silently returning `None` instead of raising exceptions.

**Fix**: Replaced `except: pass` with proper exception handling:

```python
# Before (BAD):
try:
    element = WebDriverWait(driver, timeout).until(...)
    return element
except:
    pass  # ❌ Silently fails, returns None

# After (GOOD):
try:
    element = WebDriverWait(driver, timeout).until(...)
    return element
except TimeoutException:
    self.logger.warning("Element not clickable, trying JavaScript fallback...")
    # Continue to fallback methods
    # Eventually raises TimeoutException if all methods fail ✅
```

**Impact**:
- ✅ Clear error messages instead of `'NoneType' object has no attribute 'click'`
- ✅ Proper exception propagation
- ✅ Better debugging with detailed logs

---

### ✅ Solution 2: Automatic Screenshot on Failure

When an element cannot be found, the system now automatically takes a screenshot:

```python
# Take a screenshot for debugging
try:
    screenshot_path = f"/tmp/element_not_found_{pid}_{timestamp}.png"
    driver.save_screenshot(screenshot_path)
    logger.error(f"Element not found: {selector}. Screenshot saved: {screenshot_path}")
except:
    logger.error(f"Element not found: {selector}")
```

**Screenshot Location**: `/tmp/element_not_found_[PID]_[TIMESTAMP].png`

**Benefits**:
- ✅ Visual debugging - see exactly what the page looked like
- ✅ Identify if modal was visible
- ✅ Check if element exists with different locator
- ✅ Verify page state at time of failure

---

### ✅ Solution 3: New `wait_for_modal` Action

Added dedicated action for waiting for modal dialogs to appear:

```python
def wait_for_modal(self, modal_selector='//div[contains(@class, "modal")]', timeout=None):
    """
    Wait for a modal dialog to appear and become visible.
    Includes animation completion delay.
    """
    # Wait for modal to be present in DOM
    modal = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by_strategy, modal_selector))
    )
    
    # Wait for modal to be visible
    WebDriverWait(driver, timeout).until(
        EC.visibility_of(modal)
    )
    
    # Give modal animation time to complete
    time.sleep(0.3)
```

**Features**:
- ✅ Waits for modal to be in DOM
- ✅ Waits for modal to be visible
- ✅ Allows animation to complete (300ms)
- ✅ Takes screenshot if modal doesn't appear
- ✅ Available in frontend action dropdown

---

### ✅ Solution 4: Null Check in Click Method

Added validation to prevent clicking `None`:

```python
# Validate element was found
if element is None:
    raise TimeoutException(f"Element not found: {selector}")

# Now safe to click
element.click()
```

---

## Usage Examples

### Example 1: Wait for Modal Before Clicking

**Before (Unreliable)**:
```
Step 1: Click "Delete User"
  Action: click
  Locator: //button[@id='delete-user']

Step 2: Click "Confirm Delete" in modal
  Action: click
  Locator: //div[@class='modal']//button[text()='Delete']
  ❌ Often fails - modal not ready yet
```

**After (Reliable)**:
```
Step 1: Click "Delete User"
  Action: click
  Locator: //button[@id='delete-user']

Step 2: Wait for confirmation modal
  Action: wait_for_modal
  Locator: //div[@class='modal']
  ✅ Waits for modal to appear and animate

Step 3: Click "Confirm Delete"
  Action: click
  Locator: //div[@class='modal']//button[text()='Delete']
  ✅ Modal is ready, click succeeds
```

---

### Example 2: Custom Modal Selector

```
Step: Wait for specific modal
  Action: wait_for_modal
  Locator: //div[@id='confirmation-dialog']
```

---

### Example 3: Default Modal Selector

```
Step: Wait for any modal
  Action: wait_for_modal
  Locator: (leave empty)
  
# Uses default: //div[contains(@class, "modal")]
```

---

## Improved Error Messages

### Before:
```
WARNING: Standard click failed, trying alternative methods: 'NoneType' object has no attribute 'click'
ERROR: All click methods failed
```

### After:
```
INFO: Waiting for element to be clickable: //button[text()='Delete']
WARNING: Element not clickable within timeout, falling back to find_element
INFO: Trying with element_to_be_clickable for click action...
WARNING: Element not clickable, trying JavaScript fallback...
INFO: Trying with JavaScript...
ERROR: Element not found: //button[text()='Delete']. Screenshot saved: /tmp/element_not_found_82396_1730323939.png
```

**Benefits**:
- ✅ Clear progression through fallback methods
- ✅ Screenshot path for debugging
- ✅ Actionable error message

---

## Debugging Workflow

### When Test Fails with "Element not found":

1. **Check the Screenshot**:
   ```bash
   open /tmp/element_not_found_[PID]_[TIMESTAMP].png
   ```
   - Is the modal visible?
   - Is the element on the page?
   - Is the page in the expected state?

2. **Verify the Locator**:
   - Open browser DevTools (F12)
   - Try the XPath in Console:
     ```javascript
     $x("//button[text()='Delete']")
     ```
   - Try CSS selector:
     ```javascript
     document.querySelector("button.delete-btn")
     ```

3. **Check Timing**:
   - Does element appear after a delay?
   - Is there an animation that needs to complete?
   - Add `wait_for_modal` step before clicking

4. **Inspect Logs**:
   ```
   INFO: Waiting for element to be clickable
   WARNING: Element not clickable within timeout
   INFO: Trying with element_to_be_clickable
   WARNING: Element not clickable, trying JavaScript
   ERROR: Element not found
   ```
   - Shows all attempted methods
   - Indicates if element never appeared vs. not clickable

---

## Best Practices

### 1. Always Wait for Modals

```python
# Good Practice:
Step 1: Click trigger button
Step 2: wait_for_modal
Step 3: Click modal button

# Bad Practice:
Step 1: Click trigger button
Step 2: Click modal button  # ❌ May fail if modal not ready
```

---

### 2. Use Specific Locators

```python
# Good (Specific):
//button[@id='confirm-delete']
//button[@data-testid='delete-btn']

# Bad (Generic):
//button[1]  # ❌ May match wrong button
//button     # ❌ May match multiple buttons
```

---

### 3. Increase Timeout for Slow Pages

```python
# In environment settings or test configuration:
timeout = 15  # seconds (default is 10)
```

---

### 4. Check for iframes

If element is in an iframe, the system automatically checks:

```
INFO: Element not found in main frame. Checking 2 iframes...
INFO: Switched to iframe 1
INFO: Found element in iframe 1
```

---

## Configuration

### Modal Wait Settings

Modify in `BrowserAutomation.py`:

```python
# Animation delay after modal appears
time.sleep(0.3)  # 300ms for animations to complete
```

### Default Modal Selector

```python
default_modal_selector = '//div[contains(@class, "modal")]'
```

Can be customized per test step.

---

## Troubleshooting

### Issue: Modal appears but element still not found

**Possible Causes**:
1. Element is inside modal but locator is wrong
2. Modal has nested structure
3. Element disabled or hidden

**Solutions**:
- Check screenshot to verify element exists
- Use browser DevTools to test locator
- Try more specific locator: `//div[@class='modal']//button[@id='delete']`

---

### Issue: Screenshot shows blank page

**Possible Causes**:
1. Page navigation occurred
2. JavaScript error crashed page
3. Session lost

**Solutions**:
- Check browser console for errors
- Verify previous steps completed successfully
- Check if page URL changed unexpectedly

---

### Issue: Element found but not clickable

**Possible Causes**:
1. Element covered by overlay
2. Element disabled
3. Animation in progress

**Solutions**:
- Use `wait_for_clickable` action
- Increase timeout
- Add `wait_for_modal` before clicking

---

## Related Actions

### Available Wait Actions

1. **`wait`** - Wait for element to be present
2. **`wait_for_clickable`** - Wait for element to be clickable
3. **`wait_for_modal`** - Wait for modal to appear (NEW)

### When to Use Each

```
wait               → Element just needs to exist in DOM
wait_for_clickable → Element needs to be visible and enabled
wait_for_modal     → Modal dialog needs to appear and animate
```

---

## Files Modified

- **`/auroqa/Utils/BrowserAutomation/BrowserAutomation.py`**
  - Lines 216-217, 226-227: Fixed silent failures
  - Lines 246-253: Added screenshot on element not found
  - Lines 289-291: Added null check in click method
  - Lines 557-603: New `wait_for_modal` method

- **`/auroqa/Utils/BrowserAutomation/TestRunner.py`**
  - Lines 409-412: Added `wait_for_modal` action support

- **`/auroqa-ui/src/components/TestCaseSteps.js`**
  - Line 46: Added `wait_for_modal` to action dropdown

---

## Status

✅ **COMPLETE** - Element not found errors now provide:
- Clear error messages (no more `NoneType` errors)
- Automatic screenshots for debugging
- New `wait_for_modal` action for modal dialogs
- Proper exception handling throughout

---

## Related Documentation

- [Stale Element Handling](./STALE_ELEMENT_HANDLING.md) - Handling elements that become stale
- [Modal Dialog Handling](./MODAL_DIALOG_HANDLING.md) - General modal dialog best practices
- [Dynamic Name Generation](./DYNAMIC_NAME_GENERATION.md) - Avoiding duplicate name errors
