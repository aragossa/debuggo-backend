-- Recreate missing view for variables and ensure ALL columns exist

BEGIN;

-- 1. Ensure test_variables has all required columns
ALTER TABLE test_variables 
ADD COLUMN IF NOT EXISTS scope VARCHAR(50) DEFAULT 'global' CHECK (scope IN ('global', 'client', 'project', 'environment')),
ADD COLUMN IF NOT EXISTS client_id UUID,
ADD COLUMN IF NOT EXISTS project_id UUID,
ADD COLUMN IF NOT EXISTS environment_id INTEGER,
ADD COLUMN IF NOT EXISTS is_secret BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS description TEXT,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- 2. Drop view if it exists (to avoid column mismatch errors during replacement)
DROP VIEW IF EXISTS v_variables_with_scope;

-- 3. Create view for variable resolution with scope precedence
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
