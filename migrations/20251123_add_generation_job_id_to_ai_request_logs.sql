-- Migration: Add generation_job_id to ai_request_logs
-- Date: 2025-11-23
-- Purpose: Track all AI requests for each test case generation job

-- Add generation_job_id column to ai_request_logs table
ALTER TABLE public.ai_request_logs
ADD COLUMN IF NOT EXISTS generation_job_id UUID;

-- Create index for efficient querying by generation_job_id
CREATE INDEX IF NOT EXISTS idx_ai_request_logs_generation_job_id 
ON public.ai_request_logs(generation_job_id);

-- Add comment to document the column
COMMENT ON COLUMN public.ai_request_logs.generation_job_id IS 
'UUID to track all AI requests associated with a specific test case generation job. Allows grouping and analyzing all AI requests for a single test generation session.';
