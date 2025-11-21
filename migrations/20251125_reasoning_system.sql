-- Phase 3: Reasoning & Planning System
-- Implements multi-turn conversations, reasoning traces, and error recovery

-- Conversations table: Tracks multi-turn reasoning sessions
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    overall_strategy TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    metadata JSONB
);

-- Conversation turns: Individual turns in the ReAct pattern
CREATE TABLE IF NOT EXISTS conversation_turns (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    thought TEXT,
    action TEXT,
    observation TEXT,
    tool_used VARCHAR(50),
    tool_params JSONB,
    tool_result JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reasoning traces: Detailed reasoning for each step
CREATE TABLE IF NOT EXISTS reasoning_traces (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    reasoning TEXT,
    decision TEXT,
    confidence FLOAT,
    alternative_approaches JSONB,
    selected_approach VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Error recovery attempts: Track error recovery strategies
CREATE TABLE IF NOT EXISTS error_recovery_attempts (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    error_type VARCHAR(100),
    error_message TEXT,
    recovery_strategy VARCHAR(100),
    recovery_details JSONB,
    success BOOLEAN,
    attempt_number INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Execution plans: Store detailed execution plans
CREATE TABLE IF NOT EXISTS execution_plans (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    plan_data JSONB NOT NULL,
    overall_strategy TEXT,
    subtasks JSONB,
    dependencies JSONB,
    risk_points JSONB,
    estimated_duration FLOAT,
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tool execution history: Track tool usage and results
CREATE TABLE IF NOT EXISTS tool_execution_history (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    tool_params JSONB,
    tool_result JSONB,
    execution_time_ms FLOAT,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_test_case ON conversations(test_case_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conversation_turns_conversation ON conversation_turns(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_turns_turn_number ON conversation_turns(turn_number);
CREATE INDEX IF NOT EXISTS idx_reasoning_traces_test_case ON reasoning_traces(test_case_id);
CREATE INDEX IF NOT EXISTS idx_reasoning_traces_step ON reasoning_traces(step_number);
CREATE INDEX IF NOT EXISTS idx_error_recovery_test_case ON error_recovery_attempts(test_case_id);
CREATE INDEX IF NOT EXISTS idx_error_recovery_strategy ON error_recovery_attempts(recovery_strategy);
CREATE INDEX IF NOT EXISTS idx_execution_plans_test_case ON execution_plans(test_case_id);
CREATE INDEX IF NOT EXISTS idx_tool_execution_conversation ON tool_execution_history(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tool_execution_name ON tool_execution_history(tool_name);

-- Triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_execution_plans_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER execution_plans_update_timestamp
BEFORE UPDATE ON execution_plans
FOR EACH ROW
EXECUTE FUNCTION update_execution_plans_timestamp();
