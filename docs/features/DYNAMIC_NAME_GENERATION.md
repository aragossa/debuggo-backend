# Dynamic Name Generation for UI Tests

## Overview

The dynamic name generation feature eliminates test failures caused by duplicate names in UI tests. Instead of using hardcoded names like "Test Client" or "New User", the system now generates unique names automatically at runtime.

## Problem Solved

**Before**: Tests would fail when trying to create entities with duplicate names:
```
❌ Test failed: Cannot create client "Test Client" - name already exists
❌ Test failed: User "john.doe@test.com" already registered
```

**After**: Tests use dynamic variables that generate unique names:
```
✅ Test passed: Created client "Client_a7b3c9d2"
✅ Test passed: Created user "User_f4e8d1a6@test.com"
```

## How It Works

### 1. AI Generation Phase
When Gemini generates test steps, it now uses **variable placeholders** instead of hardcoded names:

**Old approach (hardcoded)**:
```json
{
  "action": "type",
  "element_locator": "//input[@name='clientName']",
  "value": "Test Client",
  "element_purpose": "Enter client name"
}
```

**New approach (dynamic)**:
```json
{
  "action": "type",
  "element_locator": "//input[@name='clientName']",
  "value": "%unique_name:Client%",
  "element_purpose": "Enter client name"
}
```

### 2. Test Execution Phase
During test execution, the `EnvHelper` automatically detects and replaces these variables with unique generated values:

```
%unique_name:Client% → "Client_a7b3c9d2"
```

### 3. Consistency Within Test Run
The same variable placeholder generates the **same value** throughout a single test run, ensuring consistency when the same name needs to be used multiple times.

## Available Name Variables

### Basic Unique Name
- **Variable**: `%unique_name%`
- **Output**: `a7b3c9d2` (8-character random alphanumeric)
- **Use case**: Simple unique identifier

### Unique Name with Prefix
- **Variable**: `%unique_name:Client%`
- **Output**: `Client_a7b3c9d2`
- **Use case**: Client names, user names, group names

### Unique Name with Prefix and Suffix
- **Variable**: `%unique_name:User:Test%`
- **Output**: `User_a7b3c9d2_Test`
- **Use case**: Test users, temporary entities

### Timestamp-Based Name
- **Variable**: `%timestamp_name%`
- **Output**: `20250129_143052`
- **Use case**: Time-based unique identifiers

### Timestamp Name with Prefix
- **Variable**: `%timestamp_name:Group%`
- **Output**: `Group_20250129_143052`
- **Use case**: Groups, projects with timestamp

### UUID-Based Name (Short)
- **Variable**: `%uuid_name:Client%`
- **Output**: `Client_a7b3c9d2`
- **Use case**: Guaranteed uniqueness with UUID

### UUID-Based Name (Full)
- **Variable**: `%uuid_name:Client:false%`
- **Output**: `Client_a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d`
- **Use case**: When full UUID is required

## Usage Examples

### Example 1: Creating a Client
```json
{
  "action": "type",
  "element_locator": "//input[@id='clientName']",
  "value": "%unique_name:Client%",
  "element_purpose": "Enter unique client name"
}
```
**Runtime**: `Client_a7b3c9d2`

### Example 2: Creating a User with Email
```json
{
  "action": "type",
  "element_locator": "//input[@id='email']",
  "value": "%unique_name%@test.com",
  "element_purpose": "Enter unique email address"
}
```
**Runtime**: `a7b3c9d2@test.com`

### Example 3: Creating a Group
```json
{
  "action": "type",
  "element_locator": "//input[@name='groupName']",
  "value": "%unique_name:RecipientGroup%",
  "element_purpose": "Enter unique group name"
}
```
**Runtime**: `RecipientGroup_f4e8d1a6`

### Example 4: Multiple Fields Using Same Name
```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='firstName']",
    "value": "%unique_name:User%",
    "element_purpose": "Enter first name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='displayName']",
    "value": "%unique_name:User%",
    "element_purpose": "Enter display name (same as first name)"
  }
]
```
**Runtime**: Both fields get `User_a7b3c9d2` (consistent within test run)

## Implementation Details

### Components

1. **NameGenerator** (`Utils/BrowserAutomation/NameGenerator.py`)
   - Utility class with static methods for generating unique names
   - Supports multiple generation strategies (random, timestamp, UUID)

2. **EnvHelper** (`Utils/BrowserAutomation/EnvHelper.py`)
   - Enhanced `process_variables()` method
   - Detects name variables and generates unique values
   - Caches generated names for consistency within test run

3. **AIHelper** (`Utils/AIHelper/AIHelper.py`)
   - Updated prompts to instruct Gemini to use dynamic variables
   - Provides examples and guidelines for variable usage

### Caching Mechanism

The `EnvHelper` maintains a cache of generated names during a test run:

```python
self._generated_names = {
  "%unique_name:Client%": "Client_a7b3c9d2",
  "%unique_name:User%": "User_f4e8d1a6",
  "%unique_name%@test.com": "h3k9m2n5@test.com"
}
```

This ensures that if the same variable is used multiple times in a test, it generates the **same value** for consistency.

## AI Prompt Instructions

The AI is now instructed to:

1. **NEVER** use hardcoded names
2. **ALWAYS** use dynamic name variables for:
   - Client names
   - User names
   - Group names
   - Email addresses
   - Any entity that requires a unique identifier

3. Choose appropriate variable types:
   - Use `%unique_name:Prefix%` for most cases
   - Use `%timestamp_name:Prefix%` when timestamp is meaningful
   - Use `%uuid_name:Prefix%` when guaranteed uniqueness is critical

## Benefits

1. **No More Duplicate Failures**: Tests never fail due to duplicate names
2. **Parallel Test Execution**: Multiple tests can run simultaneously without conflicts
3. **Reusable Tests**: Same test can be run multiple times without cleanup
4. **Consistent Naming**: Predictable naming patterns with prefixes
5. **Easy Debugging**: Generated names include context (e.g., "Client_", "User_")

## Migration Guide

### For Existing Tests

Existing tests with hardcoded names will continue to work, but may fail on duplicate names. To migrate:

1. **Regenerate test steps** using "Generate with AI" button
2. Gemini will automatically use dynamic variables in new steps
3. Old hardcoded steps can be manually updated or regenerated

### For Manual Test Creation

When manually creating test steps, use dynamic variables in the `value` field:

**Before**:
```
value: "Test Client"
```

**After**:
```
value: "%unique_name:Client%"
```

## Troubleshooting

### Variable Not Being Replaced

**Problem**: Variable appears as literal text (e.g., "%unique_name:Client%")

**Solutions**:
1. Check that `EnvHelper` is being used in test execution
2. Verify variable syntax is correct (use `:` for separators, not `-` or `_`)
3. Ensure variable is wrapped in `%` symbols

### Same Name Generated Multiple Times

**Problem**: Different test runs generate the same name

**Solution**: This is expected behavior. Names are unique within reasonable probability. If true uniqueness is required, use `%uuid_name%` instead of `%unique_name%`.

### Name Too Long for Field

**Problem**: Generated name exceeds field length limit

**Solutions**:
1. Use `%unique_name%` without prefix (8 characters)
2. Modify `NameGenerator.generate_unique_name()` to use shorter length
3. Use custom length: Update NameGenerator to accept length parameter

## Future Enhancements

Potential improvements:

1. **Custom Length**: Allow specifying length (e.g., `%unique_name:Client:4%` for 4-char random)
2. **Sequential Numbers**: Add `%sequential_name:Client%` for Client_001, Client_002, etc.
3. **Database Lookup**: Verify name uniqueness against database before using
4. **Custom Patterns**: Support regex patterns (e.g., `%pattern:[A-Z]{3}[0-9]{4}%`)
5. **Locale Support**: Generate names in different languages/character sets

## Summary

Dynamic name generation is a critical feature that:
- ✅ Eliminates duplicate name failures
- ✅ Enables parallel test execution
- ✅ Improves test reliability
- ✅ Requires no manual intervention
- ✅ Works automatically with AI-generated tests

The system intelligently generates unique names at runtime while maintaining consistency within each test run, making tests more robust and reliable.
