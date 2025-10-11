-- Migration: Add API-specific action types to test_steps
-- Date: 2025-09-30
-- Description: Extends the valid_action constraint to support API test actions

-- Drop the existing constraint
ALTER TABLE test_steps DROP CONSTRAINT IF EXISTS valid_action;

-- Add new constraint with API action types
ALTER TABLE test_steps ADD CONSTRAINT valid_action CHECK (
    action = ANY (ARRAY[
        -- UI actions (existing)
        'click'::text,
        'type'::text,
        'select'::text,
        'hover'::text,
        'wait'::text,
        'assert'::text,
        'assert_text_contains'::text,
        'scroll'::text,
        'clear'::text,
        'navigate'::text,
        'press_key'::text,
        'use_component'::text,
        -- API actions (new)
        'api_request'::text,
        'api_auth'::text,
        'api_get'::text,
        'api_post'::text,
        'api_put'::text,
        'api_delete'::text,
        'api_patch'::text,
        'response_validation'::text,
        'validation'::text
    ])
);

-- Add comment to document the change
COMMENT ON CONSTRAINT valid_action ON test_steps IS 
'Validates action types for both UI and API test steps. UI actions use browser automation, API actions use HTTP requests.';
