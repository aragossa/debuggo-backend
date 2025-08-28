-- Fix valid_action constraint to allow assert_text_contains
-- Date: 2025-08-27

ALTER TABLE test_steps DROP CONSTRAINT IF EXISTS valid_action;

ALTER TABLE test_steps ADD CONSTRAINT valid_action 
CHECK (action = ANY (ARRAY[
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
    'use_component'::text
]));
