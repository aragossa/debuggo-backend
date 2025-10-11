-- Migration: Add test_type column to test_cases table for UI/API categorization
-- Date: 2025-09-27
-- Description: Add test_type column to support test case categorization (UI/API)

-- Add test_type column with default 'ui' for existing records
ALTER TABLE test_cases 
ADD COLUMN test_type VARCHAR(10) DEFAULT 'ui';

-- Add check constraint to ensure only valid test types
ALTER TABLE test_cases 
ADD CONSTRAINT test_cases_test_type_check 
CHECK (test_type IN ('ui', 'api'));

-- Create index for better performance on test_type queries
CREATE INDEX idx_test_cases_test_type ON test_cases(test_type);

-- Update existing test cases to have 'ui' type if they don't have it set
UPDATE test_cases SET test_type = 'ui' WHERE test_type IS NULL;

-- Make the column NOT NULL after setting default values
ALTER TABLE test_cases ALTER COLUMN test_type SET NOT NULL;

-- Comment on the column
COMMENT ON COLUMN test_cases.test_type IS 'Type of test case: ui for UI tests, api for API tests';
