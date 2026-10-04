-- What a UI test run touched, for coverage: the API requests its browser sent and the pages it was on.
--
-- test_run_api_calls: the XHR/fetch requests of the page during a run, one row per method + URL +
--   status with the number of times it was sent. The API Coverage page lays them over the calls of
--   the project's API schema: which calls of the backend the UI tests really reach.
-- test_run_pages: the page the browser was on after each step. "page" is the address with ids
--   replaced ("/product/{id}"), so that one page of the application is one row however many items it shows.

CREATE TABLE IF NOT EXISTS test_run_api_calls (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    method VARCHAR(10) NOT NULL,
    url TEXT NOT NULL,
    status INTEGER,
    hits INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_test_run_api_calls_case ON test_run_api_calls(test_case_id, test_run_id);

CREATE TABLE IF NOT EXISTS test_run_pages (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_order INTEGER,
    url TEXT NOT NULL,
    page TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_test_run_pages_case ON test_run_pages(test_case_id, test_run_id);
