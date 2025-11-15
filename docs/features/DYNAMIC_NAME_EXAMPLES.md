# Dynamic Name Generation - Examples

## ⚠️ CRITICAL: Never Hardcode Dynamic Values in XPath/CSS Selectors

### The Problem

When you create an item with a dynamic name (e.g., `%unique_name:Group%`), **DO NOT** use the generated value in subsequent XPath/CSS selectors. This is one of the most common mistakes that breaks test repeatability.

### ❌ WRONG Example

```json
// Step 1: Create group with dynamic name
{
  "action": "type",
  "element_locator": "//input[@id='groupName']",
  "value": "%unique_name:Group%",  // Generates "Group_a7b3c9d2"
  "element_purpose": "Enter group name"
}

// Step 2: Delete the created group
{
  "action": "click",
  "element_locator": "//tr[td/a[text()='Group_a7b3c9d2']]//a[@title='Delete']",  // ❌ HARDCODED!
  "element_purpose": "Delete the group"
}
```

**Why This Fails**:
- First run: Creates `Group_a7b3c9d2`, tries to delete `Group_a7b3c9d2` ✅ Works
- Second run: Creates `Group_f8e9d1c4`, tries to delete `Group_a7b3c9d2` ❌ Not found!

### ✅ CORRECT Example - BEST PRACTICE

**Reuse the SAME variable** in the selector:

```json
// Step 1: Create group with dynamic name
{
  "action": "type",
  "element_locator": "//input[@id='groupName']",
  "value": "%unique_name:Group%",
  "element_purpose": "Enter group name"
}

// Step 2: Delete the created group (using SAME variable)
{
  "action": "click",
  "element_locator": "//tr[td/a[text()='%unique_name:Group%']]//a[@title='Delete']",  // ✅ Reuses variable!
  "element_purpose": "Delete the group we just created"
}
```

**Why This Is Best**:
- ✅ Both steps use `%unique_name:Group%`
- ✅ EnvHelper cache ensures both get the SAME value at runtime
- ✅ Directly targets the created item (not position-dependent)
- ✅ Works regardless of table sort order or pagination
- ✅ If you created "Group_abc123", you delete "Group_abc123"

**Example at Runtime**:
```
Step 1: value gets replaced → "Group_a7b3c9d2" (cached)
Step 2: selector gets replaced → "//tr[td/a[text()='Group_a7b3c9d2']]//a[@title='Delete']" (same value from cache!)
```

---

### ⚠️ Alternative Approaches (Use Only When Variable Reuse Isn't Possible)

**WARNING**: These approaches are **less reliable** than variable reuse!

1. **Using `last()` function** (⚠️ Fails with pagination):
   ```xpath
   //tr[last()]//a[@title='Delete']
   ```
   **Problem**: Only works if all items fit on one page. With pagination, `last()` might be row 10, but your item could be on page 2.

2. **Using position `[1]`** (⚠️ Fails with sorting):
   ```xpath
   //tr[1]//a[@title='Delete']
   ```
   **Problem**: If table is sorted (e.g., by name descending), your newly created "Group_zq4nj5fn" might be at position 9, not position 1!
   
   **Real Example**: Test case 1851 - table sorted by name desc, created group was at index 8, not index 0!

3. **Using `contains()` with prefix** (⚠️ Matches multiple items):
   ```xpath
   //tr[td/a[contains(text(), 'Group_')]]//a[@title='Delete']
   ```
   **Problem**: Matches ALL groups with "Group_" prefix. If there are 10 groups, which one gets clicked? The first match might not be yours!

4. **Using data attributes** (✅ Better, if available):
   ```xpath
   //tr[@data-type='group'][last()]//a[@title='Delete']
   ```
   **Still has issues**: Same pagination and sorting problems as above.

**Recommendation**: Always prefer variable reuse (`%unique_name:Group%` in both create and delete steps)!

---

## Example 1: Creating a New Client

### Old Approach (Hardcoded - Will Fail on Duplicates)
```json
{
  "step_number": 1,
  "action": "type",
  "element_locator": "//input[@id='clientName']",
  "by_strategy": "xpath",
  "value": "Test Client",
  "element_purpose": "Enter client name"
}
```

**Problem**: If "Test Client" already exists, test fails ❌

### New Approach (Dynamic - Always Unique)
```json
{
  "step_number": 1,
  "action": "type",
  "element_locator": "//input[@id='clientName']",
  "by_strategy": "xpath",
  "value": "%unique_name:Client%",
  "element_purpose": "Enter unique client name"
}
```

**Result**: Generates "Client_a7b3c9d2" - Always unique ✅

---

## Example 2: User Registration with Email

### Old Approach (Hardcoded)
```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='firstName']",
    "value": "John",
    "element_purpose": "Enter first name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='lastName']",
    "value": "Doe",
    "element_purpose": "Enter last name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='email']",
    "value": "john.doe@test.com",
    "element_purpose": "Enter email"
  }
]
```

**Problem**: Email already registered ❌

### New Approach (Dynamic)
```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='firstName']",
    "value": "%unique_name:User%",
    "element_purpose": "Enter unique first name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='lastName']",
    "value": "TestUser",
    "element_purpose": "Enter last name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='email']",
    "value": "%unique_name%@test.com",
    "element_purpose": "Enter unique email"
  }
]
```

**Result**: 
- First name: "User_f4e8d1a6"
- Email: "a7b3c9d2@test.com"
- Always unique ✅

---

## Example 3: Creating Multiple Related Entities

### Scenario: Create Client, then User for that Client

```json
[
  {
    "step_number": 1,
    "action": "click",
    "element_locator": "//button[@id='newClient']",
    "element_purpose": "Click New Client button"
  },
  {
    "step_number": 2,
    "action": "type",
    "element_locator": "//input[@id='clientName']",
    "value": "%unique_name:Client%",
    "element_purpose": "Enter unique client name"
  },
  {
    "step_number": 3,
    "action": "click",
    "element_locator": "//button[@id='saveClient']",
    "element_purpose": "Save client"
  },
  {
    "step_number": 4,
    "action": "click",
    "element_locator": "//button[@id='newUser']",
    "element_purpose": "Click New User button"
  },
  {
    "step_number": 5,
    "action": "type",
    "element_locator": "//input[@id='userName']",
    "value": "%unique_name:User%",
    "element_purpose": "Enter unique user name"
  },
  {
    "step_number": 6,
    "action": "type",
    "element_locator": "//input[@id='userEmail']",
    "value": "%unique_name%@%unique_name:Client%.com",
    "element_purpose": "Enter unique email with client domain"
  }
]
```

**Result**:
- Client name: "Client_a7b3c9d2"
- User name: "User_f4e8d1a6"
- Email: "h3k9m2n5@Client_a7b3c9d2.com"
- All unique ✅

---

## Example 4: Consistent Name Across Multiple Fields

### Scenario: Same name used in multiple places

```json
[
  {
    "step_number": 1,
    "action": "type",
    "element_locator": "//input[@id='groupName']",
    "value": "%unique_name:RecipientGroup%",
    "element_purpose": "Enter group name"
  },
  {
    "step_number": 2,
    "action": "type",
    "element_locator": "//input[@id='groupDisplayName']",
    "value": "%unique_name:RecipientGroup%",
    "element_purpose": "Enter display name (same as group name)"
  },
  {
    "step_number": 3,
    "action": "type",
    "element_locator": "//input[@id='groupDescription']",
    "value": "Description for %unique_name:RecipientGroup%",
    "element_purpose": "Enter description with group name"
  }
]
```

**Result** (All use the SAME generated value):
- Group name: "RecipientGroup_j8k2m5n9"
- Display name: "RecipientGroup_j8k2m5n9"
- Description: "Description for RecipientGroup_j8k2m5n9"
- Consistent throughout test ✅

---

## Example 5: Timestamp-Based Names for Time-Sensitive Tests

### Scenario: Create daily report

```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='reportName']",
    "value": "%timestamp_name:DailyReport%",
    "element_purpose": "Enter report name with timestamp"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='reportDescription']",
    "value": "Generated on %timestamp_name%",
    "element_purpose": "Enter description with timestamp"
  }
]
```

**Result**:
- Report name: "DailyReport_20250129_143052"
- Description: "Generated on 20250129_143052"
- Timestamp shows when test ran ✅

---

## Example 6: UUID for Guaranteed Uniqueness

### Scenario: Critical entity requiring absolute uniqueness

```json
{
  "action": "type",
  "element_locator": "//input[@id='transactionId']",
  "value": "%uuid_name:TXN:false%",
  "element_purpose": "Enter transaction ID with full UUID"
}
```

**Result**: "TXN_a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d"
- Full UUID for guaranteed uniqueness ✅

---

## Example 7: Complex Form with Multiple Dynamic Fields

### Scenario: Complete user registration form

```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='username']",
    "value": "%unique_name:User%",
    "element_purpose": "Enter unique username"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='email']",
    "value": "%unique_name%@test.com",
    "element_purpose": "Enter unique email"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='firstName']",
    "value": "%unique_name:FirstName%",
    "element_purpose": "Enter unique first name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='lastName']",
    "value": "%unique_name:LastName%",
    "element_purpose": "Enter unique last name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='companyName']",
    "value": "%unique_name:Company%",
    "element_purpose": "Enter unique company name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='password']",
    "value": "%password%",
    "element_purpose": "Enter password from environment"
  }
]
```

**Result**:
- Username: "User_a7b3c9d2"
- Email: "f4e8d1a6@test.com"
- First name: "FirstName_h3k9m2n5"
- Last name: "LastName_j8k2m5n9"
- Company: "Company_p7q3r6s8"
- Password: (from environment variable)
- All fields unique ✅

---

## Comparison Table

| Scenario | Old (Hardcoded) | New (Dynamic) | Benefit |
|----------|----------------|---------------|---------|
| Client name | "Test Client" | "%unique_name:Client%" → "Client_a7b3c9d2" | No duplicates |
| Email | "test@test.com" | "%unique_name%@test.com" → "a7b3c9d2@test.com" | Unique emails |
| Group name | "My Group" | "%unique_name:Group%" → "Group_f4e8d1a6" | Parallel tests |
| User name | "John Doe" | "%unique_name:User%" → "User_h3k9m2n5" | Reusable tests |
| Report | "Daily Report" | "%timestamp_name:Report%" → "Report_20250129_143052" | Time context |

---

## Best Practices

### ✅ DO:
- Use `%unique_name:Prefix%` for most entity names
- Use `%timestamp_name%` for time-based entities
- Use `%uuid_name%` when guaranteed uniqueness is critical
- Use consistent prefixes (Client, User, Group) for clarity
- Reuse same variable when same value needed multiple times

### ❌ DON'T:
- Don't use hardcoded names like "Test Client"
- Don't use common names like "John Doe"
- Don't use sequential numbers manually (use `%sequential_name%` instead)
- Don't forget the `%` symbols around variables
- Don't use `-` or `_` as separators (use `:` instead)

---

## Migration Checklist

When updating existing tests:

- [ ] Identify all hardcoded names in test steps
- [ ] Replace with appropriate dynamic variables
- [ ] Test locally to verify unique name generation
- [ ] Verify consistency (same variable = same value in test)
- [ ] Run test multiple times to confirm no duplicates
- [ ] Update test documentation with new variable usage

---

---

## Example 8: Dynamic Dropdown Selection

### Scenario: Create recipient group with random client selection

**Old Approach (Hardcoded - Flaky)**:
```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='RecipientGroupEditForm_name']",
    "value": "Test Group",
    "element_purpose": "Enter group name"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='RecipientGroupEditForm_clientId']",
    "value": "35",
    "element_purpose": "Select client from dropdown"
  }
]
```

**Problem**: 
- Hardcoded name "Test Group" causes duplicates ❌
- Hardcoded client ID "35" may not exist ❌

**New Approach (Dynamic - Robust)**:
```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='RecipientGroupEditForm_name']",
    "value": "%unique_name:Group%",
    "element_purpose": "Enter unique group name"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='RecipientGroupEditForm_clientId']",
    "value": "%random_option%",
    "element_purpose": "Select random client from dropdown"
  }
]
```

**Result**:
- Group name: "Group_j8k2m5n9" (unique) ✅
- Client: Randomly selected from available options (e.g., "47" - "Client ABC") ✅
- Works regardless of data changes ✅

---

## Example 9: Complete Form with Dynamic Names and Dropdowns

### Scenario: Create user with all dynamic fields

```json
[
  {
    "action": "type",
    "element_locator": "//input[@id='firstName']",
    "value": "%unique_name:User%",
    "element_purpose": "Enter unique first name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='lastName']",
    "value": "TestUser",
    "element_purpose": "Enter last name"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='email']",
    "value": "%unique_name%@test.com",
    "element_purpose": "Enter unique email"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='clientId']",
    "value": "%random_option%",
    "element_purpose": "Select random client"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='roleId']",
    "value": "%random_option%",
    "element_purpose": "Select random role"
  },
  {
    "action": "select",
    "element_locator": "//select[@id='departmentId']",
    "value": "%random_option%",
    "element_purpose": "Select random department"
  },
  {
    "action": "type",
    "element_locator": "//input[@id='password']",
    "value": "%password%",
    "element_purpose": "Enter password from environment"
  }
]
```

**Result**:
- First name: "User_f4e8d1a6" (unique)
- Email: "a7b3c9d2@test.com" (unique)
- Client: Randomly selected (e.g., "Client ABC")
- Role: Randomly selected (e.g., "Admin")
- Department: Randomly selected (e.g., "IT")
- All fields dynamic and robust ✅

---

## Comparison Table (Updated)

| Scenario | Old (Hardcoded) | New (Dynamic) | Benefit |
|----------|----------------|---------------|---------|
| Client name | "Test Client" | "%unique_name:Client%" → "Client_a7b3c9d2" | No duplicates |
| Email | "test@test.com" | "%unique_name%@test.com" → "a7b3c9d2@test.com" | Unique emails |
| Group name | "My Group" | "%unique_name:Group%" → "Group_f4e8d1a6" | Parallel tests |
| User name | "John Doe" | "%unique_name:User%" → "User_h3k9m2n5" | Reusable tests |
| Report | "Daily Report" | "%timestamp_name:Report%" → "Report_20250129_143052" | Time context |
| **Client dropdown** | **"35"** | **"%random_option%"** → **Selects any valid client** | **No hardcoded IDs** |
| **Category dropdown** | **"category_123"** | **"%random_option%"** → **Selects any category** | **Data independence** |
| **Status dropdown** | **"active"** | **"%random_option%"** → **Selects any status** | **Flexible testing** |

---

## Summary

Dynamic name generation and dropdown selection transform:
- ❌ "Test Client" (fails on duplicate)
- ✅ "%unique_name:Client%" → "Client_a7b3c9d2" (always unique)
- ❌ "35" (fails if ID doesn't exist)
- ✅ "%random_option%" → Selects any valid option (always works)

**Result**: Reliable, reusable, parallel-safe, data-independent tests! 🎉
