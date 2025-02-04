-- Create clients table
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add client_id to users table
ALTER TABLE users 
    ADD COLUMN client_id UUID,
    ADD CONSTRAINT fk_users_client 
    FOREIGN KEY (client_id) 
    REFERENCES clients(id);

-- Add client_id to test_cases table
ALTER TABLE test_cases 
    ADD COLUMN client_id UUID,
    ADD CONSTRAINT fk_test_cases_client 
    FOREIGN KEY (client_id) 
    REFERENCES clients(id);

-- Create index for better performance
CREATE INDEX idx_users_client_id ON users(client_id);
CREATE INDEX idx_test_cases_client_id ON test_cases(client_id);
