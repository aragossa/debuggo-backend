-- Migration: Add support for individual test case execution in execution plans
-- Date: 2025-11-27
-- Purpose: Enable manual/quick run of individual test cases using execution_suite_plans
--          This is part of deprecating test_executions table

-- ============================================================================
-- Table: execution_suite_plan_test_cases
-- Allows individual test cases to be added to execution plans (not just suites)
-- ============================================================================
CREATE TABLE IF NOT EXISTS execution_suite_plan_test_cases (
    id SERIAL PRIMARY KEY,
    execution_suite_plan_id INTEGER NOT NULL REFERENCES execution_suite_plans(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL,
    suite_id INTEGER,  -- Optional: if test case belongs to a suite
    execution_order INTEGER DEFAULT 1,
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds FLOAT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT execution_suite_plan_test_cases_status_check 
        CHECK (status IN ('pending', 'running', 'passed', 'failed', 'skipped', 'error'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_exec_plan_test_cases_plan_id 
    ON execution_suite_plan_test_cases(execution_suite_plan_id);
CREATE INDEX IF NOT EXISTS idx_exec_plan_test_cases_test_case_id 
    ON execution_suite_plan_test_cases(test_case_id);
CREATE INDEX IF NOT EXISTS idx_exec_plan_test_cases_status 
    ON execution_suite_plan_test_cases(status);

-- ============================================================================
-- Table: execution_suite_plan_test_runs
-- Stores individual test run results within an execution plan run
-- ============================================================================
CREATE TABLE IF NOT EXISTS execution_suite_plan_test_runs (
    id SERIAL PRIMARY KEY,
    execution_suite_plan_run_id INTEGER NOT NULL REFERENCES execution_suite_plan_runs(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL,
    suite_id INTEGER,
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds FLOAT,
    error_message TEXT,
    screenshot_path TEXT,
    log_path TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT execution_suite_plan_test_runs_status_check 
        CHECK (status IN ('pending', 'running', 'passed', 'failed', 'skipped', 'error'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_exec_plan_test_runs_run_id 
    ON execution_suite_plan_test_runs(execution_suite_plan_run_id);
CREATE INDEX IF NOT EXISTS idx_exec_plan_test_runs_test_case_id 
    ON execution_suite_plan_test_runs(test_case_id);
CREATE INDEX IF NOT EXISTS idx_exec_plan_test_runs_status 
    ON execution_suite_plan_test_runs(status);

-- ============================================================================
-- Add quick_run flag to execution_suite_plans
-- Allows identification of plans created for quick/manual runs
-- ============================================================================
ALTER TABLE execution_suite_plans 
    ADD COLUMN IF NOT EXISTS is_quick_run BOOLEAN DEFAULT FALSE;

ALTER TABLE execution_suite_plans 
    ADD COLUMN IF NOT EXISTS auto_delete_after_run BOOLEAN DEFAULT FALSE;

-- Index for quick runs
CREATE INDEX IF NOT EXISTS idx_exec_suite_plans_quick_run 
    ON execution_suite_plans(is_quick_run) WHERE is_quick_run = TRUE;

-- ============================================================================
-- Function: Create quick run execution plan
-- Helper function to create a plan for manual test execution
-- ============================================================================
CREATE OR REPLACE FUNCTION create_quick_run_plan(
    p_client_id UUID,
    p_project_id UUID,
    p_name VARCHAR(255),
    p_created_by UUID
) RETURNS INTEGER AS $$
DECLARE
    v_plan_id INTEGER;
BEGIN
    INSERT INTO execution_suite_plans (
        client_id, project_id, name, description,
        plan_type, schedule_type, status,
        is_quick_run, auto_delete_after_run, created_by
    ) VALUES (
        p_client_id, p_project_id, p_name, 'Quick run - manual execution',
        'sequential', 'manual', 'active',
        TRUE, FALSE, p_created_by
    ) RETURNING id INTO v_plan_id;
    
    RETURN v_plan_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Function: Update timestamp trigger for new tables
-- ============================================================================
CREATE OR REPLACE FUNCTION update_exec_plan_test_cases_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_exec_plan_test_cases_timestamp 
    ON execution_suite_plan_test_cases;
CREATE TRIGGER trigger_update_exec_plan_test_cases_timestamp
    BEFORE UPDATE ON execution_suite_plan_test_cases
    FOR EACH ROW EXECUTE FUNCTION update_exec_plan_test_cases_timestamp();

-- ============================================================================
-- View: Quick run plans with their test cases
-- ============================================================================
CREATE OR REPLACE VIEW quick_run_plans_view AS
SELECT 
    esp.id AS plan_id,
    esp.client_id,
    esp.project_id,
    esp.name AS plan_name,
    esp.status AS plan_status,
    esp.created_at AS plan_created_at,
    COUNT(esptc.id) AS test_case_count,
    COUNT(CASE WHEN esptc.status = 'passed' THEN 1 END) AS passed_count,
    COUNT(CASE WHEN esptc.status = 'failed' THEN 1 END) AS failed_count
FROM execution_suite_plans esp
LEFT JOIN execution_suite_plan_test_cases esptc ON esp.id = esptc.execution_suite_plan_id
WHERE esp.is_quick_run = TRUE
GROUP BY esp.id, esp.client_id, esp.project_id, esp.name, esp.status, esp.created_at;

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE execution_suite_plan_test_cases IS 
    'Individual test cases assigned to execution plans for manual/quick runs';
COMMENT ON TABLE execution_suite_plan_test_runs IS 
    'Test run results within an execution plan run';
COMMENT ON COLUMN execution_suite_plans.is_quick_run IS 
    'Flag indicating this plan was created for a quick/manual test run';
COMMENT ON COLUMN execution_suite_plans.auto_delete_after_run IS 
    'If true, plan will be deleted after execution completes';
