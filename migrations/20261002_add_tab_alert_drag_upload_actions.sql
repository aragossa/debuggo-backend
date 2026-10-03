-- Allow six new step actions in test_steps:
--   switch_tab        - switch browser tab; value is "new", "main", a tab number or a part of the title/URL
--   accept_alert      - OK in a native alert/confirm/prompt; value is the text to type into a prompt (optional)
--   dismiss_alert     - Cancel in a native confirm/prompt
--   assert_alert_text - exact text of the open native alert; value is the expected text
--   drag_and_drop     - element_path is the dragged element; value is the XPath of the drop target
--                       ("html5:" prefix forces the HTML5 emulation)
--   upload_file       - element_path is the file input; value is a file name from sample_files/
ALTER TABLE public.test_steps DROP CONSTRAINT IF EXISTS valid_action;

ALTER TABLE public.test_steps ADD CONSTRAINT valid_action CHECK ((action = ANY (ARRAY[
    'click'::text, 'type'::text, 'select'::text, 'hover'::text, 'wait'::text,
    'assert'::text, 'assert_text'::text, 'assert_text_contains'::text, 'assert_attribute'::text,
    'switch_tab'::text, 'accept_alert'::text, 'dismiss_alert'::text, 'assert_alert_text'::text,
    'drag_and_drop'::text, 'upload_file'::text,
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
