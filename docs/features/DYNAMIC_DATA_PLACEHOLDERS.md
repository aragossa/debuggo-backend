# Dynamic Data Placeholders - Complete Guide

## Overview

The AuroQA platform supports comprehensive dynamic data generation through placeholders. Instead of hardcoding test data like "Test Client" or "test@test.com", you can use placeholders that generate realistic, unique data at runtime.

## Why Use Placeholders?

✅ **No Duplicate Failures**: Tests never fail due to duplicate names/emails
✅ **Realistic Test Data**: Generated data looks like real-world data
✅ **Parallel Execution**: Multiple tests can run simultaneously without conflicts
✅ **Reusable Tests**: Same test can run multiple times without cleanup
✅ **Environment Independence**: Works across dev, staging, prod
✅ **Better Coverage**: Different data on each test run

## Supported Placeholder Types

### A. Unique Identifiers (Cached per Test Run)

These generate unique IDs that are **cached** within a test run. Using the same placeholder multiple times in one test will return the **same value**.

| Placeholder | Example Output | Use Case |
|------------|----------------|----------|
| `%unique_name%` | "a7b3c9d2" | Generic unique identifier |
| `%unique_name:Client%` | "Client_a7b3c9d2" | Client name with prefix |
| `%unique_name:User:Test%` | "User_a7b3c9d2_Test" | With prefix and suffix |
| `%timestamp_name%` | "20250129_143052" | Timestamp-based ID |
| `%timestamp_name:Group%` | "Group_20250129_143052" | With prefix |

**Usage Example:**
```json
// Step 1: Create client
{"action": "type", "value": "%unique_name:Client%"}
// Generates: "Client_a7b3c9d2"

// Step 5: Delete the same client
{"element_locator": "//tr[td/a[text()='%unique_name:Client%']]//a[@title='Delete']"}
// Uses cached value: "Client_a7b3c9d2"
```

### B. Realistic Personal Data (New Value Each Time)

These generate **new** realistic data every time they're used.

| Placeholder | Example Output | Use Case |
|------------|----------------|----------|
| `%random_name%` | "John Smith" | Full name field |
| `%random_first_name%` | "John" | First name field |
| `%random_last_name%` | "Smith" | Last name field |
| `%random_email%` | "john.smith@example.com" | Email field |
| `%random_username%` | "john_smith_123" | Username field |
| `%random_phone%` | "+12025551234" | Phone number field (E.164 format) |

### C. Realistic Location Data

| Placeholder | Example Output | Use Case |
|------------|----------------|----------|
| `%random_address%` | "742 Evergreen Terrace" | Street address |
| `%random_city%` | "Springfield" | City name |
| `%random_country%` | "United States" | Country name |

### D. Realistic Business Data

| Placeholder | Example Output | Use Case |
|------------|----------------|----------|
| `%random_company%` | "AcmeCorporation" | Business/client name (alphabetic only) |
| `%random_job_title%` | "Software Engineer" | Job title field |

### E. Technical Data

| Placeholder | Example Output | Use Case |
|------------|----------------|----------|
| `%random_string%` | "k7m2p9x4q1" | Generic text (10 chars) |
| `%random_string:5%` | "a8c3z" | Custom length string |
| `%random_number%` | 7543 | Number field (1-10000) |
| `%random_number:1:100%` | 47 | Custom range number |
| `%random_url%` | "https://www.example.com" | URL field |
| `%random_ip%` | "192.168.1.42" | IP address |
| `%random_uuid%` | "a7b3c9d2-e5f1-..." | Full UUID |
| `%random_color%` | "blue" | Color name |
| `%random_date%` | "2024-03-15" | Date field |
| `%random_boolean%` | true/false | Boolean field |
| `%random_text%` | "Lorem ipsum..." | Text paragraph |
| `%random_text:5%` | "Five sentences..." | Custom sentences |

## Usage in UI Tests

### Before (Hardcoded):
```json
{
  "step_order": 1,
  "action": "type",
  "element_path": "//input[@name='clientName']",
  "value": "Test Client",
  "description": "Enter client name"
}
```
❌ **Problem**: Fails if "Test Client" already exists

### After (Dynamic):
```json
{
  "step_order": 1,
  "action": "type",
  "element_path": "//input[@name='clientName']",
  "value": "%random_company%",
  "description": "Enter client name"
}
```
✅ **Result**: Generates "Acme Corporation", "TechStart Inc", etc.

### Complete Form Example:
```json
[
  {
    "action": "type",
    "element_path": "//input[@name='firstName']",
    "value": "%random_first_name%"
  },
  {
    "action": "type",
    "element_path": "//input[@name='lastName']",
    "value": "%random_last_name%"
  },
  {
    "action": "type",
    "element_path": "//input[@name='email']",
    "value": "%random_email%"
  },
  {
    "action": "type",
    "element_path": "//input[@name='phone']",
    "value": "%random_phone%"
  },
  {
    "action": "type",
    "element_path": "//input[@name='city']",
    "value": "%random_city%"
  }
]
```

## Usage in API Tests

### Before (Hardcoded):
```json
{
  "method": "PUT",
  "endpoint": "%base_url%/api/clients",
  "body": {
    "name": "Test Client Automation",
    "email": "test@test.com",
    "phone": "555-1234"
  }
}
```
❌ **Problem**: Duplicate client name, unrealistic data

### After (Dynamic):
```json
{
  "method": "PUT",
  "endpoint": "%base_url%/api/clients",
  "body": {
    "name": "%random_company%",
    "email": "%random_email%",
    "phone": "%random_phone%"
  },
  "extract_variables": {
    "client_id": "$.client.id"
  }
}
```
✅ **Result**: Generates realistic, unique data every time

### Complete API Example:
```json
{
  "method": "POST",
  "endpoint": "%base_url%/api/users",
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer %auth_token%"
  },
  "body": {
    "firstName": "%random_first_name%",
    "lastName": "%random_last_name%",
    "email": "%random_email%",
    "username": "%random_username%",
    "phone": "%random_phone%",
    "address": {
      "street": "%random_address%",
      "city": "%random_city%",
      "country": "%random_country%"
    },
    "company": "%random_company%",
    "jobTitle": "%random_job_title%"
  },
  "expected_status": 201,
  "extract_variables": {
    "user_id": "$.user.id"
  }
}
```

## When to Use Each Type

### Use `%unique_name:Type%` When:
- ✅ Entity needs to be referenced in multiple steps
- ✅ Need consistency (create → edit → delete same item)
- ✅ Value must be same across test run
- ✅ Need to verify exact created item

**Example:**
```json
// Step 1: Create
{"value": "%unique_name:Group%"} → "Group_a7b3c9d2"

// Step 5: Delete same group
{"element_locator": "//tr[td/a[text()='%unique_name:Group%']]//a[@title='Delete']"}
→ Targets "Group_a7b3c9d2" (cached value)
```

### Use `%random_*%` When:
- ✅ Need realistic test data
- ✅ Value doesn't need to be referenced later
- ✅ Each field independent
- ✅ Better readability than prefixed IDs

**Example:**
```json
{
  "firstName": "%random_first_name%",  → "Michael"
  "lastName": "%random_last_name%",    → "Johnson"
  "email": "%random_email%"             → "sarah.williams@example.com"
}
```

## Best Practices

### ✅ DO:
- Use `%random_company%` for business/client names
- Use `%random_email%` instead of `%unique_name%@test.com`
- Use `%random_name%` for person name fields
- Use `%unique_name:Type%` when you need to reference the value later
- Reuse same variable in multiple steps for consistency

### ❌ DON'T:
- Don't hardcode "Test Client", "John Doe", etc.
- Don't use `%unique_name%@test.com` (use `%random_email%` instead)
- Don't hardcode generated values in selectors
- Don't use position-based selectors (use variable reuse)

## Implementation Details

### Backend (Python)

**NameGenerator.py**:
- Uses Faker library for realistic data
- Provides static methods for each placeholder type
- Generates consistent or unique values as needed

**EnvHelper.py**:
- Processes `%placeholder%` syntax
- Caches unique_name values per test run
- Generates new random values each time

**ApiTestExecutor.py**:
- Integrates EnvHelper for variable substitution
- Processes placeholders before API requests
- Supports both `%placeholder%` and `{{placeholder}}` syntax

### AI Prompts

**AIHelper.py** (UI Tests):
- Comprehensive placeholder documentation
- Examples for correct usage
- Warnings against hardcoded values

**ApiSchemaService.py** (API Tests):
- API-specific placeholder examples
- JSON body examples with placeholders
- Request data generation guidelines

## Testing the Feature

### Test UI Form:
1. Create test case: "Create New Client"
2. Generate steps with AI
3. Verify AI uses `%random_company%` instead of "Test Client"
4. Run test multiple times - should create different clients each time

### Test API Endpoint:
1. Upload API schema with client creation
2. Generate test steps
3. Verify AI uses placeholders in request body
4. Run test - check realistic data in database

## Troubleshooting

### Issue: Placeholder not replaced
**Cause**: Typo in placeholder name
**Solution**: Check spelling - use exact names from documentation

### Issue: Same value in multiple fields
**Cause**: Using cached placeholder (`%unique_name%`)
**Solution**: Use `%random_*%` placeholders for independent values

### Issue: "Faker not found" error
**Cause**: Faker library not installed
**Solution**: Run `pip install -r requirements.txt`

### Issue: Empty/null values
**Cause**: Placeholder used in wrong context
**Solution**: Verify placeholder is appropriate for field type

## Examples Gallery

### E-commerce User Registration:
```json
{
  "email": "%random_email%",
  "password": "%random_string:12%",
  "firstName": "%random_first_name%",
  "lastName": "%random_last_name%",
  "phone": "%random_phone%",
  "shippingAddress": {
    "street": "%random_address%",
    "city": "%random_city%",
    "country": "%random_country%"
  }
}
```

### Company Profile:
```json
{
  "companyName": "%random_company%",
  "website": "%random_url%",
  "email": "%random_email%",
  "phone": "%random_phone%",
  "address": "%random_address%",
  "city": "%random_city%",
  "country": "%random_country%"
}
```

### Product Creation:
```json
{
  "name": "%random_string:20%",
  "sku": "%random_uuid%",
  "price": "%random_number:10:1000%",
  "color": "%random_color%",
  "description": "%random_text:3%"
}
```

## Migration Guide

### For Existing Tests:

1. **Identify hardcoded values** in test steps
2. **Replace with appropriate placeholders**:
   - Names → `%random_name%` or `%random_company%`
   - Emails → `%random_email%`
   - Phones → `%random_phone%`
   - Addresses → `%random_address%`, `%random_city%`
3. **For entity names** that need consistency:
   - Use `%unique_name:Type%` instead
   - Reuse in multiple steps
4. **Regenerate test** to get AI-updated steps

### SQL Update Examples:

```sql
-- Update client name field
UPDATE test_steps 
SET value = '%random_company%'
WHERE action = 'type' 
  AND element_path LIKE '%clientName%'
  AND value LIKE '%Test%';

-- Update email fields
UPDATE test_steps 
SET value = '%random_email%'
WHERE action = 'type' 
  AND element_path LIKE '%email%'
  AND value LIKE '%test%@%';
```

## Status

✅ **COMPLETE** - Dynamic data placeholders fully implemented
- Backend support in NameGenerator, EnvHelper, ApiTestExecutor
- AI prompts updated for both UI and API tests
- Faker library integrated for realistic data
- Documentation complete
- Ready for production use

---

**Last Updated**: 2025-11-09
**Version**: 1.0.0
