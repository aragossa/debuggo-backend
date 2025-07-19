-- Migration to add OAuth fields to users table
-- Add auth_provider column
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50);

-- Add auth_provider_id column
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider_id VARCHAR(255);

-- Add profile_picture column
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(1024);

-- Update existing is_google_auth field to be consistent with auth_provider
UPDATE users SET auth_provider = 'google' WHERE is_google_auth = true;

-- Add comment to explain the fields
COMMENT ON COLUMN users.auth_provider IS 'OAuth provider (e.g., google, facebook)';
COMMENT ON COLUMN users.auth_provider_id IS 'User ID from the OAuth provider';
COMMENT ON COLUMN users.profile_picture IS 'URL to user profile picture from OAuth provider';
