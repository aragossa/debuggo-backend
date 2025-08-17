-- Migration: Add test steps generation timing columns to test_cases table
-- This migration adds two timestamp columns to track when test steps generation starts and ends

-- Check if columns already exist before adding them
DO $$
BEGIN
    -- Add steps_generation_start_time if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'test_cases' 
        AND column_name = 'steps_generation_start_time'
    ) THEN
        ALTER TABLE public.test_cases 
        ADD COLUMN steps_generation_start_time timestamp with time zone;
        
        RAISE NOTICE 'Added steps_generation_start_time column to test_cases table';
    ELSE
        RAISE NOTICE 'Column steps_generation_start_time already exists in test_cases table';
    END IF;

    -- Add steps_generation_end_time if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'test_cases' 
        AND column_name = 'steps_generation_end_time'
    ) THEN
        ALTER TABLE public.test_cases 
        ADD COLUMN steps_generation_end_time timestamp with time zone;
        
        RAISE NOTICE 'Added steps_generation_end_time column to test_cases table';
    ELSE
        RAISE NOTICE 'Column steps_generation_end_time already exists in test_cases table';
    END IF;
END $$;

-- Add comment to the columns
COMMENT ON COLUMN public.test_cases.steps_generation_start_time IS 'Timestamp when test steps generation started';
COMMENT ON COLUMN public.test_cases.steps_generation_end_time IS 'Timestamp when test steps generation completed';

-- Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration completed: Added test steps generation timing columns to test_cases table';
END $$;
