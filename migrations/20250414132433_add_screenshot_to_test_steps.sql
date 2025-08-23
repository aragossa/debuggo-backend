-- Migration: add_screenshot_to_test_steps
-- Created at: 2025-04-14 13:24:33 UTC
-- Description: Adds a screenshot column to the test_steps table to store screenshots taken during test step generation and execution

-- Add screenshot column to test_steps table
ALTER TABLE test_steps ADD COLUMN screenshot_path TEXT;

-- Create a new table to store screenshots
CREATE TABLE IF NOT EXISTS  screenshots (
    id SERIAL PRIMARY KEY,
    test_step_id INTEGER NOT NULL,
    screenshot BYTEA NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    FOREIGN KEY (test_step_id) REFERENCES test_steps(id) ON DELETE CASCADE
);

-- Create index on test_step_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_screenshots_test_step_id ON screenshots(test_step_id);

-- To roll back this migration, you can add statements like:
-- ROLLBACK
-- DROP INDEX idx_screenshots_test_step_id;
-- DROP TABLE screenshots;
-- ALTER TABLE test_steps DROP COLUMN screenshot_path;
