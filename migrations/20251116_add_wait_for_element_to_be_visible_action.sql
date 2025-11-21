-- Migration: Add wait_for_element_to_be_visible action type
-- Date: 2025-11-16
-- Description: Adds support for wait_for_element_to_be_visible action which waits for an element to be visible on the page

-- Drop the existing constraint
ALTER TABLE test_steps DROP CONSTRAINT IF EXISTS valid_action;

-- Add new constraint with wait_for_element_to_be_visible action
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
        -- Wait actions (new)
        'wait_for_element_to_be_visible'::text,
        'wait_for_element_visible'::text,
        'wait_for_modal'::text,
        'wait_for_clickable'::text,
        -- API actions (existing)
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
'Validates action types for both UI and API test steps. UI actions use browser automation, API actions use HTTP requests. Wait actions: wait_for_element_to_be_visible, wait_for_modal, wait_for_clickable.';
