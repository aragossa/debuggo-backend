-- Create environments table
CREATE TABLE IF NOT EXISTS environments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    base_url VARCHAR(255) NOT NULL,
    login VARCHAR(255),
    password VARCHAR(255),
    project_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    custom_variables JSONB DEFAULT '{}'
);

-- Create index on project_id
CREATE INDEX IF NOT EXISTS environments_project_id_idx ON environments(project_id);

-- Add foreign key constraint to projects table
ALTER TABLE environments 
ADD CONSTRAINT environments_project_id_fkey 
FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
