-- Phase 1: Core Test Management System
-- Date: 2025-11-25
-- Purpose: Test suites, enhanced variables, and execution tracking

-- ============================================================================
-- ENHANCE EXISTING TABLES
-- ============================================================================

-- Enhance test_variables with scoping support
ALTER TABLE test_variables
    ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS environment_id INTEGER REFERENCES environments(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS scope VARCHAR(20) DEFAULT 'global' 
        CHECK (scope IN ('global', 'client', 'project', 'environment')),
    ADD COLUMN IF NOT EXISTS is_encrypted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS description TEXT;

-- Create index for efficient variable lookup by scope
CREATE INDEX IF NOT EXISTS idx_test_variables_scope 
    ON test_variables(client_id, project_id, environment_id, scope);

-- Enhance test_runs with suite and plan tracking
ALTER TABLE test_runs
    ADD COLUMN IF NOT EXISTS environment_id INTEGER REFERENCES environments(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS execution_plan_id INTEGER REFERENCES execution_plans(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS suite_id INTEGER REFERENCES test_suites(id) ON DELETE SET NULL;

-- ============================================================================
-- NEW TABLES
-- ============================================================================

-- Test Suites: Organize related test cases into logical groups
CREATE TABLE IF NOT EXISTS test_suites (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parent_suite_id INTEGER REFERENCES test_suites(id) ON DELETE CASCADE,
    suite_type VARCHAR(20) DEFAULT 'static' CHECK (suite_type IN ('static', 'dynamic', 'smart')),
    default_environment_id INTEGER REFERENCES environments(id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_test_suites_client ON test_suites(client_id);
CREATE INDEX IF NOT EXISTS idx_test_suites_project ON test_suites(project_id);
CREATE INDEX IF NOT EXISTS idx_test_suites_parent ON test_suites(parent_suite_id);

-- Suite Test Cases: Link test cases to suites with execution order
CREATE TABLE IF NOT EXISTS suite_test_cases (
    id SERIAL PRIMARY KEY,
    suite_id INTEGER NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    execution_order INTEGER DEFAULT 0,
    environment_override_id INTEGER REFERENCES environments(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(suite_id, test_case_id)
);

CREATE INDEX IF NOT EXISTS idx_suite_test_cases_suite ON suite_test_cases(suite_id);
CREATE INDEX IF NOT EXISTS idx_suite_test_cases_test ON suite_test_cases(test_case_id);

-- Execution Plans: Define how, when, and where tests run
CREATE TABLE IF NOT EXISTS execution_plans (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    environment_id INTEGER REFERENCES environments(id) ON DELETE SET NULL,
    max_parallel_tests INTEGER DEFAULT 4,
    retry_failed_tests BOOLEAN DEFAULT FALSE,
    schedule_type VARCHAR(20) DEFAULT 'manual' CHECK (schedule_type IN ('manual', 'scheduled', 'triggered')),
    cron_expression VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    browser_config JSONB DEFAULT '{}',
    notification_config JSONB DEFAULT '{}',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_execution_plans_client ON execution_plans(client_id);
CREATE INDEX IF NOT EXISTS idx_execution_plans_project ON execution_plans(project_id);
CREATE INDEX IF NOT EXISTS idx_execution_plans_schedule ON execution_plans(schedule_type, is_active);

-- Execution Plan Runs: Track individual plan executions
CREATE TABLE IF NOT EXISTS execution_plan_runs (
    id SERIAL PRIMARY KEY,
    execution_plan_id INTEGER NOT NULL REFERENCES execution_plans(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'stopped')),
    total_tests INTEGER DEFAULT 0,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    skipped_tests INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    triggered_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_execution_plan_runs_plan ON execution_plan_runs(execution_plan_id);
CREATE INDEX IF NOT EXISTS idx_execution_plan_runs_status ON execution_plan_runs(status);
CREATE INDEX IF NOT EXISTS idx_execution_plan_runs_created ON execution_plan_runs(created_at);

-- Test Metrics: Track test health and performance
CREATE TABLE IF NOT EXISTS test_metrics (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    environment_id INTEGER REFERENCES environments(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_runs INTEGER DEFAULT 0,
    passed_runs INTEGER DEFAULT 0,
    failed_runs INTEGER DEFAULT 0,
    avg_execution_time_seconds FLOAT,
    pass_rate FLOAT,
    flakiness_score FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_case_id, environment_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_test_metrics_test ON test_metrics(test_case_id);
CREATE INDEX IF NOT EXISTS idx_test_metrics_environment ON test_metrics(environment_id);
CREATE INDEX IF NOT EXISTS idx_test_metrics_date ON test_metrics(metric_date);

-- Flaky Tests: Track and manage unreliable tests
CREATE TABLE IF NOT EXISTS flaky_tests (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    environment_id INTEGER REFERENCES environments(id) ON DELETE CASCADE,
    flakiness_score FLOAT NOT NULL,
    failure_pattern JSONB,
    recommended_action TEXT,
    status VARCHAR(20) DEFAULT 'detected' CHECK (status IN ('detected', 'investigating', 'fixed', 'ignored')),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_flaky_tests_test ON flaky_tests(test_case_id);
CREATE INDEX IF NOT EXISTS idx_flaky_tests_environment ON flaky_tests(environment_id);
CREATE INDEX IF NOT EXISTS idx_flaky_tests_status ON flaky_tests(status);

-- Requirements: Link tests to business requirements
CREATE TABLE IF NOT EXISTS requirements (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    requirement_type VARCHAR(50) DEFAULT 'functional',
    priority VARCHAR(20) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'implemented', 'verified', 'deprecated')),
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, project_id, requirement_id)
);

CREATE INDEX IF NOT EXISTS idx_requirements_client ON requirements(client_id);
CREATE INDEX IF NOT EXISTS idx_requirements_project ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_requirements_status ON requirements(status);

-- Test Requirement Mapping: Link tests to requirements
CREATE TABLE IF NOT EXISTS test_requirement_mapping (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    coverage_type VARCHAR(50) DEFAULT 'full' CHECK (coverage_type IN ('full', 'partial', 'exploratory')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_case_id, requirement_id)
);

CREATE INDEX IF NOT EXISTS idx_test_requirement_mapping_test ON test_requirement_mapping(test_case_id);
CREATE INDEX IF NOT EXISTS idx_test_requirement_mapping_requirement ON test_requirement_mapping(requirement_id);

-- ============================================================================
-- AUTOMATIC TIMESTAMP TRIGGERS
-- ============================================================================

-- Update test_suites.updated_at
CREATE OR REPLACE FUNCTION update_test_suites_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_test_suites_timestamp ON test_suites;
CREATE TRIGGER trigger_update_test_suites_timestamp
    BEFORE UPDATE ON test_suites
    FOR EACH ROW
    EXECUTE FUNCTION update_test_suites_timestamp();

-- Update execution_plans.updated_at
CREATE OR REPLACE FUNCTION update_execution_plans_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_execution_plans_timestamp ON execution_plans;
CREATE TRIGGER trigger_update_execution_plans_timestamp
    BEFORE UPDATE ON execution_plans
    FOR EACH ROW
    EXECUTE FUNCTION update_execution_plans_timestamp();

-- Update requirements.updated_at
CREATE OR REPLACE FUNCTION update_requirements_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_requirements_timestamp ON requirements;
CREATE TRIGGER trigger_update_requirements_timestamp
    BEFORE UPDATE ON requirements
    FOR EACH ROW
    EXECUTE FUNCTION update_requirements_timestamp();

-- Update flaky_tests.updated_at
CREATE OR REPLACE FUNCTION update_flaky_tests_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_flaky_tests_timestamp ON flaky_tests;
CREATE TRIGGER trigger_update_flaky_tests_timestamp
    BEFORE UPDATE ON flaky_tests
    FOR EACH ROW
    EXECUTE FUNCTION update_flaky_tests_timestamp();

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Phase 1 tables created successfully
-- Next: Implement SuiteService and API endpoints
