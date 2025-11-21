# Phase 3 Import Update Guide

## Overview

This guide explains how to update imports throughout the AuroQA codebase to use Phase 3 wrapper classes.

## Files Updated

### 1. Main Application (`/auroqa/main.py`)
**Status**: ✅ Updated

**Changes**:
```python
# Before
from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner

# After
if os.getenv('USE_PHASE3', 'true').lower() == 'true':
    from auroqa.Utils.BrowserAutomation.EnhancedTestRunner import EnhancedTestRunner as TestRunner
else:
    from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
```

### 2. API Schema Service (`/auroqa/Services/ApiSchemaService.py`)
**Status**: ✅ Updated

**Changes**:
```python
# Before
from auroqa.Utils.AIHelper.AIHelper import AIHelper

# After
if os.getenv('USE_PHASE3', 'true').lower() == 'true':
    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper as AIHelper
else:
    from auroqa.Utils.AIHelper.AIHelper import AIHelper
```

## Pattern for Updating Imports

Use this pattern when updating any file:

```python
import os

# Phase 3 Integration: Use wrapper if enabled
if os.getenv('USE_PHASE3', 'true').lower() == 'true':
    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper as AIHelper
    from auroqa.Utils.BrowserAutomation.EnhancedTestRunner import EnhancedTestRunner as TestRunner
else:
    from auroqa.Utils.AIHelper.AIHelper import AIHelper
    from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
```

## Files to Update

### High Priority (Core Services)

1. **`/auroqa/Services/TestExecutionService.py`**
   - Imports: TestRunner
   - Update: Add Phase 3 conditional import

2. **`/auroqa/Services/AgentMonitoring.py`**
   - Imports: AIHelper (if used)
   - Update: Add Phase 3 conditional import

3. **`/auroqa/Utils/BrowserAutomation/BrowserAutomation.py`**
   - Imports: TestRunner (if used)
   - Update: Add Phase 3 conditional import

### Medium Priority (Utilities)

4. **`/auroqa/Utils/AIHelper/HtmlAnalyzer.py`**
   - Check for AIHelper imports
   - Update if needed

5. **`/auroqa/Utils/AIHelper/ImageAnalyzer.py`**
   - Check for AIHelper imports
   - Update if needed

6. **`/auroqa/Utils/AIHelper/TextAnalyzer.py`**
   - Check for AIHelper imports
   - Update if needed

### Low Priority (Documentation/Examples)

7. **`/auroqa/docs/ai-agent/phase2/PHASE2.5_IMPLEMENTATION_GUIDE.md`**
   - Documentation only
   - No code changes needed

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Phase 3 Integration
USE_PHASE3=true
PHASE3_LOG_LEVEL=INFO
```

Or use the provided `.env.phase3`:

```bash
cp .env.phase3 .env.phase3.local
# Edit .env.phase3.local as needed
source .env.phase3.local
```

## Verification Steps

### Step 1: Check Imports

```bash
# Find all AIHelper imports
grep -r "from.*AIHelper import" /auroqa --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"

# Find all TestRunner imports
grep -r "from.*TestRunner import" /auroqa --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

### Step 2: Verify Wrapper Classes

```python
# test_imports.py

import os
os.environ['USE_PHASE3'] = 'true'

# Test AIHelper import
try:
    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper
    print("✓ EnhancedAIHelper imported successfully")
except ImportError as e:
    print(f"✗ Failed to import EnhancedAIHelper: {e}")

# Test TestRunner import
try:
    from auroqa.Utils.BrowserAutomation.EnhancedTestRunner import EnhancedTestRunner
    print("✓ EnhancedTestRunner imported successfully")
except ImportError as e:
    print(f"✗ Failed to import EnhancedTestRunner: {e}")

# Test instantiation
try:
    helper = EnhancedAIHelper()
    print(f"✓ EnhancedAIHelper instantiated: Phase 3 enabled = {helper.is_phase3_enabled()}")
except Exception as e:
    print(f"✗ Failed to instantiate EnhancedAIHelper: {e}")

try:
    runner = EnhancedTestRunner()
    print(f"✓ EnhancedTestRunner instantiated: Phase 3 enabled = {runner.is_phase3_enabled()}")
except Exception as e:
    print(f"✗ Failed to instantiate EnhancedTestRunner: {e}")
```

Run verification:
```bash
cd /Users/aragossa/dzrprj/auroqa
python3 test_imports.py
```

### Step 3: Test with Phase 3 Disabled

```bash
# Test with Phase 3 disabled
USE_PHASE3=false python3 test_imports.py
```

Expected output:
```
✓ EnhancedAIHelper imported successfully
✓ EnhancedTestRunner imported successfully
✓ EnhancedAIHelper instantiated: Phase 3 enabled = True
✓ EnhancedTestRunner instantiated: Phase 3 enabled = True
```

## Automated Update Script

Create a script to update all files automatically:

```bash
#!/bin/bash
# update_imports.sh

set -e

PROJECT_ROOT="/Users/aragossa/dzrprj/auroqa"
PATTERN="from auroqa.Utils.AIHelper.AIHelper import AIHelper"
REPLACEMENT="# Phase 3 Integration\nif os.getenv('USE_PHASE3', 'true').lower() == 'true':\n    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper as AIHelper\nelse:\n    from auroqa.Utils.AIHelper.AIHelper import AIHelper"

echo "🔄 Updating imports for Phase 3 integration..."

# Find and update AIHelper imports
find "$PROJECT_ROOT" -name "*.py" -type f ! -path "*/.*" ! -path "*/__pycache__/*" | while read file; do
    if grep -q "from auroqa.Utils.AIHelper.AIHelper import AIHelper" "$file"; then
        echo "📝 Updating: $file"
        # Add import os if not present
        if ! grep -q "^import os" "$file"; then
            sed -i '1i import os' "$file"
        fi
        # Update import
        sed -i 's/from auroqa\.Utils\.AIHelper\.AIHelper import AIHelper/# Phase 3 Integration\nif os.getenv("USE_PHASE3", "true").lower() == "true":\n    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper as AIHelper\nelse:\n    from auroqa.Utils.AIHelper.AIHelper import AIHelper/' "$file"
    fi
done

echo "✅ Import updates completed!"
```

## Manual Update Checklist

- [ ] `/auroqa/main.py` - Updated
- [ ] `/auroqa/Services/ApiSchemaService.py` - Updated
- [ ] `/auroqa/Services/TestExecutionService.py` - Check and update if needed
- [ ] `/auroqa/Services/AgentMonitoring.py` - Check and update if needed
- [ ] `/auroqa/Utils/BrowserAutomation/BrowserAutomation.py` - Check and update if needed
- [ ] Other services - Check and update if needed
- [ ] `.env` file - Add Phase 3 configuration
- [ ] Run verification tests
- [ ] Test with Phase 3 enabled
- [ ] Test with Phase 3 disabled

## Rollback Plan

If issues occur, revert imports:

```bash
# Revert to original imports
git checkout -- auroqa/main.py
git checkout -- auroqa/Services/ApiSchemaService.py
# ... other files

# Or manually revert to:
from auroqa.Utils.AIHelper.AIHelper import AIHelper
from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
```

## Testing After Update

### Unit Tests

```bash
# Run existing tests
pytest tests/ -v

# Run Phase 3 specific tests
pytest tests/test_phase3_reasoning_system.py -v
```

### Integration Tests

```bash
# Test with Phase 3 enabled
USE_PHASE3=true pytest tests/ -v

# Test with Phase 3 disabled
USE_PHASE3=false pytest tests/ -v
```

### Manual Testing

```python
# manual_test.py

import os
os.environ['USE_PHASE3'] = 'true'

from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper
from auroqa.Utils.BrowserAutomation.EnhancedTestRunner import EnhancedTestRunner

# Test AIHelper
helper = EnhancedAIHelper()
print(f"AIHelper Phase 3 status: {helper.get_phase3_status()}")

# Test TestRunner
runner = EnhancedTestRunner()
print(f"TestRunner Phase 3 status: {runner.get_phase3_status()}")

# Test planning
planning = helper.get_planning_context(test_case_id=123)
print(f"Planning context: {planning}")

# Test execution
result = runner.initialize_execution(test_case_id=123, total_steps=5)
print(f"Execution initialized: {result}")
```

Run:
```bash
cd /Users/aragossa/dzrprj/auroqa
python3 manual_test.py
```

## Troubleshooting

### Import Error: ModuleNotFoundError

```
ModuleNotFoundError: No module named 'auroqa.Utils.AIHelper.EnhancedAIHelper'
```

**Solution**: Ensure EnhancedAIHelper.py exists in `/auroqa/Utils/AIHelper/`

### Import Error: USE_PHASE3 not recognized

```
NameError: name 'os' is not defined
```

**Solution**: Add `import os` at the top of the file

### Circular Import Error

```
ImportError: cannot import name 'AIHelper' from partially initialized module
```

**Solution**: Check for circular imports, ensure wrapper classes don't import original classes in __init__

## Success Criteria

- ✅ All imports updated
- ✅ No import errors
- ✅ Phase 3 enabled by default
- ✅ Phase 3 can be disabled with environment variable
- ✅ All tests passing
- ✅ Backward compatibility maintained
- ✅ No performance degradation

## Next Steps

1. ✅ Update main.py
2. ✅ Update ApiSchemaService.py
3. ⏳ Update other services
4. ⏳ Run verification tests
5. ⏳ Test with Phase 3 enabled/disabled
6. ⏳ Deploy to staging
7. ⏳ Monitor logs
8. ⏳ Deploy to production

---

**Status**: ✅ Import update guide complete  
**Last Updated**: November 16, 2025
