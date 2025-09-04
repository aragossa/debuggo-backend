-- Create user checklists tables
-- Migration: 20250902_create_user_checklists.sql

-- Create checklists table
CREATE TABLE IF NOT EXISTS checklists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create checklist_items table  
CREATE TABLE IF NOT EXISTS checklist_items (
    id SERIAL PRIMARY KEY,
    checklist_id INTEGER NOT NULL REFERENCES checklists(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT true,
    is_checked BOOLEAN DEFAULT false,
    order_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_checklists_user_id ON checklists(user_id);
CREATE INDEX IF NOT EXISTS idx_checklists_user_active ON checklists(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_checklist_items_checklist_id ON checklist_items(checklist_id);
CREATE INDEX IF NOT EXISTS idx_checklist_items_order ON checklist_items(checklist_id, order_index);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_checklist_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_checklists_timestamp
    BEFORE UPDATE ON checklists
    FOR EACH ROW
    EXECUTE FUNCTION update_checklist_timestamp();

CREATE TRIGGER update_checklist_items_timestamp
    BEFORE UPDATE ON checklist_items
    FOR EACH ROW
    EXECUTE FUNCTION update_checklist_timestamp();
