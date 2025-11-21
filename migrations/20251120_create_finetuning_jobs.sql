-- Create finetuning_jobs table for model fine-tuning tracking
CREATE TABLE IF NOT EXISTS finetuning_jobs (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    job_name VARCHAR(255) NOT NULL,
    job_type VARCHAR(50) NOT NULL,  -- 'prompt_optimization', 'model_finetuning', 'pattern_learning'
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    base_model VARCHAR(100),  -- e.g., 'gemini-1.5-pro', 'gpt-4'
    training_data_count INTEGER DEFAULT 0,
    training_samples JSONB,  -- Store sample training data
    parameters JSONB,  -- Store job-specific parameters
    results JSONB,  -- Store job results
    error_message TEXT,
    started_at TIMESTAMP WITHOUT TIME ZONE,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Create finetuning_job_logs table for tracking job progress
CREATE TABLE IF NOT EXISTS finetuning_job_logs (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES finetuning_jobs(id) ON DELETE CASCADE,
    log_level VARCHAR(20),  -- 'info', 'warning', 'error'
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_finetuning_jobs_client ON finetuning_jobs(client_id);
CREATE INDEX idx_finetuning_jobs_project ON finetuning_jobs(project_id);
CREATE INDEX idx_finetuning_jobs_status ON finetuning_jobs(status);
CREATE INDEX idx_finetuning_jobs_created ON finetuning_jobs(created_at DESC);
CREATE INDEX idx_finetuning_jobs_type ON finetuning_jobs(job_type);
CREATE INDEX idx_finetuning_job_logs_job ON finetuning_job_logs(job_id);
CREATE INDEX idx_finetuning_job_logs_created ON finetuning_job_logs(created_at DESC);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_finetuning_jobs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER finetuning_jobs_update_timestamp
BEFORE UPDATE ON finetuning_jobs
FOR EACH ROW
EXECUTE FUNCTION update_finetuning_jobs_timestamp();
