-- Migration: Add API conflict notifications table
-- Date: 2025-10-17
-- Description: Store API documentation vs reality conflicts that require user intervention

-- Create conflict notifications table
CREATE TABLE IF NOT EXISTS api_conflict_notifications (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Conflict details
    step_number INTEGER NOT NULL,
    conflict_type VARCHAR(50) NOT NULL DEFAULT 'status_mismatch', -- status_mismatch, schema_mismatch, etc.
    
    -- Request details
    request_method VARCHAR(10) NOT NULL,
    request_endpoint TEXT NOT NULL,
    request_body JSONB,
    request_headers JSONB,
    
    -- Expected vs Actual
    expected_status INTEGER,
    actual_status INTEGER NOT NULL,
    expected_response JSONB,
    actual_response JSONB NOT NULL,
    
    -- Conflict description from AI
    conflict_description TEXT NOT NULL,
    suggested_resolution TEXT,
    
    -- Corrected expected result (proposed by AI)
    corrected_expected_status INTEGER,
    corrected_expected_response JSONB,
    
    -- User decision
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, approved, rejected, cancelled
    user_decision TEXT,
    resolved_at TIMESTAMP,
    
    -- Generation state to resume from
    generation_state JSONB, -- Stores execution_history, extracted_variables, etc.
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_api_conflicts_test_case ON api_conflict_notifications(test_case_id);
CREATE INDEX idx_api_conflicts_user ON api_conflict_notifications(user_id);
CREATE INDEX idx_api_conflicts_status ON api_conflict_notifications(status);
CREATE INDEX idx_api_conflicts_client ON api_conflict_notifications(client_id);
CREATE INDEX idx_api_conflicts_created ON api_conflict_notifications(created_at DESC);

-- Create trigger for updated_at
CREATE OR REPLACE FUNCTION update_api_conflict_notifications_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_api_conflict_notifications_updated_at
    BEFORE UPDATE ON api_conflict_notifications
    FOR EACH ROW
    EXECUTE FUNCTION update_api_conflict_notifications_updated_at();

-- Add comment
COMMENT ON TABLE api_conflict_notifications IS 'Stores API documentation vs reality conflicts requiring user intervention during test generation';
