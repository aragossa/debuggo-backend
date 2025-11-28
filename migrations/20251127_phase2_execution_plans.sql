-- Phase 2: Execution Plans
-- This migration adds support for execution plan scheduling, parallel execution, and auto-retry logic

-- 1. Create execution_plans table
CREATE TABLE IF NOT EXISTS execution_plans (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL,
    project_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    plan_type VARCHAR(50) NOT NULL CHECK (plan_type IN ('sequential', 'parallel', 'hybrid')),
    
    -- Scheduling
    schedule_type VARCHAR(50) DEFAULT 'manual' CHECK (schedule_type IN ('manual', 'once', 'recurring', 'cron')),
    scheduled_at TIMESTAMP,
    cron_expression VARCHAR(100),
    recurrence_pattern VARCHAR(100),
    
    -- Execution settings
    max_parallel_suites INTEGER DEFAULT 1,
    max_retries INTEGER DEFAULT 0,
    retry_delay_seconds INTEGER DEFAULT 5,
    timeout_seconds INTEGER DEFAULT 3600,
    
    -- Status
    status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived')),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    created_by UUID NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed_at TIMESTAMP,
    next_execution_at TIMESTAMP
);

CREATE INDEX idx_execution_plans_client_id ON execution_plans(client_id);
CREATE INDEX idx_execution_plans_project_id ON execution_plans(project_id);
CREATE INDEX idx_execution_plans_status ON execution_plans(status);
CREATE INDEX idx_execution_plans_schedule_type ON execution_plans(schedule_type);
CREATE INDEX idx_execution_plans_next_execution ON execution_plans(next_execution_at);

-- 2. Create execution_plan_suites table (junction table for suites in a plan)
CREATE TABLE IF NOT EXISTS execution_plan_suites (
    id SERIAL PRIMARY KEY,
    execution_plan_id INTEGER NOT NULL REFERENCES execution_plans(id) ON DELETE CASCADE,
    test_suite_id INTEGER NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
    execution_order INTEGER NOT NULL,
    
    -- Execution settings per suite
    environment_id INTEGER REFERENCES environments(id),
    timeout_seconds INTEGER,
    max_retries INTEGER,
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'passed', 'failed', 'skipped')),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_execution_plan_suites_plan_id ON execution_plan_suites(execution_plan_id);
CREATE INDEX idx_execution_plan_suites_suite_id ON execution_plan_suites(test_suite_id);
CREATE INDEX idx_execution_plan_suites_status ON execution_plan_suites(status);

-- 3. Create execution_plan_runs table (tracks each execution)
CREATE TABLE IF NOT EXISTS execution_plan_runs (
    id SERIAL PRIMARY KEY,
    execution_plan_id INTEGER NOT NULL REFERENCES execution_plans(id) ON DELETE CASCADE,
    
    -- Execution info
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL CHECK (status IN ('running', 'passed', 'failed', 'partial', 'stopped')),
    
    -- Statistics
    total_suites INTEGER,
    passed_suites INTEGER DEFAULT 0,
    failed_suites INTEGER DEFAULT 0,
    skipped_suites INTEGER DEFAULT 0,
    
    total_tests INTEGER,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    skipped_tests INTEGER DEFAULT 0,
    
    -- Timing
    duration_seconds DECIMAL(10, 2),
    
    -- Metadata
    triggered_by VARCHAR(50) DEFAULT 'manual' CHECK (triggered_by IN ('manual', 'schedule', 'webhook', 'api')),
    triggered_by_user_id UUID,
    
    -- Logs
    error_message TEXT,
    execution_log TEXT
);

CREATE INDEX idx_execution_plan_runs_plan_id ON execution_plan_runs(execution_plan_id);
CREATE INDEX idx_execution_plan_runs_status ON execution_plan_runs(status);
CREATE INDEX idx_execution_plan_runs_started_at ON execution_plan_runs(started_at);

-- 4. Create execution_plan_suite_runs table (tracks each suite execution in a plan run)
CREATE TABLE IF NOT EXISTS execution_plan_suite_runs (
    id SERIAL PRIMARY KEY,
    execution_plan_run_id INTEGER NOT NULL REFERENCES execution_plan_runs(id) ON DELETE CASCADE,
    execution_plan_suite_id INTEGER NOT NULL REFERENCES execution_plan_suites(id) ON DELETE CASCADE,
    test_suite_id INTEGER NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
    
    -- Execution info
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL CHECK (status IN ('running', 'passed', 'failed', 'skipped', 'retrying')),
    
    -- Statistics
    total_tests INTEGER,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    skipped_tests INTEGER DEFAULT 0,
    
    -- Retry info
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER,
    
    -- Timing
    duration_seconds DECIMAL(10, 2),
    
    -- Metadata
    error_message TEXT,
    execution_log TEXT
);

CREATE INDEX idx_execution_plan_suite_runs_plan_run_id ON execution_plan_suite_runs(execution_plan_run_id);
CREATE INDEX idx_execution_plan_suite_runs_suite_id ON execution_plan_suite_runs(test_suite_id);
CREATE INDEX idx_execution_plan_suite_runs_status ON execution_plan_suite_runs(status);

-- 5. Create retry_history table (tracks retry attempts)
CREATE TABLE IF NOT EXISTS retry_history (
    id SERIAL PRIMARY KEY,
    execution_plan_suite_run_id INTEGER NOT NULL REFERENCES execution_plan_suite_runs(id) ON DELETE CASCADE,
    
    -- Retry info
    retry_number INTEGER NOT NULL,
    attempted_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL CHECK (status IN ('running', 'passed', 'failed')),
    
    -- Statistics
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    
    -- Metadata
    error_message TEXT,
    execution_log TEXT
);

CREATE INDEX idx_retry_history_suite_run_id ON retry_history(execution_plan_suite_run_id);
CREATE INDEX idx_retry_history_attempted_at ON retry_history(attempted_at);

-- 6. Create execution_plan_notifications table (for alerts and notifications)
CREATE TABLE IF NOT EXISTS execution_plan_notifications (
    id SERIAL PRIMARY KEY,
    execution_plan_id INTEGER NOT NULL REFERENCES execution_plans(id) ON DELETE CASCADE,
    
    -- Notification settings
    notify_on_start BOOLEAN DEFAULT FALSE,
    notify_on_completion BOOLEAN DEFAULT TRUE,
    notify_on_failure BOOLEAN DEFAULT TRUE,
    notify_on_retry BOOLEAN DEFAULT FALSE,
    
    -- Recipients
    email_recipients TEXT, -- JSON array of email addresses
    webhook_urls TEXT, -- JSON array of webhook URLs
    slack_channels TEXT, -- JSON array of Slack channels
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_execution_plan_notifications_plan_id ON execution_plan_notifications(execution_plan_id);

-- 7. Create execution_plan_history table (for audit trail)
CREATE TABLE IF NOT EXISTS execution_plan_history (
    id SERIAL PRIMARY KEY,
    execution_plan_id INTEGER NOT NULL REFERENCES execution_plans(id) ON DELETE CASCADE,
    
    -- Change info
    action VARCHAR(50) NOT NULL CHECK (action IN ('created', 'updated', 'executed', 'paused', 'resumed', 'deleted')),
    changed_by UUID NOT NULL,
    
    -- Details
    old_values JSONB,
    new_values JSONB,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_execution_plan_history_plan_id ON execution_plan_history(execution_plan_id);
CREATE INDEX idx_execution_plan_history_created_at ON execution_plan_history(created_at);

-- 8. Create function to calculate next execution time
CREATE OR REPLACE FUNCTION calculate_next_execution_time(
    p_schedule_type VARCHAR,
    p_cron_expression VARCHAR,
    p_recurrence_pattern VARCHAR
) RETURNS TIMESTAMP AS $$
DECLARE
    v_next_time TIMESTAMP;
BEGIN
    CASE p_schedule_type
        WHEN 'once' THEN
            -- One-time execution, no next time
            RETURN NULL;
        WHEN 'recurring' THEN
            -- Simple recurring pattern (e.g., "daily", "weekly", "monthly")
            CASE p_recurrence_pattern
                WHEN 'daily' THEN
                    v_next_time := CURRENT_TIMESTAMP + INTERVAL '1 day';
                WHEN 'weekly' THEN
                    v_next_time := CURRENT_TIMESTAMP + INTERVAL '7 days';
                WHEN 'monthly' THEN
                    v_next_time := CURRENT_TIMESTAMP + INTERVAL '1 month';
                ELSE
                    v_next_time := CURRENT_TIMESTAMP + INTERVAL '1 day';
            END CASE;
            RETURN v_next_time;
        WHEN 'cron' THEN
            -- For cron, we would need a cron parser library
            -- For now, return NULL and handle in application code
            RETURN NULL;
        ELSE
            RETURN NULL;
    END CASE;
END;
$$ LANGUAGE plpgsql;

-- 9. Create function to update execution plan timestamp
CREATE OR REPLACE FUNCTION update_execution_plan_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_execution_plan_timestamp ON execution_plans;
CREATE TRIGGER trigger_update_execution_plan_timestamp
BEFORE UPDATE ON execution_plans
FOR EACH ROW
EXECUTE FUNCTION update_execution_plan_timestamp();

-- 10. Create function to log execution plan history
CREATE OR REPLACE FUNCTION log_execution_plan_history(
    p_execution_plan_id INTEGER,
    p_action VARCHAR,
    p_changed_by UUID,
    p_old_values JSONB,
    p_new_values JSONB
) RETURNS VOID AS $$
BEGIN
    INSERT INTO execution_plan_history (
        execution_plan_id, action, changed_by, old_values, new_values
    ) VALUES (
        p_execution_plan_id, p_action, p_changed_by, p_old_values, p_new_values
    );
END;
$$ LANGUAGE plpgsql;

-- 11. Create view for execution plan statistics
CREATE OR REPLACE VIEW v_execution_plan_stats AS
SELECT 
    ep.id,
    ep.name,
    ep.status,
    COUNT(DISTINCT eps.test_suite_id) as total_suites,
    COUNT(DISTINCT epr.id) as total_runs,
    SUM(CASE WHEN epr.status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
    SUM(CASE WHEN epr.status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
    ep.last_executed_at,
    ep.next_execution_at
FROM execution_plans ep
LEFT JOIN execution_plan_suites eps ON ep.id = eps.execution_plan_id
LEFT JOIN execution_plan_runs epr ON ep.id = epr.execution_plan_id
WHERE ep.is_active = TRUE
GROUP BY ep.id, ep.name, ep.status, ep.last_executed_at, ep.next_execution_at;

-- 12. Create view for recent execution plan runs
CREATE OR REPLACE VIEW v_recent_execution_plan_runs AS
SELECT 
    epr.id,
    ep.name as plan_name,
    epr.status,
    epr.started_at,
    epr.completed_at,
    epr.duration_seconds,
    epr.total_suites,
    epr.passed_suites,
    epr.failed_suites,
    epr.total_tests,
    epr.passed_tests,
    epr.failed_tests,
    epr.triggered_by
FROM execution_plan_runs epr
JOIN execution_plans ep ON epr.execution_plan_id = ep.id
WHERE ep.is_active = TRUE
ORDER BY epr.started_at DESC
LIMIT 100;

COMMIT;
