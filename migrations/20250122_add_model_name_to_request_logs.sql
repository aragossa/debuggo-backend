-- Migration: Add model_name column to ai_request_logs for easier querying
-- Date: 2025-01-22
-- Purpose: Store model name in request logs to avoid JOIN queries

-- Add model_name column to ai_request_logs
ALTER TABLE public.ai_request_logs
ADD COLUMN IF NOT EXISTS model_name VARCHAR(255);

-- Populate existing records with model names from ai_models table
UPDATE public.ai_request_logs arl
SET model_name = am.name
FROM public.ai_models am
WHERE arl.ai_model_id = am.id AND arl.model_name IS NULL;

-- Create index on model_name for faster queries
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_model_name ON public.ai_request_logs(model_name);

-- Create index on request_type for faster filtering
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_request_type ON public.ai_request_logs(request_type);

-- Create index on created_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_created_at ON public.ai_request_logs(created_at);
