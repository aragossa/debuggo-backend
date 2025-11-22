-- Migration: Add Extended AI Pricing (Context Caching and Storage)
-- Date: 2025-01-22
-- Purpose: Add context caching and storage pricing support to ai_models and ai_request_logs

-- 1. Add context caching and storage pricing columns to ai_models table
ALTER TABLE public.ai_models
ADD COLUMN IF NOT EXISTS cache_input_price_per_1m DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_input_price_per_1m_above DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_storage_price_per_1m_hour DECIMAL(10, 6) DEFAULT 0;

-- 2. Add context caching and storage tracking to ai_request_logs table
ALTER TABLE public.ai_request_logs
ADD COLUMN IF NOT EXISTS cache_input_tokens INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_input_cost DECIMAL(12, 8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_storage_tokens INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_storage_cost DECIMAL(12, 8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_creation_tokens INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_creation_cost DECIMAL(12, 8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_read_cost DECIMAL(12, 8) DEFAULT 0;

-- 3. Add pricing snapshot columns for caching to ai_request_logs
ALTER TABLE public.ai_request_logs
ADD COLUMN IF NOT EXISTS cache_input_price_per_1m DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_input_price_per_1m_above DECIMAL(10, 6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS cache_storage_price_per_1m_hour DECIMAL(10, 6) DEFAULT 0;

-- 4. Update total_cost calculation to include cache costs
-- Note: This is handled in application logic, not in database trigger

-- 5. Drop existing views (they will be recreated with new columns)
DROP VIEW IF EXISTS public.ai_request_type_stats CASCADE;
DROP VIEW IF EXISTS public.client_ai_usage CASCADE;
DROP VIEW IF EXISTS public.ai_usage_stats CASCADE;

-- 6. Create or update view for AI usage statistics to include cache costs
CREATE VIEW public.ai_usage_stats AS
SELECT 
    am.id as model_id,
    am.name as model_name,
    COUNT(*) as total_requests,
    SUM(arl.input_tokens) as total_input_tokens,
    SUM(arl.output_tokens) as total_output_tokens,
    SUM(arl.total_tokens) as total_tokens,
    SUM(arl.cache_input_tokens) as total_cache_input_tokens,
    SUM(arl.cache_creation_tokens) as total_cache_creation_tokens,
    SUM(arl.cache_read_tokens) as total_cache_read_tokens,
    SUM(arl.input_cost) as total_input_cost,
    SUM(arl.output_cost) as total_output_cost,
    SUM(arl.cache_input_cost) as total_cache_input_cost,
    SUM(arl.cache_creation_cost) as total_cache_creation_cost,
    SUM(arl.cache_read_cost) as total_cache_read_cost,
    SUM(arl.cache_storage_cost) as total_cache_storage_cost,
    SUM(arl.total_cost) as total_cost,
    AVG(arl.response_time_ms) as avg_response_time_ms,
    MIN(arl.created_at) as first_request_at,
    MAX(arl.created_at) as last_request_at
FROM public.ai_request_logs arl
JOIN public.ai_models am ON arl.ai_model_id = am.id
GROUP BY am.id, am.name;

-- 7. Create client AI usage view to include cache costs
CREATE VIEW public.client_ai_usage AS
SELECT 
    c.id as client_id,
    c.name as client_name,
    am.id as model_id,
    am.name as model_name,
    COUNT(*) as total_requests,
    SUM(arl.input_tokens) as total_input_tokens,
    SUM(arl.output_tokens) as total_output_tokens,
    SUM(arl.total_tokens) as total_tokens,
    SUM(arl.cache_input_tokens) as total_cache_input_tokens,
    SUM(arl.cache_creation_tokens) as total_cache_creation_tokens,
    SUM(arl.cache_read_tokens) as total_cache_read_tokens,
    SUM(arl.input_cost) as total_input_cost,
    SUM(arl.output_cost) as total_output_cost,
    SUM(arl.cache_input_cost) as total_cache_input_cost,
    SUM(arl.cache_creation_cost) as total_cache_creation_cost,
    SUM(arl.cache_read_cost) as total_cache_read_cost,
    SUM(arl.cache_storage_cost) as total_cache_storage_cost,
    SUM(arl.total_cost) as total_cost,
    DATE(arl.created_at) as request_date
FROM public.ai_request_logs arl
JOIN public.ai_models am ON arl.ai_model_id = am.id
LEFT JOIN public.clients c ON arl.client_id = c.id
GROUP BY c.id, c.name, am.id, am.name, DATE(arl.created_at);

-- 8. Create request type statistics view to include cache costs
CREATE VIEW public.ai_request_type_stats AS
SELECT 
    arl.request_type,
    COUNT(*) as total_requests,
    SUM(arl.input_tokens) as total_input_tokens,
    SUM(arl.output_tokens) as total_output_tokens,
    SUM(arl.total_tokens) as total_tokens,
    SUM(arl.cache_input_tokens) as total_cache_input_tokens,
    SUM(arl.cache_creation_tokens) as total_cache_creation_tokens,
    SUM(arl.cache_read_tokens) as total_cache_read_tokens,
    SUM(arl.input_cost) as total_input_cost,
    SUM(arl.output_cost) as total_output_cost,
    SUM(arl.cache_input_cost) as total_cache_input_cost,
    SUM(arl.cache_creation_cost) as total_cache_creation_cost,
    SUM(arl.cache_read_cost) as total_cache_read_cost,
    SUM(arl.cache_storage_cost) as total_cache_storage_cost,
    SUM(arl.total_cost) as total_cost,
    AVG(arl.response_time_ms) as avg_response_time_ms,
    AVG(arl.total_cost) as avg_cost_per_request
FROM public.ai_request_logs arl
GROUP BY arl.request_type;
