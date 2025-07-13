-- Migration: create_contact_requests_table
-- Created at: 2025-07-13 23:23:25 UTC
-- Description: Creates a table to store contact requests submitted through the "Get In Touch" form

-- Create contact_requests table
CREATE TABLE contact_requests (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Add index on status for faster filtering
CREATE INDEX idx_contact_requests_status ON contact_requests(status);

-- Add index on created_at for chronological sorting
CREATE INDEX idx_contact_requests_created_at ON contact_requests(created_at);

-- Create trigger to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_contact_request_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_contact_request_timestamp
BEFORE UPDATE ON contact_requests
FOR EACH ROW
EXECUTE FUNCTION update_contact_request_timestamp();

-- To roll back this migration, you can add statements like:
-- -- ROLLBACK
-- -- DROP TRIGGER update_contact_request_timestamp ON contact_requests;
-- -- DROP FUNCTION update_contact_request_timestamp();
-- -- DROP INDEX idx_contact_requests_created_at;
-- -- DROP INDEX idx_contact_requests_status;
-- -- DROP TABLE contact_requests;
