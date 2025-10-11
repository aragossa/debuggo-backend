-- Check Step 2 headers for test case 1219
SELECT 
    id,
    step_order,
    action,
    description::text,
    expected_result
FROM test_steps
WHERE test_case_id = 1219 AND step_order = 2;
