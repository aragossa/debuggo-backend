-- Migration: Add error_message column to test_steps table
-- Date: 2025-08-27
-- Description: Add error_message column to store error information when test steps fail

ALTER TABLE test_steps 
ADD COLUMN error_message TEXT;

-- Add comment to document the column purpose
COMMENT ON COLUMN test_steps.error_message IS 'Stores error message when test step fails during execution';
