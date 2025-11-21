-- Create embedding_cache table for caching embeddings
CREATE TABLE IF NOT EXISTS embedding_cache (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL,
    content_type VARCHAR(50),  -- 'test_step', 'error_message', 'prompt'
    embedding FLOAT8[],  -- Vector embedding
    metadata JSONB,
    hit_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create performance_logs table for tracking query performance
CREATE TABLE IF NOT EXISTS performance_logs (
    id SERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    query_text TEXT,
    execution_time_ms FLOAT,
    rows_affected INTEGER,
    query_type VARCHAR(20),  -- 'SELECT', 'INSERT', 'UPDATE', 'DELETE'
    table_name VARCHAR(100),
    status VARCHAR(20),  -- 'success', 'slow', 'error'
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_embedding_cache_client ON embedding_cache(client_id);
CREATE INDEX idx_embedding_cache_hash ON embedding_cache(content_hash);
CREATE INDEX idx_embedding_cache_type ON embedding_cache(content_type);
CREATE INDEX idx_embedding_cache_accessed ON embedding_cache(last_accessed DESC);
CREATE INDEX idx_performance_logs_client ON performance_logs(client_id);
CREATE INDEX idx_performance_logs_table ON performance_logs(table_name);
CREATE INDEX idx_performance_logs_status ON performance_logs(status);
CREATE INDEX idx_performance_logs_created ON performance_logs(created_at DESC);
CREATE INDEX idx_performance_logs_time ON performance_logs(execution_time_ms DESC);

-- Create trigger to update embedding_cache timestamp
CREATE OR REPLACE FUNCTION update_embedding_cache_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER embedding_cache_update_timestamp
BEFORE UPDATE ON embedding_cache
FOR EACH ROW
EXECUTE FUNCTION update_embedding_cache_timestamp();
