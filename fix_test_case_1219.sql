-- Fix Step 2 for test case 1219
-- Add Authorization header and extract_variables for group_id

UPDATE test_steps 
SET description = '{
  "method": "PUT",
  "endpoint": "{{base_url}}/api/recipient-groups",
  "headers": {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": "Bearer {{access_token}}"
  },
  "body": {
    "name": "Test Automation Lifecycle Group"
  },
  "expected_status": 200,
  "extract_variables": {
    "group_id": "$.recipient-group.id"
  }
}'
WHERE id = 565 AND test_case_id = 1219;

-- Verify the fix
SELECT id, step_order, action, description 
FROM test_steps 
WHERE test_case_id = 1219 
ORDER BY step_order;
