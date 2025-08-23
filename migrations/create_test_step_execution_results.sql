-- Migration: Create test step execution results table
-- This table tracks the execution results of individual test steps during test runs

CREATE TABLE IF NOT EXISTS test_step_execution_results (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    test_step_id INTEGER NOT NULL REFERENCES test_steps(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('passed', 'failed', 'skipped', 'running')),
    error_message TEXT,
    screenshot_path TEXT,
    screenshot_base64 TEXT,
    execution_time_ms INTEGER,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    additional_info JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_test_step_execution_results_test_run_id ON test_step_execution_results(test_run_id);
CREATE INDEX IF NOT EXISTS idx_test_step_execution_results_test_step_id ON test_step_execution_results(test_step_id);
CREATE INDEX IF NOT EXISTS idx_test_step_execution_results_status ON test_step_execution_results(status);
CREATE INDEX IF NOT EXISTS idx_test_step_execution_results_step_order ON test_step_execution_results(test_run_id, step_order);

-- Add comments for documentation
COMMENT ON TABLE test_step_execution_results IS 'Tracks execution results for individual test steps during test runs';
COMMENT ON COLUMN test_step_execution_results.test_run_id IS 'Reference to the test run this step execution belongs to';
COMMENT ON COLUMN test_step_execution_results.test_step_id IS 'Reference to the test step being executed';
COMMENT ON COLUMN test_step_execution_results.step_order IS 'Order of step execution within the test run';
COMMENT ON COLUMN test_step_execution_results.status IS 'Execution status: passed, failed, skipped, or running';
COMMENT ON COLUMN test_step_execution_results.error_message IS 'Error message if step failed';
COMMENT ON COLUMN test_step_execution_results.screenshot_path IS 'File path to screenshot taken during step execution';
COMMENT ON COLUMN test_step_execution_results.screenshot_base64 IS 'Base64 encoded screenshot data';
COMMENT ON COLUMN test_step_execution_results.execution_time_ms IS 'Step execution time in milliseconds';
COMMENT ON COLUMN test_step_execution_results.additional_info IS 'Additional execution metadata in JSON format';
