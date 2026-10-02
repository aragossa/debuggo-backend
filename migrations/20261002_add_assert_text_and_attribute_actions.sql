-- Allow two assertion actions in test_steps:
--   assert_text      - exact text match. The generation prompt offers it and TestRunner.execute_step
--                      runs it, but the constraint rejected it, so passed assertions were never saved.
--   assert_attribute - attribute check, value is "attribute=expected" (e.g. "aria-valuenow=0").
ALTER TABLE public.test_steps DROP CONSTRAINT IF EXISTS valid_action;

ALTER TABLE public.test_steps ADD CONSTRAINT valid_action CHECK ((action = ANY (ARRAY[
    'click'::text, 'type'::text, 'select'::text, 'hover'::text, 'wait'::text,
    'assert'::text, 'assert_text'::text, 'assert_text_contains'::text, 'assert_attribute'::text,
    'scroll'::text, 'clear'::text, 'navigate'::text, 'press_key'::text, 'use_component'::text,
    'assert_element_is_visible'::text, 'assert_element_exists'::text, 'assert_element_not_visible'::text,
    'assert_element_enabled'::text, 'assert_element_disabled'::text,
    'assert_text_equals'::text, 'assert_text_not_contains'::text,
    'assert_url_contains'::text, 'assert_title_contains'::text,
    'wait_for_element_to_be_visible'::text, 'wait_for_element_visible'::text,
    'wait_for_modal'::text, 'wait_for_clickable'::text,
    'api_request'::text, 'api_auth'::text, 'api_get'::text, 'api_post'::text, 'api_put'::text,
    'api_delete'::text, 'api_patch'::text, 'response_validation'::text, 'validation'::text
])));
