-- What the generator changed in a test after seeing how the API really answers, for a person to confirm.
--
-- A generated API test is run while it is generated, and the model fixes it until it passes. Some of
-- the fixes change what the test expects (a total of 28.5 instead of 30, a status of 201 instead of
-- 200) or drop a step the API refused (a delete answered with 409). The test then passes, but it may
-- have recorded a bug of the API as the expected behaviour. The note says what was changed and why;
-- it is cleared when a person confirms it.

ALTER TABLE test_steps ADD COLUMN IF NOT EXISTS review_notes TEXT;
ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS review_notes TEXT;
