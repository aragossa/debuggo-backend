CREATE TABLE "test_cases" (
    id SERIAL PRIMARY KEY, -- SERIAL automatically handles sequence generation
    name TEXT NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES "test_cases" (id) ON DELETE CASCADE,
    type TEXT CHECK (type IN ('root', 'test', 'group')) NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- PostgreSQL prefers TIMESTAMPTZ for date-time fields
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    test_case_id INTEGER,
    curl TEXT,
    python_script TEXT
);

CREATE TABLE "test_runs" (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES "test_cases" (id) ON DELETE CASCADE,
    run_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    result TEXT NOT NULL,
    exception TEXT,
    duration REAL,
    stdout TEXT,
    stderr TEXT,
    additional_info TEXT
);

CREATE TABLE "test_steps" (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES "test_cases" (id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    description TEXT NOT NULL,
    expected_result TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
