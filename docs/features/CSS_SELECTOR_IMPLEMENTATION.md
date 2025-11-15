# CSS Selector Column Implementation

## Overview
Added CSS selector support as a fallback locator strategy for test steps. This implements the dual locator strategy where XPath is tried first, then CSS selector as a fallback.

## Changes Made

### 1. Backend Changes

#### HtmlAnalyzer.py
- **Updated return type annotations** for `html_analyzer()` and `analyze_error()` methods
  - Changed from 6-tuple to 7-tuple to include `css_selector`
  - Return format: `(next_step, element_purpose, action, element_locator, css_selector, by_strategy, value)`

#### TestRunner.py
- **Updated `_save_step()` method** to accept `css_selector` parameter
  - Added `css_selector` column to INSERT query
  - Default value: empty string
  
- **Updated error recovery** to pass `css_selector` when saving corrected steps
  - Both error recovery loops now include `css_selector` parameter

#### main.py
- **Updated `UpdateTestStepAction` model** to include `css_selector` field
- **Updated `/api/update_test_step/{id}` endpoint** to handle CSS selector updates
  - Accepts `css_selector` in PATCH requests
  - Updates database with new CSS selector value

### 2. Frontend Changes

#### TestCaseSteps.js
- **Added CSS Selector column** to test steps table
  - Header: "CSS Selector (Fallback)"
  - Input field for each step row
  
- **Added `handleCssSelectorChange()` handler**
  - Updates local state immediately
  - Sends PATCH request to backend
  - Format: `{ css_selector: "value" }`

- **Column widths adjusted**:
  - XPath: 30% → 25%
  - CSS: New 20% column
  - Value: 20% → 15%

#### TestCaseSteps.css
- **Added styling for CSS selector column**:
  - `.step-css-column`: Column width (20%)
  - `.step-css-cell .css-selector-input`: Input field styling
    - Monospace font (Consolas)
    - Gray background (#f8f9fa)
    - Green focus border (success color)
    - Placeholder styling

## How It Works

### Test Generation Flow
1. **AI generates step** with both XPath and CSS selector
2. **HtmlAnalyzer returns** 7-tuple including both locators
3. **TestRunner saves** both locators to database
4. **Frontend displays** both in separate columns

### Test Execution Flow  
1. **TestRunner reads** both `element_path` (XPath) and `css_selector`
2. **BrowserAutomation tries XPath first**
3. **If XPath fails**, automatically tries CSS selector
4. **If both fail**, error is reported

### Manual Editing
1. **User can edit** CSS selector directly in UI
2. **Frontend sends** PATCH request with new value
3. **Backend updates** `css_selector` column
4. **Change takes effect** immediately

## Database Schema

```sql
ALTER TABLE test_steps 
ADD COLUMN IF NOT EXISTS css_selector TEXT;

COMMENT ON COLUMN test_steps.css_selector IS 'CSS selector fallback when element_path (XPath) fails';
```

## Benefits

1. **Increased reliability**: Dual locator strategy provides fallback
2. **AI-powered**: Gemini generates both locators automatically
3. **Manual override**: Users can edit CSS selectors when needed
4. **Backward compatible**: Existing steps work without CSS selectors
5. **Better maintainability**: CSS selectors often more stable than XPath

## Testing

To test the implementation:

1. **Generate new test steps** - verify both XPath and CSS are populated
2. **Edit CSS selector** in UI - verify it saves correctly
3. **Run test** with CSS fallback - verify it works when XPath fails
4. **Check logs** - verify which locator strategy was used

## Files Modified

- `/auroqa/Utils/AIHelper/HtmlAnalyzer.py` - Return type annotations
- `/auroqa/Utils/BrowserAutomation/TestRunner.py` - Save and error recovery
- `/auroqa/main.py` - API model and endpoint
- `/auroqa-ui/src/components/TestCaseSteps.js` - UI column and handler
- `/auroqa-ui/src/components/TestCaseSteps.css` - Styling

## Status

✅ **COMPLETE** - CSS selector column fully implemented in both backend and frontend
