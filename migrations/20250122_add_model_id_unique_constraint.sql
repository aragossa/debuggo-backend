-- Migration: Add UNIQUE constraint to model_id for UPSERT support
-- Date: 2025-01-22
-- Purpose: Enable UPSERT operations on ai_models table using model_id

-- Add UNIQUE constraint to model_id column
ALTER TABLE public.ai_models
ADD CONSTRAINT ai_models_model_id_unique UNIQUE (model_id);
