-- Library of API calls of a project: one row per method + path of an uploaded API schema.
-- Built by code when a schema is uploaded (Services/ApiOperationLibrary.py). API tests are
-- assembled from these calls, and UI tests insert them as api_request steps.
CREATE TABLE IF NOT EXISTS api_operations (
    id SERIAL PRIMARY KEY,
    schema_id INTEGER NOT NULL REFERENCES api_schemas(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    method VARCHAR(10) NOT NULL,
    path TEXT NOT NULL,
    name VARCHAR(255) NOT NULL,
    summary TEXT,
    resource VARCHAR(255),
    requires_auth BOOLEAN NOT NULL DEFAULT FALSE,
    expected_status INTEGER NOT NULL DEFAULT 200,
    -- {"path_params": [...], "query_params": [...], "body": {...}, "content_type": "..."}
    request JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"kind": "object" | "list" | "paginated" | "none", "fields": {"id": "string", ...}}
    response JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_api_operations_schema_method_path ON api_operations (schema_id, method, path);
CREATE INDEX IF NOT EXISTS idx_api_operations_project ON api_operations (project_id);
