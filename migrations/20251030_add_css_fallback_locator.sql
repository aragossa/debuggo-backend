-- Migration: Add CSS fallback locator to test_steps
-- Date: 2025-10-30
-- Description: Adds css_selector column to store CSS selector as fallback when XPath fails

-- Add css_selector column to test_steps table
ALTER TABLE test_steps 
ADD COLUMN IF NOT EXISTS css_selector TEXT;

-- Add comment to explain the column
COMMENT ON COLUMN test_steps.css_selector IS 'CSS selector fallback when element_path (XPath) fails';

-- Update existing rows to have NULL css_selector (will be populated by AI going forward)
-- No need to update existing data as NULL is acceptable

-- Create index for better query performance (optional but recommended)
CREATE INDEX IF NOT EXISTS idx_test_steps_css_selector ON test_steps(css_selector) WHERE css_selector IS NOT NULL;

COMMENT ON INDEX idx_test_steps_css_selector IS 'Index for CSS selector lookups';
