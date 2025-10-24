-- Migration: Create api_schemas table for storing API schemas per project
-- Date: 2025-10-01
-- Description: Store OpenAPI/Swagger schemas uploaded by users for API test generation

CREATE TABLE IF NOT EXISTS api_schemas (
    id SERIAL PRIMARY KEY,
    project_id UUID NOT NULL,
    client_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    schema_type VARCHAR(50) DEFAULT 'openapi',  -- openapi, swagger, postman, custom
    content TEXT NOT NULL,  -- JSON/YAML schema content
    created_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_api_schemas_project FOREIGN KEY (project_id) 
        REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_api_schemas_client FOREIGN KEY (client_id) 
        REFERENCES clients(id) ON DELETE CASCADE,
    CONSTRAINT fk_api_schemas_user FOREIGN KEY (created_by) 
        REFERENCES users(id) ON DELETE SET NULL
);

-- Create indexes for performance
CREATE INDEX idx_api_schemas_project ON api_schemas(project_id);
CREATE INDEX idx_api_schemas_client ON api_schemas(client_id);
CREATE INDEX idx_api_schemas_created_at ON api_schemas(created_at DESC);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_api_schemas_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_api_schemas_updated_at
    BEFORE UPDATE ON api_schemas
    FOR EACH ROW
    EXECUTE FUNCTION update_api_schemas_updated_at();

-- Add comment
COMMENT ON TABLE api_schemas IS 'Stores API schemas (OpenAPI, Swagger, Postman) for projects to generate API test cases';
