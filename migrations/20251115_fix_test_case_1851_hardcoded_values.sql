-- Complete Fix for Test Case 1851
-- Addresses all hardcoded values and variables
-- Date: November 15, 2025

-- Issue 1: Step 8 - Hardcoded client ID "35"
-- Fix: Use %random_option% for dynamic dropdown selection
UPDATE test_steps 
SET value = '%random_option%',
    description = 'Select random client from dropdown. Element verified in HTML: id=''RecipientGroupEditForm_clientId'''
WHERE test_case_id = 1851 AND step_order = 8;

-- Issue 2: Step 11 - Hardcoded group name 'Group_vbry9j86' from previous test run
-- Fix: Use %unique_name:Group% variable to match the dynamically generated name from step 7
UPDATE test_steps 
SET element_path = '//tr[td/a[contains(text(), ''%unique_name:Group%'')]]//a[@title=''Delete'']',
    description = 'Click the delete icon for the newly created recipient group. Element verified in HTML: <a href="#del" title="Delete">'
WHERE test_case_id = 1851 AND step_order = 11;

-- Verify the changes
SELECT step_order, action, element_path, value, description 
FROM test_steps 
WHERE test_case_id = 1851 AND step_order IN (7, 8, 11, 14) 
ORDER BY step_order;

-- Expected results after fix:
-- Step 7:  value = '%unique_name:Group%' (already correct)
-- Step 8:  value = '%random_option%' (fixed)
-- Step 11: element_path contains '%unique_name:Group%' (fixed)
-- Step 14: element_path contains '%unique_name:Group%' (already correct)
