-- Create ab_test_results table for A/B testing analysis
CREATE TABLE IF NOT EXISTS ab_test_results (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    test_case_id_a INTEGER REFERENCES test_cases(id) ON DELETE CASCADE,
    test_case_id_b INTEGER REFERENCES test_cases(id) ON DELETE CASCADE,
    variant_a_id VARCHAR(255) NOT NULL,
    variant_b_id VARCHAR(255) NOT NULL,
    variant_a_success_rate FLOAT DEFAULT 0.0,
    variant_b_success_rate FLOAT DEFAULT 0.0,
    variant_a_avg_time FLOAT DEFAULT 0.0,
    variant_b_avg_time FLOAT DEFAULT 0.0,
    winner VARCHAR(1),  -- 'A', 'B', or NULL if no winner
    confidence_level FLOAT DEFAULT 0.0,
    sample_size_a INTEGER DEFAULT 0,
    sample_size_b INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused', 'cancelled')),
    notes TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITHOUT TIME ZONE
);

-- Create indexes for performance
CREATE INDEX idx_ab_test_results_client ON ab_test_results(client_id);
CREATE INDEX idx_ab_test_results_project ON ab_test_results(project_id);
CREATE INDEX idx_ab_test_results_status ON ab_test_results(status);
CREATE INDEX idx_ab_test_results_created ON ab_test_results(created_at DESC);
CREATE INDEX idx_ab_test_results_winner ON ab_test_results(winner);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_ab_test_results_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ab_test_results_update_timestamp
BEFORE UPDATE ON ab_test_results
FOR EACH ROW
EXECUTE FUNCTION update_ab_test_results_timestamp();
