# Using Dynamic Placeholders in Your Tests

## What Are Placeholders?

Placeholders are special codes you can use in your test steps that automatically generate realistic data when the test runs. This means you never have to worry about duplicate names, invalid emails, or hardcoded values!

### Why Use Placeholders?

❌ **Without Placeholders:**
```
Name: "Test Client"  ← Will fail if already exists!
Email: "test@test.com"  ← Not realistic, causes duplicates
```

✅ **With Placeholders:**
```
Name: %unique_name:Client%  → Generates: "Client_a7b3c9d2"
Email: %random_email%  → Generates: "john.smith@example.com"
```

**Benefits:**
- ✅ No duplicate data errors
- ✅ Realistic test data
- ✅ Tests can run multiple times
- ✅ Works in any environment

---

## How to Use Placeholders

Simply type the placeholder name with `%` symbols around it:

```
%placeholder_name%
```

The system will automatically replace it with real data when your test runs!

---

## 📚 Placeholder Categories

### 🔑 1. Your Project Settings

Use these to access your project's environment variables:

| Type This | Get This |
|-----------|----------|
| `%base_url%` | Your application URL |
| `%login%` | Your login username/email |
| `%password%` | Your login password |

**Example:**
```
Navigate to: %base_url%/login
Type in username field: %login%
Type in password field: %password%
```

---

### 🏷️ 2. Unique Names (Remember Throughout Test)

Perfect for creating, finding, and deleting entities in your tests:

| Type This | Get This | When to Use |
|-----------|----------|-------------|
| `%unique_name:Client%` | Client_a7b3c9d2 | Client names |
| `%unique_name:User%` | User_f4e8d1a6 | User names |
| `%unique_name:Group%` | Group_x9y2z5w8 | Group names |
| `%timestamp_name:Order%` | Order_20250129_143052 | Time-based names |

**💡 Special Feature:** These placeholders remember their value throughout your entire test!

**Example - Complete Flow:**
```
Step 1: Click "Add Client"
Step 2: Type in name field: %unique_name:Client%
        (Generates: "Client_abc123")
Step 3: Click "Save"

Step 4: Find the client: //td[text()='%unique_name:Client%']
        (Looks for: "Client_abc123" - same name!)

Step 5: Click delete button for: %unique_name:Client%
        (Deletes: "Client_abc123" - same name!)
```

---

### 👤 3. Personal Information

Generate realistic people data:

| Type This | Get This |
|-----------|----------|
| `%random_name%` | John Smith |
| `%random_first_name%` | John |
| `%random_last_name%` | Smith |
| `%random_email%` | john.smith@example.com |
| `%random_phone%` | +12025551234 |
| `%random_username%` | john_smith_123 |

**Example - User Registration:**
```
First Name: %random_first_name%
Last Name: %random_last_name%
Email: %random_email%
Phone: %random_phone%
```

---

### 🏢 4. Business Information

Generate company-related data:

| Type This | Get This |
|-----------|----------|
| `%random_company%` | AcmeCorporation |
| `%random_job_title%` | Software Engineer |

**Example:**
```
Company Name: %random_company%
Job Title: %random_job_title%
```

---

### 📍 5. Location Information

Generate address data:

| Type This | Get This |
|-----------|----------|
| `%random_address%` | 742 Evergreen Terrace |
| `%random_city%` | Springfield |
| `%random_country%` | United States |

**Example - Address Form:**
```
Street: %random_address%
City: %random_city%
Country: %random_country%
```

---

### 🎲 6. Random Data

Generate various types of random data:

| Type This | Get This | Use For |
|-----------|----------|---------|
| `%random_string%` | k7m2p9x4q1 | Random codes |
| `%random_number%` | 7543 | Quantities, IDs |
| `%random_date%` | 2024-03-15 | Dates |
| `%random_color%` | blue | Color selections |
| `%random_url%` | https://www.example.com | Website URLs |

**Example:**
```
Order Number: %random_string%
Quantity: %random_number:1:100%
Delivery Date: %random_date%
```

---

### 📋 7. Dropdown Selections

Special placeholder for automatically selecting from dropdowns:

| Type This | What Happens |
|-----------|--------------|
| `%random_option%` | Picks any valid option from the dropdown |

**When to Use:**
- ✅ When any option is fine for your test
- ✅ When dropdown options vary between environments
- ✅ When testing general functionality

**Example:**
```
Action: select
Element: //select[@id='clientDropdown']
Value: %random_option%
```

---

## 🎯 Common Use Cases

### Creating a New Client

```
Step 1: Click "Add Client" button
Step 2: Type in "Name" field: %unique_name:Client%
Step 3: Type in "Email" field: %random_email%
Step 4: Select from "Category" dropdown: %random_option%
Step 5: Type in "Phone" field: %random_phone%
Step 6: Click "Save"
```

### User Registration Form

```
Step 1: Navigate to: %base_url%/register
Step 2: Type in "First Name": %random_first_name%
Step 3: Type in "Last Name": %random_last_name%
Step 4: Type in "Email": %random_email%
Step 5: Type in "Phone": %random_phone%
Step 6: Type in "Company": %random_company%
Step 7: Type in "Job Title": %random_job_title%
Step 8: Click "Register"
```

### Create, Find, and Delete Pattern

```
# Create
Step 1: Click "Add Group"
Step 2: Type in "Name": %unique_name:Group%
Step 3: Click "Save"

# Find and Verify
Step 4: Wait for element: //td[text()='%unique_name:Group%']
         (Looks for the same group name we created!)

# Edit
Step 5: Click edit button for: %unique_name:Group%
Step 6: Change something
Step 7: Click "Save"

# Delete
Step 8: Click delete button for: %unique_name:Group%
Step 9: Click "Confirm"

# Verify Deleted
Step 10: Verify element doesn't exist: //td[text()='%unique_name:Group%']
```

---

## 💡 Pro Tips

### Tip 1: Combine Placeholders
You can combine multiple placeholders in one value:

```
Email: %unique_name%@test.com
Description: Created by %random_name% on %random_date%
```

### Tip 2: Custom Lengths and Ranges
Some placeholders accept parameters:

```
%random_string:5%  → Generates 5-character string
%random_number:1:100%  → Number between 1 and 100
%random_text:2%  → 2 sentences of text
```

### Tip 3: Date Formats
Customize date format:

```
%random_date%  → 2024-03-15
%random_date:%d/%m/%Y%  → 15/03/2024
%random_date:%B %d, %Y%  → March 15, 2024
```

### Tip 4: Use Unique Names for Consistency
When you need to reference the same entity multiple times in a test, use `%unique_name%`:

```
✅ CORRECT:
Step 5: Create client: %unique_name:Client%
Step 10: Find client: %unique_name:Client%  (same value!)
Step 15: Delete client: %unique_name:Client%  (same value!)

❌ WRONG:
Step 5: Create client: %random_company%
Step 10: Find client: %random_company%  (different value! Won't find it!)
```

---

## ⚠️ Common Mistakes to Avoid

### Mistake 1: Hardcoding Values
```
❌ Bad: Name: "Test Client"
✅ Good: Name: %unique_name:Client%
```

### Mistake 2: Using Random Instead of Unique
```
❌ Bad for entities you need to find later:
    Create: %random_company%
    Find: %random_company%  (generates different value!)

✅ Good:
    Create: %unique_name:Company%
    Find: %unique_name:Company%  (same value!)
```

### Mistake 3: Hardcoding Dropdown IDs
```
❌ Bad: Select option: "35"  (ID 35 might not exist!)
✅ Good: Select option: %random_option%
```

### Mistake 4: Typos in Placeholder Names
```
❌ Bad: %random_emial%  (typo - won't work!)
✅ Good: %random_email%
```

---

## 🆘 Help & Troubleshooting

### Placeholder Not Working?

**Check these:**
1. ✅ Spelling is correct (case-sensitive)
2. ✅ Has `%` on both sides
3. ✅ Placeholder exists (see lists above)
4. ✅ Using correct syntax for parameters

### Need the Same Value Multiple Times?

Use `%unique_name%` variants - they remember their value throughout the test!

### Dropdown Selection Not Working?

Make sure:
1. ✅ Dropdown is loaded before selection
2. ✅ Using `%random_option%` for dynamic options
3. ✅ Add a wait step before selection if needed

---

## 📖 Quick Reference Card

**Print this out or keep it handy!**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MOST USED PLACEHOLDERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment:
  %base_url%  %login%  %password%

Unique Names (Remembers Value):
  %unique_name:Client%  %unique_name:User%
  %unique_name:Group%   %timestamp_name:Order%

Personal Info:
  %random_name%  %random_first_name%  %random_last_name%
  %random_email%  %random_phone%  %random_username%

Business:
  %random_company%  %random_job_title%

Location:
  %random_address%  %random_city%  %random_country%

Random Data:
  %random_string%  %random_number%  %random_date%
  %random_url%  %random_color%

Special:
  %random_option%  (for dropdowns)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🎓 Learn More

Want more details? Check out:
- [Complete Technical Guide](TEST_PLACEHOLDERS_GUIDE.md)
- [Quick Reference](PLACEHOLDERS_QUICK_REFERENCE.md)

---

## 🤝 Need Help?

If you're stuck or have questions:
1. Check the troubleshooting section above
2. Review the examples for your use case
3. Ask your test automation team
4. Submit a feature request if you need a new placeholder type

---

**Remember:** Using placeholders makes your tests more reliable, realistic, and reusable! 🚀

**Last Updated:** November 11, 2025  
**Version:** 1.0 - User Guide
