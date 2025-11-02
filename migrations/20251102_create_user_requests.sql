-- Migration: Create user_requests table for bug reports and feature requests
-- Description: Allows users to submit bugs/feature requests and admins to manage them
-- Date: 2025-11-02

-- Create user_requests table
CREATE TABLE IF NOT EXISTS user_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    request_type VARCHAR(20) NOT NULL CHECK (request_type IN ('bug', 'feature', 'improvement', 'question')),
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'in_progress', 'resolved', 'closed', 'rejected')),
    priority VARCHAR(20) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    browser_info TEXT,
    page_url TEXT,
    screenshot_path TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    admin_notes TEXT
);

-- Create indexes for performance
CREATE INDEX idx_user_requests_user_id ON user_requests(user_id);
CREATE INDEX idx_user_requests_client_id ON user_requests(client_id);
CREATE INDEX idx_user_requests_status ON user_requests(status);
CREATE INDEX idx_user_requests_type ON user_requests(request_type);
CREATE INDEX idx_user_requests_created_at ON user_requests(created_at DESC);

-- Create trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_user_requests_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_user_requests_updated_at
    BEFORE UPDATE ON user_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_user_requests_updated_at();

-- Create comments for documentation
COMMENT ON TABLE user_requests IS 'Stores bug reports and feature requests submitted by users';
COMMENT ON COLUMN user_requests.request_type IS 'Type of request: bug, feature, improvement, or question';
COMMENT ON COLUMN user_requests.status IS 'Current status: new, in_progress, resolved, closed, or rejected';
COMMENT ON COLUMN user_requests.priority IS 'Priority level set by admin: low, medium, high, or critical';
COMMENT ON COLUMN user_requests.browser_info IS 'Browser and OS information for bug reports';
COMMENT ON COLUMN user_requests.page_url IS 'URL where the bug occurred or feature is needed';
