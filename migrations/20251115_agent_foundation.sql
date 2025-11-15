-- Phase 1: AI Agent Foundation
-- Migration for ValidationAgent, ExecutionFeedbackCollector, and ConfidenceScorer

-- Table for storing validation results
CREATE TABLE IF NOT EXISTS validation_results (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_id INTEGER NOT NULL REFERENCES test_steps(id) ON DELETE CASCADE,
    is_valid BOOLEAN NOT NULL DEFAULT true,
    errors TEXT[] DEFAULT '{}',
    warnings TEXT[] DEFAULT '{}',
    suggestions TEXT[] DEFAULT '{}',
    confidence FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_case_id, step_id)
);

-- Table for storing execution feedback
CREATE TABLE IF NOT EXISTS execution_feedback (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_id INTEGER NOT NULL REFERENCES test_steps(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    action VARCHAR(50) NOT NULL,
    element_locator TEXT,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    error_details JSONB,
    screenshot_path TEXT,
    html_snapshot TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table for storing confidence scores
CREATE TABLE IF NOT EXISTS confidence_scores (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_id INTEGER NOT NULL REFERENCES test_steps(id) ON DELETE CASCADE,
    overall_confidence FLOAT NOT NULL DEFAULT 0.0,
    selector_confidence FLOAT NOT NULL DEFAULT 0.0,
    action_confidence FLOAT NOT NULL DEFAULT 0.0,
    data_confidence FLOAT NOT NULL DEFAULT 0.0,
    pattern_confidence FLOAT NOT NULL DEFAULT 0.0,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium',
    factors TEXT,
    recommendations TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_case_id, step_id)
);

-- Table for tracking retry attempts
CREATE TABLE IF NOT EXISTS retry_attempts (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_id INTEGER NOT NULL REFERENCES test_steps(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    original_error VARCHAR(100),
    feedback_used TEXT,
    success BOOLEAN NOT NULL DEFAULT false,
    new_selector TEXT,
    new_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_validation_results_test_case ON validation_results(test_case_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_step ON validation_results(step_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_valid ON validation_results(is_valid);

CREATE INDEX IF NOT EXISTS idx_execution_feedback_test_case ON execution_feedback(test_case_id);
CREATE INDEX IF NOT EXISTS idx_execution_feedback_step ON execution_feedback(step_id);
CREATE INDEX IF NOT EXISTS idx_execution_feedback_error_type ON execution_feedback(error_type);
CREATE INDEX IF NOT EXISTS idx_execution_feedback_created ON execution_feedback(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_confidence_scores_test_case ON confidence_scores(test_case_id);
CREATE INDEX IF NOT EXISTS idx_confidence_scores_step ON confidence_scores(step_id);
CREATE INDEX IF NOT EXISTS idx_confidence_scores_risk_level ON confidence_scores(risk_level);
CREATE INDEX IF NOT EXISTS idx_confidence_scores_overall ON confidence_scores(overall_confidence);

CREATE INDEX IF NOT EXISTS idx_retry_attempts_test_case ON retry_attempts(test_case_id);
CREATE INDEX IF NOT EXISTS idx_retry_attempts_step ON retry_attempts(step_id);
CREATE INDEX IF NOT EXISTS idx_retry_attempts_success ON retry_attempts(success);

-- Create trigger to update updated_at timestamp for validation_results
CREATE OR REPLACE FUNCTION update_validation_results_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validation_results_update_timestamp
BEFORE UPDATE ON validation_results
FOR EACH ROW
EXECUTE FUNCTION update_validation_results_timestamp();

-- Create trigger to update updated_at timestamp for confidence_scores
CREATE OR REPLACE FUNCTION update_confidence_scores_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER confidence_scores_update_timestamp
BEFORE UPDATE ON confidence_scores
FOR EACH ROW
EXECUTE FUNCTION update_confidence_scores_timestamp();

-- Add comments for documentation
COMMENT ON TABLE validation_results IS 'Stores validation results for test steps';
COMMENT ON TABLE execution_feedback IS 'Stores feedback from test execution failures';
COMMENT ON TABLE confidence_scores IS 'Stores confidence scores for test steps';
COMMENT ON TABLE retry_attempts IS 'Tracks retry attempts and their outcomes';

COMMENT ON COLUMN validation_results.is_valid IS 'Whether the step passed validation';
COMMENT ON COLUMN validation_results.confidence IS 'Confidence score 0-100';
COMMENT ON COLUMN execution_feedback.error_type IS 'Category of error (selector_not_found, timeout, etc.)';
COMMENT ON COLUMN confidence_scores.risk_level IS 'Risk level: low, medium, high, very_low';
COMMENT ON COLUMN retry_attempts.attempt_number IS 'Which retry attempt this is (1, 2, 3, etc.)';
