-- Migration: Add missing 'target' column to test_steps table
-- Date: 2025-10-26

-- Add target column to test_steps table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'test_steps' AND column_name = 'target'
    ) THEN
        ALTER TABLE test_steps ADD COLUMN target TEXT;
        RAISE NOTICE 'Added target column to test_steps table';
    ELSE
        RAISE NOTICE 'Target column already exists in test_steps table';
    END IF;
END $$;

-- Update existing records to have empty target if needed
UPDATE test_steps SET target = '' WHERE target IS NULL;

-- Add comment to document the column
COMMENT ON COLUMN test_steps.target IS 'Target element or URL for the test step action';
