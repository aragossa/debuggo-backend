-- Migration: Add missing columns to test_step_execution_results table
-- This migration adds columns that were missing from the production server

-- Add columns to store step information directly in execution results
ALTER TABLE test_step_execution_results 
ADD COLUMN IF NOT EXISTS step_description TEXT,
ADD COLUMN IF NOT EXISTS step_action VARCHAR(50),
ADD COLUMN IF NOT EXISTS step_element_path TEXT,
ADD COLUMN IF NOT EXISTS step_value TEXT,
ADD COLUMN IF NOT EXISTS step_target TEXT;

-- Add comments for the new columns
COMMENT ON COLUMN test_step_execution_results.step_description IS 'Preserved step description from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_action IS 'Preserved step action from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_element_path IS 'Preserved step element path from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_value IS 'Preserved step value from when execution occurred';
COMMENT ON COLUMN test_step_execution_results.step_target IS 'Preserved step target from when execution occurred';

-- Drop the foreign key constraint to allow test steps to be deleted independently
ALTER TABLE test_step_execution_results 
DROP CONSTRAINT IF EXISTS test_step_execution_results_test_step_id_fkey;

-- Make test_step_id nullable since steps can be deleted but results preserved
ALTER TABLE test_step_execution_results 
ALTER COLUMN test_step_id DROP NOT NULL;

-- Add a new index for performance on nullable test_step_id
CREATE INDEX IF NOT EXISTS idx_test_step_execution_results_test_step_id_nullable 
ON test_step_execution_results(test_step_id) WHERE test_step_id IS NOT NULL;
