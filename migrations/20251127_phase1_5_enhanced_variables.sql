-- Phase 1.5: Enhanced Variables with Scoping
-- This migration adds support for variable scoping (global, client, project, environment)
-- and variable substitution in test steps

-- 1. Add scope column to test_variables if not exists
ALTER TABLE test_variables 
ADD COLUMN IF NOT EXISTS scope VARCHAR(50) DEFAULT 'global' CHECK (scope IN ('global', 'client', 'project', 'environment')),
ADD COLUMN IF NOT EXISTS client_id UUID,
ADD COLUMN IF NOT EXISTS project_id UUID,
ADD COLUMN IF NOT EXISTS environment_id INTEGER,
ADD COLUMN IF NOT EXISTS is_secret BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS description TEXT;

-- 2. Add indexes for efficient variable lookup
CREATE INDEX IF NOT EXISTS idx_test_variables_scope ON test_variables(scope);
CREATE INDEX IF NOT EXISTS idx_test_variables_client_id ON test_variables(client_id);
CREATE INDEX IF NOT EXISTS idx_test_variables_project_id ON test_variables(project_id);
CREATE INDEX IF NOT EXISTS idx_test_variables_environment_id ON test_variables(environment_id);
CREATE INDEX IF NOT EXISTS idx_test_variables_name_scope ON test_variables(name, scope);

-- 3. Create variable_substitution_log table for tracking variable usage
CREATE TABLE IF NOT EXISTS variable_substitution_log (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER REFERENCES test_runs(id) ON DELETE CASCADE,
    test_step_id INTEGER REFERENCES test_steps(id) ON DELETE CASCADE,
    variable_name VARCHAR(255) NOT NULL,
    variable_scope VARCHAR(50) NOT NULL,
    original_value TEXT,
    substituted_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_variable_substitution_log_test_run ON variable_substitution_log(test_run_id);
CREATE INDEX IF NOT EXISTS idx_variable_substitution_log_test_step ON variable_substitution_log(test_step_id);

-- 4. Create variable_extraction_log table for tracking extracted variables from responses
CREATE TABLE IF NOT EXISTS variable_extraction_log (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER REFERENCES test_runs(id) ON DELETE CASCADE,
    test_step_id INTEGER REFERENCES test_steps(id) ON DELETE CASCADE,
    variable_name VARCHAR(255) NOT NULL,
    extracted_value TEXT,
    extraction_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_variable_extraction_log_test_run ON variable_extraction_log(test_run_id);
CREATE INDEX IF NOT EXISTS idx_variable_extraction_log_test_step ON variable_extraction_log(test_step_id);

-- 5. Add variable_substitution_config column to test_steps for storing extraction rules
ALTER TABLE test_steps 
ADD COLUMN IF NOT EXISTS variable_substitution_config JSONB DEFAULT '{}';

-- 6. Create variable_scope_hierarchy table to define scope precedence
CREATE TABLE IF NOT EXISTS variable_scope_hierarchy (
    id SERIAL PRIMARY KEY,
    scope_order INTEGER NOT NULL,
    scope_name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert scope hierarchy (higher order = higher precedence)
INSERT INTO variable_scope_hierarchy (scope_order, scope_name, description) VALUES
    (1, 'global', 'Global variables available to all tests'),
    (2, 'client', 'Client-specific variables'),
    (3, 'project', 'Project-specific variables'),
    (4, 'environment', 'Environment-specific variables (highest precedence)')
ON CONFLICT (scope_name) DO NOTHING;

-- 7. Create function to get variable by name with scope resolution
CREATE OR REPLACE FUNCTION get_variable_by_scope(
    p_name VARCHAR,
    p_client_id UUID DEFAULT NULL,
    p_project_id UUID DEFAULT NULL,
    p_environment_id INTEGER DEFAULT NULL
) RETURNS TABLE (
    id INTEGER,
    name VARCHAR,
    value TEXT,
    scope VARCHAR,
    is_secret BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT tv.id, tv.name, tv.value, tv.scope, tv.is_secret
    FROM test_variables tv
    WHERE tv.name = p_name
    AND (
        -- Environment scope (highest precedence)
        (tv.scope = 'environment' AND tv.environment_id = p_environment_id AND p_environment_id IS NOT NULL)
        OR
        -- Project scope
        (tv.scope = 'project' AND tv.project_id = p_project_id AND p_project_id IS NOT NULL AND p_environment_id IS NULL)
        OR
        -- Client scope
        (tv.scope = 'client' AND tv.client_id = p_client_id AND p_client_id IS NOT NULL AND p_project_id IS NULL AND p_environment_id IS NULL)
        OR
        -- Global scope (lowest precedence)
        (tv.scope = 'global' AND p_environment_id IS NULL AND p_project_id IS NULL AND p_client_id IS NULL)
    )
    ORDER BY 
        CASE tv.scope
            WHEN 'environment' THEN 4
            WHEN 'project' THEN 3
            WHEN 'client' THEN 2
            WHEN 'global' THEN 1
        END DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- 8. Create function to log variable substitution
CREATE OR REPLACE FUNCTION log_variable_substitution(
    p_test_run_id INTEGER,
    p_test_step_id INTEGER,
    p_variable_name VARCHAR,
    p_variable_scope VARCHAR,
    p_original_value TEXT,
    p_substituted_value TEXT
) RETURNS VOID AS $$
BEGIN
    INSERT INTO variable_substitution_log (
        test_run_id, test_step_id, variable_name, variable_scope, 
        original_value, substituted_value
    ) VALUES (
        p_test_run_id, p_test_step_id, p_variable_name, p_variable_scope,
        p_original_value, p_substituted_value
    );
END;
$$ LANGUAGE plpgsql;

-- 9. Create function to log variable extraction
CREATE OR REPLACE FUNCTION log_variable_extraction(
    p_test_run_id INTEGER,
    p_test_step_id INTEGER,
    p_variable_name VARCHAR,
    p_extracted_value TEXT,
    p_extraction_path VARCHAR
) RETURNS VOID AS $$
BEGIN
    INSERT INTO variable_extraction_log (
        test_run_id, test_step_id, variable_name, extracted_value, extraction_path
    ) VALUES (
        p_test_run_id, p_test_step_id, p_variable_name, p_extracted_value, p_extraction_path
    );
END;
$$ LANGUAGE plpgsql;

-- 10. Add trigger to update test_variables timestamp
CREATE OR REPLACE FUNCTION update_test_variables_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_test_variables_timestamp ON test_variables;
CREATE TRIGGER trigger_update_test_variables_timestamp
BEFORE UPDATE ON test_variables
FOR EACH ROW
EXECUTE FUNCTION update_test_variables_timestamp();

-- 11. Create view for variable resolution with scope precedence
CREATE OR REPLACE VIEW v_variables_with_scope AS
SELECT 
    tv.id,
    tv.name,
    tv.value,
    tv.scope,
    tv.client_id,
    tv.project_id,
    tv.environment_id,
    tv.is_secret,
    tv.description,
    tv.created_at,
    tv.updated_at,
    CASE tv.scope
        WHEN 'environment' THEN 4
        WHEN 'project' THEN 3
        WHEN 'client' THEN 2
        WHEN 'global' THEN 1
    END as scope_precedence
FROM test_variables tv
WHERE tv.is_active = TRUE
ORDER BY tv.name, scope_precedence DESC;

COMMIT;
