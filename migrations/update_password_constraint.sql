-- Migration to modify password_hash constraint for OAuth users
-- Alter password_hash column to allow NULL values for OAuth users
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- Add a check constraint to ensure either password_hash is not null OR auth_provider is not null
ALTER TABLE users ADD CONSTRAINT check_auth_method 
    CHECK (password_hash IS NOT NULL OR auth_provider IS NOT NULL);

-- Add comment to explain the constraint
COMMENT ON CONSTRAINT check_auth_method ON users IS 'Ensures users have either a password or an OAuth provider';
