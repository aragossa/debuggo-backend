-- Add role to users table
ALTER TABLE users 
    ADD COLUMN role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user'));

-- Make client_id optional in users table
ALTER TABLE users 
    ALTER COLUMN client_id DROP NOT NULL;
