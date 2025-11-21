-- Phase 4: Optimization Schema
-- Supports prompt optimization, model ensemble, monitoring, and performance tracking

-- Prompt Variants for A/B Testing
CREATE TABLE IF NOT EXISTS prompt_variants (
    id SERIAL PRIMARY KEY,
    base_prompt_id INTEGER,
    variant_name VARCHAR(100) NOT NULL,
    variant_text TEXT NOT NULL,
    variant_type VARCHAR(50), -- 'instruction_clarity', 'example_format', 'constraint_emphasis', etc.
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    UNIQUE(variant_name)
);

-- A/B Test Results
CREATE TABLE IF NOT EXISTS ab_test_results (
    id SERIAL PRIMARY KEY,
    variant_a_id INTEGER NOT NULL REFERENCES prompt_variants(id),
    variant_b_id INTEGER NOT NULL REFERENCES prompt_variants(id),
    test_cases_count INTEGER,
    variant_a_success_rate FLOAT,
    variant_b_success_rate FLOAT,
    variant_a_avg_confidence FLOAT,
    variant_b_avg_confidence FLOAT,
    winner VARCHAR(10), -- 'A', 'B', or 'TIE'
    confidence_level FLOAT, -- Statistical significance
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Model Ensemble Results
CREATE TABLE IF NOT EXISTS model_ensemble_results (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id),
    step_number INTEGER NOT NULL,
    gemini_result JSONB,
    claude_result JSONB,
    deepseek_result JSONB,
    agreement_score FLOAT,
    selected_result JSONB,
    selection_strategy VARCHAR(50), -- 'voting', 'confidence', 'consensus', 'weighted'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent Metrics (Time-series data)
CREATE TABLE IF NOT EXISTS agent_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    metric_type VARCHAR(50), -- 'counter', 'gauge', 'histogram'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags JSONB, -- Additional context like test_case_id, step_number, etc.
    UNIQUE(metric_name, timestamp)
);

-- Performance Logs
CREATE TABLE IF NOT EXISTS performance_logs (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(100) NOT NULL,
    duration_ms FLOAT NOT NULL,
    status VARCHAR(20), -- 'success', 'failure', 'timeout'
    error_message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Embedding Cache
CREATE TABLE IF NOT EXISTS embedding_cache (
    id SERIAL PRIMARY KEY,
    content_hash VARCHAR(64) UNIQUE NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536), -- Gemini embedding dimension
    model VARCHAR(50), -- 'gemini', 'claude', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 1
);

-- Fine-tuning Data Collection
CREATE TABLE IF NOT EXISTS finetuning_data (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id),
    step_number INTEGER,
    prompt TEXT NOT NULL,
    response JSONB NOT NULL,
    success BOOLEAN NOT NULL,
    confidence FLOAT,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending' -- 'pending', 'approved', 'rejected', 'used'
);

-- Fine-tuning Jobs
CREATE TABLE IF NOT EXISTS finetuning_jobs (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    model_name VARCHAR(50), -- 'gemini', 'claude', etc.
    training_data_count INTEGER,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    job_id VARCHAR(255), -- Provider's job ID
    result_model_id VARCHAR(255),
    accuracy FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Continuous Improvement Logs
CREATE TABLE IF NOT EXISTS improvement_logs (
    id SERIAL PRIMARY KEY,
    improvement_type VARCHAR(50), -- 'prompt_update', 'pattern_retrain', 'threshold_adjust', etc.
    description TEXT,
    metrics_before JSONB,
    metrics_after JSONB,
    impact FLOAT, -- Percentage improvement
    applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_prompt_variants_type ON prompt_variants(variant_type);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_winner ON ab_test_results(winner);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_created ON ab_test_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_ensemble_test_case ON model_ensemble_results(test_case_id);
CREATE INDEX IF NOT EXISTS idx_model_ensemble_strategy ON model_ensemble_results(selection_strategy);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_name ON agent_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_timestamp ON agent_metrics(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_performance_logs_operation ON performance_logs(operation);
CREATE INDEX IF NOT EXISTS idx_performance_logs_timestamp ON performance_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_embedding_cache_hash ON embedding_cache(content_hash);
CREATE INDEX IF NOT EXISTS idx_embedding_cache_accessed ON embedding_cache(last_accessed DESC);
CREATE INDEX IF NOT EXISTS idx_finetuning_data_status ON finetuning_data(status);
CREATE INDEX IF NOT EXISTS idx_finetuning_data_test_case ON finetuning_data(test_case_id);
CREATE INDEX IF NOT EXISTS idx_finetuning_jobs_status ON finetuning_jobs(status);
CREATE INDEX IF NOT EXISTS idx_finetuning_jobs_created ON finetuning_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_improvement_logs_created ON improvement_logs(created_at DESC);

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;
