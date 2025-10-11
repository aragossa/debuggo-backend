-- Fix Step 2 for test case 1219 (current step IDs: 584-593)
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
    "name": "Test Automation Group - {{timestamp}}"
  },
  "expected_status": 200,
  "extract_variables": {
    "group_id": "$.recipient-group.id"
  }
}'
WHERE test_case_id = 1219 AND step_order = 2;

-- Verify the fix
SELECT id, step_order, 
       description::json->>'method' as method,
       description::json->'headers'->>'Authorization' as auth_header,
       description::json->'extract_variables'->>'group_id' as extracts_group_id
FROM test_steps 
WHERE test_case_id = 1219 AND step_order IN (1, 2, 3)
ORDER BY step_order;
