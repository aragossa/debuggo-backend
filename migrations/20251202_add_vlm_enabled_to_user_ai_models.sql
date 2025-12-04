-- Add vlm_enabled column to user_ai_models table
-- Default is FALSE as requested

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_ai_models'
        AND column_name = 'vlm_enabled'
    ) THEN
        ALTER TABLE user_ai_models
        ADD COLUMN vlm_enabled BOOLEAN DEFAULT FALSE;
    END IF;
END $$;
