-- Migration: Add A/B Test Result Tracking
-- Date: 2025-11-20
-- Description: Add table to track individual test runs for A/B tests

-- Add ab_test_id column to test_runs table to link runs to A/B tests
ALTER TABLE test_runs 
ADD COLUMN IF NOT EXISTS ab_test_id INTEGER REFERENCES ab_test_results(id) ON DELETE SET NULL;

-- Add variant column to track which variant (A or B) was executed
ALTER TABLE test_runs 
ADD COLUMN IF NOT EXISTS ab_variant VARCHAR(1) CHECK (ab_variant IN ('A', 'B'));

-- Create index for faster A/B test result queries
CREATE INDEX IF NOT EXISTS idx_test_runs_ab_test_id ON test_runs(ab_test_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_ab_variant ON test_runs(ab_variant);

-- Create index for finding runs by A/B test and variant
CREATE INDEX IF NOT EXISTS idx_test_runs_ab_test_variant ON test_runs(ab_test_id, ab_variant);
