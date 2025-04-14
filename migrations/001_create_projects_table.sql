-- Create projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    client_id UUID,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create index on client_id
CREATE INDEX IF NOT EXISTS idx_projects_client_id ON projects(client_id);

-- Add foreign key constraint to clients table
ALTER TABLE projects 
ADD CONSTRAINT projects_client_id_fkey 
FOREIGN KEY (client_id) REFERENCES clients(id);

-- Add project_id column to test_cases table
ALTER TABLE test_cases 
ADD COLUMN IF NOT EXISTS project_id UUID,
ADD COLUMN IF NOT EXISTS is_reusable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS component_type VARCHAR(50) DEFAULT NULL;

-- Create index on project_id
CREATE INDEX IF NOT EXISTS idx_test_cases_project_id ON test_cases(project_id);

-- Add foreign key constraint to projects table
ALTER TABLE test_cases 
ADD CONSTRAINT test_cases_project_id_fkey 
FOREIGN KEY (project_id) REFERENCES projects(id);

-- Update the valid_action constraint to include use_component
ALTER TABLE test_steps 
DROP CONSTRAINT IF EXISTS valid_action;

ALTER TABLE test_steps 
ADD CONSTRAINT valid_action 
CHECK (action = ANY (ARRAY['click', 'type', 'select', 'hover', 'wait', 'assert', 'scroll', 'clear', 'navigate', 'press_key', 'use_component']));
