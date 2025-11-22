-- Migration: Add AI Token Tracking and Request Logging
-- Date: 2025-01-22
-- Purpose: Track AI API requests, token usage, and pricing

-- 1. Update ai_models table to include pricing columns
ALTER TABLE public.ai_models
ADD COLUMN IF NOT EXISTS input_price_per_1m DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS output_price_per_1m DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS tier_threshold INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS input_price_per_1m_above DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS output_price_per_1m_above DECIMAL(10, 6) DEFAULT 0;

-- 2. Create ai_request_logs table
CREATE TABLE IF NOT EXISTS public.ai_request_logs (
    id BIGSERIAL PRIMARY KEY,
    ai_model_id INTEGER NOT NULL REFERENCES public.ai_models(id) ON DELETE CASCADE,
    client_id UUID REFERENCES public.clients(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    request_type VARCHAR(50) NOT NULL, -- 'ui_step', 'ui_error', 'api_test', 'api_schema', 'image_analysis', 'text_analysis', 'other'
    request_context VARCHAR(255), -- e.g., test_case_id, schema_id, etc.
    
    -- Token tracking
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    
    -- Pricing (snapshot at time of request - immutable)
    input_price_per_1m DECIMAL(10, 6) NOT NULL, -- Price per 1M tokens at time of request
    output_price_per_1m DECIMAL(10, 6) NOT NULL, -- Price per 1M tokens at time of request
    tier_threshold INTEGER DEFAULT 0, -- Tier threshold at time of request
    input_price_per_1m_above DECIMAL(10, 6) DEFAULT 0, -- Price above tier at time of request
    output_price_per_1m_above DECIMAL(10, 6) DEFAULT 0, -- Price above tier at time of request
    
    -- Calculated costs
    input_cost DECIMAL(12, 8) NOT NULL DEFAULT 0, -- Calculated cost for input tokens
    output_cost DECIMAL(12, 8) NOT NULL DEFAULT 0, -- Calculated cost for output tokens
    total_cost DECIMAL(12, 8) NOT NULL DEFAULT 0, -- Total cost for this request
    
    -- Request details
    prompt_length INTEGER DEFAULT 0, -- Length of the prompt in characters
    response_length INTEGER DEFAULT 0, -- Length of the response in characters
    response_time_ms INTEGER DEFAULT 0, -- Response time in milliseconds
    
    -- Status and error tracking
    status VARCHAR(20) NOT NULL DEFAULT 'success', -- 'success', 'error', 'rate_limited', 'blocked'
    error_message TEXT, -- Error message if status is 'error'
    
    -- Metadata
    metadata JSONB, -- Additional metadata (e.g., model version, temperature, etc.)
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_ai_model_id ON public.ai_request_logs(ai_model_id);
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_client_id ON public.ai_request_logs(client_id);
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_user_id ON public.ai_request_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_request_type ON public.ai_request_logs(request_type);
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_created_at ON public.ai_request_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_status ON public.ai_request_logs(status);
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_client_created ON public.ai_request_logs(client_id, created_at);

-- 4. Create view for AI usage statistics
CREATE OR REPLACE VIEW public.ai_usage_stats AS
SELECT 
    am.id as model_id,
    am.name as model_name,
    COUNT(*) as total_requests,
    SUM(arl.input_tokens) as total_input_tokens,
    SUM(arl.output_tokens) as total_output_tokens,
    SUM(arl.total_tokens) as total_tokens,
    SUM(arl.total_cost) as total_cost,
    AVG(arl.response_time_ms) as avg_response_time_ms,
    MIN(arl.created_at) as first_request_at,
    MAX(arl.created_at) as last_request_at
FROM public.ai_request_logs arl
JOIN public.ai_models am ON arl.ai_model_id = am.id
GROUP BY am.id, am.name;

-- 5. Create view for client AI usage
CREATE OR REPLACE VIEW public.client_ai_usage AS
SELECT 
    c.id as client_id,
    c.name as client_name,
    am.id as model_id,
    am.name as model_name,
    COUNT(*) as total_requests,
    SUM(arl.input_tokens) as total_input_tokens,
    SUM(arl.output_tokens) as total_output_tokens,
    SUM(arl.total_tokens) as total_tokens,
    SUM(arl.total_cost) as total_cost,
    DATE(arl.created_at) as request_date
FROM public.ai_request_logs arl
JOIN public.ai_models am ON arl.ai_model_id = am.id
LEFT JOIN public.clients c ON arl.client_id = c.id
GROUP BY c.id, c.name, am.id, am.name, DATE(arl.created_at);

-- 6. Create view for request type statistics
CREATE OR REPLACE VIEW public.ai_request_type_stats AS
SELECT 
    arl.request_type,
    COUNT(*) as total_requests,
    SUM(arl.input_tokens) as total_input_tokens,
    SUM(arl.output_tokens) as total_output_tokens,
    SUM(arl.total_tokens) as total_tokens,
    SUM(arl.total_cost) as total_cost,
    AVG(arl.response_time_ms) as avg_response_time_ms,
    AVG(arl.total_cost) as avg_cost_per_request
FROM public.ai_request_logs arl
GROUP BY arl.request_type;

-- 7. Set table owner
ALTER TABLE public.ai_request_logs OWNER TO postgres;

-- 8. Create trigger for updated_at timestamp
CREATE OR REPLACE FUNCTION update_ai_request_logs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ai_request_logs_update_timestamp ON public.ai_request_logs;
CREATE TRIGGER ai_request_logs_update_timestamp
BEFORE UPDATE ON public.ai_request_logs
FOR EACH ROW
EXECUTE FUNCTION update_ai_request_logs_timestamp();
