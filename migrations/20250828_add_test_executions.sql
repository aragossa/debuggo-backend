-- Migration: Add test_executions table and update test_runs
-- Date: 2025-08-28
-- Description: Add test executions feature with status tracking

-- Create test_executions table
CREATE TABLE IF NOT EXISTS test_executions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'New' CHECK (status IN ('New', 'In Progress', 'Done')),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Add execution_id to test_runs table
ALTER TABLE test_runs 
ADD COLUMN IF NOT EXISTS execution_id INTEGER REFERENCES test_executions(id) ON DELETE SET NULL;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_test_executions_project_id ON test_executions(project_id);
CREATE INDEX IF NOT EXISTS idx_test_executions_client_id ON test_executions(client_id);
CREATE INDEX IF NOT EXISTS idx_test_executions_status ON test_executions(status);
CREATE INDEX IF NOT EXISTS idx_test_executions_created_at ON test_executions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_execution_id ON test_runs(execution_id);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_test_executions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_test_executions_updated_at_trigger
    BEFORE UPDATE ON test_executions
    FOR EACH ROW
    EXECUTE FUNCTION update_test_executions_updated_at();
