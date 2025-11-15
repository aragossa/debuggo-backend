# Dynamic Variables Feature

## Overview
Added support for built-in dynamic variables in API test steps. These variables are automatically replaced with generated values during test execution.

## Supported Variables

| Variable | Description | Example Output |
|----------|-------------|----------------|
| `{{timestamp}}` | Unix timestamp (seconds since epoch) | `1760217061` |
| `{{datetime}}` | ISO 8601 datetime string | `2025-10-12T00:11:01.742000` |
| `{{uuid}}` | UUID v4 string | `550e8400-e29b-41d4-a716-446655440000` |
| `{{random}}` | Random 4-digit number | `7342` |

## Usage Examples

### 1. Unique Resource Names with Timestamp
```json
{
  "method": "PUT",
  "endpoint": "{{base_url}}/api/recipient-groups",
  "body": {
    "name": "Test Group - {{timestamp}}"
  }
}
```
**Result**: `"name": "Test Group - 1760217061"`

### 2. Unique Email Addresses with UUID
```json
{
  "body": {
    "email": "test-{{uuid}}@example.com",
    "name": "Test User"
  }
}
```
**Result**: `"email": "test-550e8400-e29b-41d4-a716-446655440000@example.com"`

### 3. Datetime for Audit Fields
```json
{
  "body": {
    "created_at": "{{datetime}}",
    "status": "active"
  }
}
```
**Result**: `"created_at": "2025-10-12T00:11:01.742000"`

### 4. Random Numbers for Testing
```json
{
  "body": {
    "order_number": "ORD-{{random}}",
    "amount": 100
  }
}
```
**Result**: `"order_number": "ORD-7342"`

## Implementation Details

**File**: `/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiTestExecutor.py`

The `_substitute_variables` method now handles dynamic variables **before** environment and session variables:

```python
def _substitute_variables(self, text: str) -> str:
    """Substitute variables in text with values from environment and session."""
    if not isinstance(text, str):
        return text
    
    result = text
    
    # 1. Built-in dynamic variables (NEW!)
    if '{{timestamp}}' in result:
        result = result.replace('{{timestamp}}', str(int(time.time())))
    if '{{datetime}}' in result:
        result = result.replace('{{datetime}}', datetime.now().isoformat())
    if '{{uuid}}' in result:
        result = result.replace('{{uuid}}', str(uuid.uuid4()))
    if '{{random}}' in result:
        result = result.replace('{{random}}', str(random.randint(1000, 9999)))
    
    # 2. Environment variables (base_url, login, password)
    for key, value in self.environment_vars.items():
        if key != 'custom_variables':
            result = result.replace(f'{{{{{key}}}}}', str(value))
    
    # 3. Session variables (extracted from API responses)
    for key, value in self.session_variables.items():
        result = result.replace(f'{{{{{key}}}}}', str(value))
    
    return result
```

## Use Cases

### Avoiding Duplicate Resource Errors
When creating resources that require unique names/identifiers:
```json
{
  "name": "Automation Test - {{timestamp}}",
  "email": "test-{{uuid}}@example.com"
}
```

### Testing with Fresh Data
Each test run creates new resources with unique identifiers, avoiding conflicts with previous test runs.

### Audit Trail Testing
Testing systems that require timestamps or datetime values:
```json
{
  "event_time": "{{datetime}}",
  "event_id": "{{uuid}}"
}
```

## Variable Substitution Order

1. **Dynamic variables** (`{{timestamp}}`, `{{uuid}}`, etc.) - Generated fresh each time
2. **Environment variables** (`{{base_url}}`, `{{login}}`, `{{password}}`) - From environment config
3. **Session variables** (`{{access_token}}`, `{{group_id}}`, etc.) - Extracted from API responses

This order ensures dynamic values are generated first, then environment config is applied, and finally session data from previous steps.

## Benefits

- ✅ **No hardcoded values** - Each test run uses fresh data
- ✅ **Avoid conflicts** - Unique identifiers prevent duplicate resource errors
- ✅ **Realistic testing** - Tests behave like real-world usage with unique data
- ✅ **Easy to use** - Simple placeholder syntax in test steps
- ✅ **Automatic** - No manual intervention needed

## Future Enhancements

Potential additions:
- `{{date}}` - Current date in YYYY-MM-DD format
- `{{time}}` - Current time in HH:MM:SS format
- `{{random_string}}` - Random alphanumeric string
- `{{random_email}}` - Random email address
- `{{random_phone}}` - Random phone number

## Status
✅ **IMPLEMENTED** - Dynamic variables now supported in API test execution
