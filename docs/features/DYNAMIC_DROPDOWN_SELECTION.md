# Dynamic Dropdown Selection

## Overview

The dynamic dropdown selection feature eliminates test failures caused by hardcoded dropdown values (like specific IDs or option values). Instead of using hardcoded values like `"35"` or `"client_123"`, the system now selects random available options at runtime.

## Problem Solved

**Before**: Tests would fail when hardcoded dropdown values don't exist or data changes:
```
❌ Test failed: Option with value "35" not found in dropdown
❌ Test failed: Client ID "123" no longer exists in database
```

**After**: Tests use `%random_option%` to select any available option:
```
✅ Test passed: Randomly selected option "47" (Client ABC)
✅ Test passed: Randomly selected option "89" (Client XYZ)
```

## How It Works

### 1. AI Generation Phase
When Gemini generates test steps for dropdown/select elements, it now uses `%random_option%` instead of hardcoded values:

**Old approach (hardcoded - flaky)**:
```json
{
  "action": "select",
  "element_locator": "//select[@id='RecipientGroupEditForm_clientId']",
  "value": "35",
  "element_purpose": "Select a client from the dropdown"
}
```

**New approach (dynamic - robust)**:
```json
{
  "action": "select",
  "element_locator": "//select[@id='RecipientGroupEditForm_clientId']",
  "value": "%random_option%",
  "element_purpose": "Select a random client from the dropdown. Available options: Client A, Client B, Client C"
}
```

### 2. Test Execution Phase
During test execution, the `BrowserAutomation.select()` method detects `%random_option%` and:
1. Retrieves all available options from the dropdown
2. Filters out empty/placeholder options
3. Randomly selects one valid option
4. Logs which option was selected

```
INFO: Randomly selected option with value '47' (text: 'Client ABC') from select element
```

## When to Use

### ✅ Use `%random_option%` When:
- The test doesn't care which specific option is selected
- Any valid option will satisfy the test requirement
- You want to avoid hardcoding IDs that may change
- Testing general functionality (create, edit, delete)
- Data is dynamic and options may vary between environments

### ❌ Use Specific Value When:
- The test explicitly requires testing a specific option
- Testing behavior specific to a particular selection
- Validating option-specific logic or permissions
- The test description explicitly mentions a specific entity

## Usage Examples

### Example 1: Client Dropdown (Test Case 1851)

**Scenario**: Create recipient group with any client

**Before (Hardcoded)**:
```json
{
  "step_number": 8,
  "action": "select",
  "element_locator": "//select[@id='RecipientGroupEditForm_clientId']",
  "value": "35",
  "element_purpose": "Select a client from the dropdown"
}
```
**Problem**: Fails if client ID 35 doesn't exist ❌

**After (Dynamic)**:
```json
{
  "step_number": 8,
  "action": "select",
  "element_locator": "//select[@id='RecipientGroupEditForm_clientId']",
  "value": "%random_option%",
  "element_purpose": "Select a random client from the dropdown"
}
```
**Result**: Always selects a valid client ✅

### Example 2: Category Dropdown

```json
{
  "action": "select",
  "element_locator": "//select[@name='category']",
  "value": "%random_option%",
  "element_purpose": "Select a random category from available options"
}
```

### Example 3: User Assignment Dropdown

```json
{
  "action": "select",
  "element_locator": "//select[@id='assignedUserId']",
  "value": "%random_option%",
  "element_purpose": "Assign to a random user from the dropdown"
}
```

### Example 4: Status Dropdown

```json
{
  "action": "select",
  "element_locator": "//select[@id='status']",
  "value": "%random_option%",
  "element_purpose": "Select a random status. Available: Active, Inactive, Pending"
}
```

### Example 5: Country Dropdown

```json
{
  "action": "select",
  "element_locator": "//select[@name='country']",
  "value": "%random_option%",
  "element_purpose": "Select a random country from the dropdown"
}
```

## Implementation Details

### BrowserAutomation.select() Method

The enhanced `select()` method now handles `%random_option%`:

```python
def select(self, selector, option_value, by='xpath'):
    if option_value == '%random_option%':
        # Get all valid options (excluding empty values)
        valid_options = [opt for opt in select.options 
                        if opt.get_attribute('value') and opt.get_attribute('value').strip()]
        
        # Select a random option
        random_option = random.choice(valid_options)
        actual_value = random_option.get_attribute('value')
        select.select_by_value(actual_value)
        
        self.logger.info(f"Randomly selected option with value '{actual_value}' (text: '{random_option.text}')")
    else:
        # Normal selection by value
        select.select_by_value(option_value)
```

### BrowserAutomation.get_dropdown_options() Method

New helper method to retrieve all available options:

```python
def get_dropdown_options(self, selector, by='xpath'):
    """Get all available options from a dropdown/select element."""
    select = WebDriverSelect(element)
    options = []
    
    for option in select.options:
        value = option.get_attribute('value')
        text = option.text.strip()
        # Skip empty or placeholder options
        if value and value.strip():
            options.append({
                'value': value,
                'text': text
            })
    
    return options
```

## AI Prompt Instructions

The AI is now instructed to:

1. **NEVER** use hardcoded dropdown values like "35", "123", specific IDs
2. **ALWAYS** use `%random_option%` for dropdown/select elements (unless test requires specific option)
3. Document available options in `element_purpose` when visible in HTML
4. Only use specific values when test explicitly requires testing that specific option

## Benefits

1. **No More Hardcoded ID Failures**: Tests never fail due to missing IDs
2. **Environment Independence**: Works across dev, staging, prod with different data
3. **Data Change Resilience**: Tests continue working when data is added/removed
4. **Better Test Coverage**: Different options selected on each run
5. **Parallel Test Safety**: Multiple tests can run without conflicts
6. **Realistic Testing**: Mimics real user behavior (selecting various options)

## Comparison: Before vs After

| Aspect | Before (Hardcoded) | After (Dynamic) |
|--------|-------------------|-----------------|
| **Value** | `"35"` | `"%random_option%"` |
| **Failure Rate** | High (if ID changes) | Very Low |
| **Maintenance** | Requires updates when data changes | Zero maintenance |
| **Coverage** | Tests same option every time | Tests different options |
| **Environments** | Breaks across environments | Works everywhere |
| **Parallel Tests** | May conflict | Safe |

## Logging and Debugging

When `%random_option%` is used, the system logs:
```
INFO: Randomly selected option with value '47' (text: 'Client ABC') from select element: //select[@id='RecipientGroupEditForm_clientId']
```

On failure, enhanced error messages show available options:
```
ERROR: Failed to select option '%random_option%'. Available options: 35 (Client A), 47 (Client B), 89 (Client C)
```

## Migration Guide

### For Existing Tests with Hardcoded Values

1. **Identify hardcoded dropdown values** in test steps
2. **Determine if specific value is required** for the test
3. **If not required**, replace with `%random_option%`
4. **Regenerate test** using "Generate with AI" for automatic fix

### Example Migration

**Before**:
```sql
UPDATE test_steps 
SET value = '35' 
WHERE test_case_id = 1851 AND step_order = 8;
```

**After**:
```sql
UPDATE test_steps 
SET value = '%random_option%' 
WHERE test_case_id = 1851 AND step_order = 8;
```

Or simply regenerate the test case with AI, which will automatically use `%random_option%`.

## Advanced Usage

### Combining with Dynamic Names

```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='groupName']",
    "value": "%unique_name:Group%",
    "element_purpose": "Enter unique group name"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='clientId']",
    "value": "%random_option%",
    "element_purpose": "Select random client for the group"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='categoryId']",
    "value": "%random_option%",
    "element_purpose": "Select random category"
  }
]
```

### When Specific Value IS Required

```json
{
  "action": "select",
  "element_locator": "//select[@id='clientId']",
  "value": "admin_client_id",
  "element_purpose": "Select the Admin client specifically to test admin-only features"
}
```

## Troubleshooting

### No Valid Options Found

**Problem**: `ValueError: No valid options found in dropdown`

**Solutions**:
1. Check if dropdown is populated (may need to wait for AJAX)
2. Add a `wait` step before the `select` step
3. Verify the dropdown selector is correct
4. Check if options have empty values (placeholders)

### Same Option Selected Multiple Times

**Problem**: Random selection picks the same option repeatedly

**Solution**: This is expected random behavior. If you need different options, run the test multiple times or use specific values.

### Dropdown Not Loading

**Problem**: Dropdown exists but has no options

**Solutions**:
1. Add explicit wait for options to load:
```json
{
  "action": "wait",
  "element_locator": "//select[@id='clientId']/option[2]",
  "element_purpose": "Wait for dropdown options to load"
}
```
2. Check for JavaScript errors preventing option population
3. Verify API calls that populate the dropdown are succeeding

## Best Practices

### ✅ DO:
- Use `%random_option%` for most dropdown selections
- Document available options in `element_purpose` when visible
- Add wait steps if dropdown loads dynamically
- Use specific values only when test requires it
- Test with `%random_option%` to ensure robustness

### ❌ DON'T:
- Don't hardcode IDs unless absolutely necessary
- Don't assume specific options will always exist
- Don't use `%random_option%` when test requires specific option
- Don't forget to handle empty/placeholder options
- Don't use for dropdowns where order matters (use index instead)

## Future Enhancements

Potential improvements:

1. **Filtered Random Selection**: `%random_option:filter=Active%` to select only options matching criteria
2. **Index-Based Selection**: `%random_option:index=0%` to select first option
3. **Exclusion Patterns**: `%random_option:exclude=Admin%` to exclude specific options
4. **Weighted Selection**: `%random_option:weight=first%` to prefer first options
5. **Multiple Selection**: Support for multi-select dropdowns

## Summary

Dynamic dropdown selection transforms:
- ❌ `"35"` (fails if ID doesn't exist)
- ✅ `"%random_option%"` (always selects valid option)

**Result**: Robust, maintainable, environment-independent tests! 🎉

## Related Features

- **Dynamic Name Generation**: See `DYNAMIC_NAME_GENERATION.md`
- **Environment Variables**: See `%base_url%`, `%login%`, `%password%`
- **Test Execution**: See `TestRunner` and `BrowserAutomation` classes
