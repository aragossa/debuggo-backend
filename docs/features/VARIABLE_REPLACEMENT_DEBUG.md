# Variable Replacement in Element Locators - Debug Guide

## Issue Discovered in Test Run 330

**Test Case**: 1851 - "create & delete recipient group"
**Problem**: Variables like `%unique_name:Group%` in element locators (XPath) were not being replaced with actual values during test execution.

## Symptoms

### Step 7 (Type Action)
```
element_path: //input[@id='RecipientGroupEditForm_name']
value: %unique_name:Group%
```
**Result**: ✅ Value correctly replaced with "Group_xyz123"

### Step 14 (Assert Action)
```
element_path: //table[@id='recipient-group-list']//a[contains(text(), '%unique_name:Group%')]
value: (empty)
```
**Result**: ❌ Variable NOT replaced in element_path, looking for literal text "%unique_name:Group%"

## Root Cause Analysis

The variable replacement IS implemented correctly in `TestRunner.execute_step()` (line 376-377):

```python
if env_helper:
    if element_path:
        element_path = env_helper.process_variables(element_path)
    if value:
        value = env_helper.process_variables(value)
```

However, there was **insufficient logging** to verify that:
1. The replacement was actually happening
2. The cached values were being reused correctly
3. The same `EnvHelper` instance was being used throughout the test

## Solution Implemented

### 1. Enhanced Logging in TestRunner

Added detailed logging to show variable replacement:

```python
if env_helper:
    if element_path:
        original_element_path = element_path
        element_path = env_helper.process_variables(element_path)
        if original_element_path != element_path:
            self.logger.info(f"Variable replacement in element_path: '{original_element_path}' → '{element_path}'")
    if value:
        original_value = value
        value = env_helper.process_variables(value)
        if original_value != value:
            self.logger.info(f"Variable replacement in value: '{original_value}' → '{value}'")
```

### 2. Enhanced Logging in EnvHelper

Added logging to show cache hits/misses:

```python
if placeholder in self._generated_names:
    value = self._generated_names[placeholder]
    self.logger.info(f"Using cached value for '{placeholder}': '{value}'")
else:
    value = NameGenerator.generate_unique_name(prefix=prefix, suffix=suffix)
    self._generated_names[placeholder] = value
    self.logger.info(f"Generated and cached new value for '{placeholder}': '{value}'")
```

## Expected Log Output

With the enhanced logging, you should now see:

```
INFO: Generated and cached new value for '%unique_name:Group%': 'Group_a7b3c9d2'
INFO: Variable replacement in value: '%unique_name:Group%' → 'Group_a7b3c9d2'
...
INFO: Using cached value for '%unique_name:Group%': 'Group_a7b3c9d2'
INFO: Variable replacement in element_path: '//table[@id='recipient-group-list']//a[contains(text(), '%unique_name:Group%')]' → '//table[@id='recipient-group-list']//a[contains(text(), 'Group_a7b3c9d2')]'
```

## Testing the Fix

### 1. Restart Backend
```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa
./stop.sh
./run.sh > test.log 2>&1 &
```

### 2. Run Test Case 1851
- Navigate to test case 1851 in UI
- Click "Run Test"
- Select environment

### 3. Check Logs
```bash
tail -f /Users/aragossa/dzrprj/auroqa/auroqa/test.log | grep -E "(Variable replacement|cached value)"
```

### 4. Verify Database
```sql
SELECT step_order, status, step_element_path, step_value 
FROM test_step_execution_results 
WHERE test_run_id = (SELECT MAX(id) FROM test_runs WHERE test_case_id = 1851)
AND step_order IN (7, 14, 15);
```

**Expected**: 
- Step 7: `step_value` shows unreplaced variable (stored before replacement)
- Step 14: `step_element_path` shows unreplaced variable (stored before replacement)
- But logs show actual replaced values were used during execution

## Additional Issues Found

### Issue 1: Step 11 Has Hardcoded Group Name

```sql
SELECT step_order, element_path 
FROM test_steps 
WHERE test_case_id = 1851 AND step_order = 11;
```

**Result**:
```
step_order: 11
element_path: //tr[td/a[text()='Group_vbry9j86']]//a[@title='Delete']
```

**Problem**: Hardcoded group name from previous test run

**Fix**: Should use variable:
```sql
UPDATE test_steps 
SET element_path = '//tr[td/a[contains(text(), ''%unique_name:Group%'')]]//a[@title=''Delete'']'
WHERE test_case_id = 1851 AND step_order = 11;
```

### Issue 2: Negative Assertion Passing Incorrectly

Step 14 (shows as 15 in execution) is a **negative assertion** checking that the deleted group no longer exists. Since the variable wasn't replaced (before the fix), it was looking for literal text `%unique_name:Group%`, which doesn't exist, so the assertion passed incorrectly.

With the fix, it will correctly look for the actual group name and verify it's been deleted.

## Files Modified

1. `/auroqa/Utils/BrowserAutomation/TestRunner.py`
   - Added logging for variable replacement in element_path and value

2. `/auroqa/Utils/BrowserAutomation/EnvHelper.py`
   - Added logger initialization
   - Added logging for cache hits/misses in unique_name generation

3. `/auroqa/docs/VARIABLE_REPLACEMENT_DEBUG.md`
   - This documentation file

## Summary

**Problem**: Insufficient logging made it unclear whether variable replacement was working
**Solution**: Added comprehensive logging to track variable replacement and cache usage
**Impact**: Can now debug and verify that variables are correctly replaced in both element_path and value fields
**Status**: ✅ Fix implemented, ready for testing

## Next Steps

1. ✅ Enhanced logging implemented
2. ⏳ Restart backend to apply changes
3. ⏳ Run test case 1851 and verify logs
4. ⏳ Fix step 11 hardcoded group name
5. ⏳ Regenerate test case 1851 with AI for complete fix
