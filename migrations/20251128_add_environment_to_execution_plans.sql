-- Migration: Add environment_id to execution_suite_plans
-- Date: 2025-11-28
-- Description: Adds environment selection to execution plans

-- Add environment_id column to execution_suite_plans
ALTER TABLE execution_suite_plans 
ADD COLUMN IF NOT EXISTS environment_id INTEGER REFERENCES environments(id);

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_execution_suite_plans_environment 
ON execution_suite_plans(environment_id);

-- Comment
COMMENT ON COLUMN execution_suite_plans.environment_id IS 'The environment to use for test execution';
