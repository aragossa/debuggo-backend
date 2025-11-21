-- Phase 2: Learning System Database Schema
-- Adds vector database support for pattern storage and similarity search

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Patterns table: Stores reusable patterns (selectors, API flows, error resolutions, UI components)
CREATE TABLE IF NOT EXISTS patterns (
    id SERIAL PRIMARY KEY,
    pattern_type VARCHAR(50) NOT NULL,  -- 'selector', 'api_flow', 'error_resolution', 'ui_component'
    pattern_data JSONB NOT NULL,  -- Contains the actual pattern (selector, flow steps, etc.)
    embedding vector(1536),  -- Embedding vector from Gemini
    success_rate FLOAT DEFAULT 0.5,  -- Success rate (0-1)
    usage_count INTEGER DEFAULT 0,  -- Number of times used
    tags TEXT[],  -- Tags for categorization
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    client_id UUID REFERENCES clients(id)
);

-- Pattern usage tracking: Records when patterns are used and whether they succeeded
CREATE TABLE IF NOT EXISTS pattern_usage (
    id SERIAL PRIMARY KEY,
    pattern_id INTEGER NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_number INTEGER,
    success BOOLEAN NOT NULL,
    execution_time_ms INTEGER,  -- How long the pattern took to execute
    error_message TEXT,  -- Error if it failed
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Similar tests: Pre-computed similarity between test cases
CREATE TABLE IF NOT EXISTS similar_tests (
    id SERIAL PRIMARY KEY,
    test_case_id_1 INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    test_case_id_2 INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL,  -- 0-1 similarity score
    reason TEXT,  -- Why they're similar (e.g., "same UI flow", "same API endpoint")
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_case_id_1, test_case_id_2)
);

-- Few-shot examples: Pre-curated examples for few-shot learning
CREATE TABLE IF NOT EXISTS few_shot_examples (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,  -- Category of example (e.g., "login_flow", "form_validation")
    example_input TEXT NOT NULL,  -- Input/prompt for the example
    example_output JSONB NOT NULL,  -- Expected output (generated step)
    success_rate FLOAT DEFAULT 0.9,  -- How often this example leads to success
    usage_count INTEGER DEFAULT 0,  -- Number of times used
    embedding vector(1536),  -- Embedding of the example
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_client ON patterns(client_id);
CREATE INDEX IF NOT EXISTS idx_patterns_created_by ON patterns(created_by);
CREATE INDEX IF NOT EXISTS idx_patterns_success_rate ON patterns(success_rate DESC);
CREATE INDEX IF NOT EXISTS idx_patterns_embedding ON patterns USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_pattern_usage_pattern ON pattern_usage(pattern_id);
CREATE INDEX IF NOT EXISTS idx_pattern_usage_test_case ON pattern_usage(test_case_id);
CREATE INDEX IF NOT EXISTS idx_pattern_usage_success ON pattern_usage(success);
CREATE INDEX IF NOT EXISTS idx_pattern_usage_created ON pattern_usage(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_similar_tests_1 ON similar_tests(test_case_id_1);
CREATE INDEX IF NOT EXISTS idx_similar_tests_2 ON similar_tests(test_case_id_2);
CREATE INDEX IF NOT EXISTS idx_similar_tests_score ON similar_tests(similarity_score DESC);

CREATE INDEX IF NOT EXISTS idx_few_shot_examples_category ON few_shot_examples(category);
CREATE INDEX IF NOT EXISTS idx_few_shot_examples_success ON few_shot_examples(success_rate DESC);

-- Trigger to update patterns.updated_at
CREATE OR REPLACE FUNCTION update_patterns_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER patterns_updated_at_trigger
BEFORE UPDATE ON patterns
FOR EACH ROW
EXECUTE FUNCTION update_patterns_updated_at();

-- Trigger to update few_shot_examples.updated_at
CREATE OR REPLACE FUNCTION update_few_shot_examples_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER few_shot_examples_updated_at_trigger
BEFORE UPDATE ON few_shot_examples
FOR EACH ROW
EXECUTE FUNCTION update_few_shot_examples_updated_at();
