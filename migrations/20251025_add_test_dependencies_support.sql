-- Migration: Add support for test case dependencies and preconditions
-- Date: 2025-10-25
-- Description: Enable test cases to have API preconditions with reusability and teardown support

-- Create test_dependencies table to track prerequisite relationships
CREATE TABLE IF NOT EXISTS test_dependencies (
    id SERIAL PRIMARY KEY,
    dependent_test_case_id INTEGER NOT NULL,
    prerequisite_test_case_id INTEGER NOT NULL,
    dependency_type VARCHAR(20) NOT NULL DEFAULT 'precondition', -- 'precondition', 'teardown'
    execution_order INTEGER NOT NULL DEFAULT 1, -- Order of execution for multiple dependencies
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraints
    CONSTRAINT fk_dependent_test_case 
        FOREIGN KEY (dependent_test_case_id) 
        REFERENCES test_cases(id) ON DELETE CASCADE,
    
    CONSTRAINT fk_prerequisite_test_case 
        FOREIGN KEY (prerequisite_test_case_id) 
        REFERENCES test_cases(id) ON DELETE CASCADE,
    
    -- Prevent self-dependencies
    CONSTRAINT no_self_dependency 
        CHECK (dependent_test_case_id != prerequisite_test_case_id),
    
    -- Ensure valid dependency types
    CONSTRAINT valid_dependency_type 
        CHECK (dependency_type IN ('precondition', 'teardown')),
    
    -- Unique constraint to prevent duplicate dependencies
    CONSTRAINT unique_dependency 
        UNIQUE (dependent_test_case_id, prerequisite_test_case_id, dependency_type)
);

-- Add columns to test_cases table for precondition support
ALTER TABLE test_cases 
ADD COLUMN IF NOT EXISTS requires_preconditions BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_precondition_template BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS precondition_description TEXT,
ADD COLUMN IF NOT EXISTS generated_from_schema_id INTEGER;

-- Create precondition_templates table for reusability
CREATE TABLE IF NOT EXISTS precondition_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    schema_id INTEGER,
    client_id UUID NOT NULL,
    project_id UUID,
    template_data JSONB, -- Store template configuration for reuse
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraints
    CONSTRAINT fk_precondition_client 
        FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    
    CONSTRAINT fk_precondition_schema 
        FOREIGN KEY (schema_id) 
        REFERENCES api_schemas(id) ON DELETE SET NULL
);

-- Create indexes for better performance
CREATE INDEX idx_test_dependencies_dependent ON test_dependencies(dependent_test_case_id);
CREATE INDEX idx_test_dependencies_prerequisite ON test_dependencies(prerequisite_test_case_id);
CREATE INDEX idx_test_dependencies_type ON test_dependencies(dependency_type);
CREATE INDEX idx_test_cases_requires_preconditions ON test_cases(requires_preconditions);
CREATE INDEX idx_test_cases_is_precondition_template ON test_cases(is_precondition_template);
CREATE INDEX idx_precondition_templates_client ON precondition_templates(client_id);
CREATE INDEX idx_precondition_templates_project ON precondition_templates(project_id);
CREATE INDEX idx_precondition_templates_schema ON precondition_templates(schema_id);

-- Add comments for documentation
COMMENT ON TABLE test_dependencies IS 'Tracks prerequisite relationships between test cases for preconditions and teardown';
COMMENT ON COLUMN test_dependencies.dependency_type IS 'Type: precondition (runs before) or teardown (runs after)';
COMMENT ON COLUMN test_dependencies.execution_order IS 'Order of execution when multiple dependencies exist';

COMMENT ON COLUMN test_cases.requires_preconditions IS 'Whether this test case needs API preconditions to be generated';
COMMENT ON COLUMN test_cases.is_precondition_template IS 'Whether this test case serves as a reusable precondition template';
COMMENT ON COLUMN test_cases.precondition_description IS 'Description of what preconditions this test case provides';
COMMENT ON COLUMN test_cases.generated_from_schema_id IS 'API schema ID used to generate preconditions for this test case';

COMMENT ON TABLE precondition_templates IS 'Reusable precondition templates for multiple test cases';
COMMENT ON COLUMN precondition_templates.template_data IS 'JSONB configuration data for template reuse';

-- Add foreign key constraint for generated_from_schema_id (if api_schemas table exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'api_schemas') THEN
        ALTER TABLE test_cases 
        ADD CONSTRAINT fk_test_cases_schema 
        FOREIGN KEY (generated_from_schema_id) 
        REFERENCES api_schemas(id) ON DELETE SET NULL;
    END IF;
END $$;
