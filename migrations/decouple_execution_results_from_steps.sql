-- Migration: Decouple test step execution results from test steps
-- This allows preserving execution results and screenshots when test steps are regenerated

-- First, add columns to store step information directly in execution results
ALTER TABLE test_step_execution_results 
ADD COLUMN IF NOT EXISTS step_description TEXT,
ADD COLUMN IF NOT EXISTS step_action VARCHAR(50),
ADD COLUMN IF NOT EXISTS step_element_path TEXT,
ADD COLUMN IF NOT EXISTS step_value TEXT,
ADD COLUMN IF NOT EXISTS step_target TEXT;

-- Copy existing step information to execution results before removing constraint
UPDATE test_step_execution_results 
SET 
    step_description = ts.description,
    step_action = ts.action,
    step_element_path = ts.element_path,
    step_value = ts.value,
    step_target = ts.element_path  -- Use element_path as target since target column doesn't exist
FROM test_steps ts 
WHERE test_step_execution_results.test_step_id = ts.id
AND test_step_execution_results.step_description IS NULL;

-- Drop the foreign key constraint to allow test steps to be deleted independently
ALTER TABLE test_step_execution_results 
DROP CONSTRAINT IF EXISTS test_step_execution_results_test_step_id_fkey;

-- Make test_step_id nullable since steps can be deleted but results preserved
ALTER TABLE test_step_execution_results 
ALTER COLUMN test_step_id DROP NOT NULL;

-- Add a new index for performance on nullable test_step_id
CREATE INDEX IF NOT EXISTS idx_test_step_execution_results_test_step_id_nullable 
ON test_step_execution_results(test_step_id) WHERE test_step_id IS NOT NULL;

-- Add comments for the new columns
COMMENT ON COLUMN test_step_execution_results.step_description IS 'Preserved step description from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_action IS 'Preserved step action from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_element_path IS 'Preserved step element path from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_value IS 'Preserved step value from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_target IS 'Preserved step target from when execution occurred';
