-- Fix triggered_by_user_id type mismatch
-- Change column from UUID to VARCHAR to support integer IDs as strings

BEGIN;

DO $$ 
BEGIN
    -- Check if column exists and is of type uuid
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'execution_suite_plan_runs' 
        AND column_name = 'triggered_by_user_id' 
        AND data_type = 'uuid'
    ) THEN
        -- Alter column type to VARCHAR(50)
        ALTER TABLE execution_suite_plan_runs 
        ALTER COLUMN triggered_by_user_id TYPE VARCHAR(50) USING triggered_by_user_id::text;
    END IF;
END $$;

COMMIT;
