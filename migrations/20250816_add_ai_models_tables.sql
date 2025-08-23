-- Migration: Add AI Models Tables
-- Date: 2025-08-16

-- Create AI Models table
CREATE TABLE IF NOT EXISTS public.ai_models (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    model_id character varying(255) NOT NULL,
    description text,
    is_active boolean DEFAULT true,
    is_default boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.ai_models OWNER TO postgres;

-- Create sequence for ai_models id
CREATE SEQUENCE IF NOT EXISTS public.ai_models_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.ai_models_id_seq OWNER TO postgres;

-- Set sequence ownership
ALTER SEQUENCE public.ai_models_id_seq OWNED BY public.ai_models.id;

-- Create User AI Models table
CREATE TABLE IF NOT EXISTS public.user_ai_models (
    user_id integer NOT NULL,
    ai_model_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.user_ai_models OWNER TO postgres;

-- Set default value for ai_models.id from sequence
ALTER TABLE ONLY public.ai_models ALTER COLUMN id SET DEFAULT nextval('public.ai_models_id_seq'::regclass);

-- Add primary key constraint to ai_models (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ai_models_pkey') THEN
        ALTER TABLE ONLY public.ai_models ADD CONSTRAINT ai_models_pkey PRIMARY KEY (id);
    END IF;
END $$;

-- Add primary key constraint to user_ai_models (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_ai_models_pkey') THEN
        ALTER TABLE ONLY public.user_ai_models ADD CONSTRAINT user_ai_models_pkey PRIMARY KEY (user_id, ai_model_id);
    END IF;
END $$;

-- Add foreign key constraint to user_ai_models (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_ai_models_ai_model_id_fkey') THEN
        ALTER TABLE ONLY public.user_ai_models ADD CONSTRAINT user_ai_models_ai_model_id_fkey FOREIGN KEY (ai_model_id) REFERENCES public.ai_models(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_ai_models_user_id_fkey') THEN
        ALTER TABLE ONLY public.user_ai_models ADD CONSTRAINT user_ai_models_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
    END IF;
END $$;
