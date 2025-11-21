# Phase 3 Quick Reference Card

## Services Overview

### PlanningAgent
**Purpose**: Analyze tests and create execution plans  
**File**: `/auroqa/Services/PlanningAgent.py`

```python
from Services.PlanningAgent import PlanningAgent

agent = PlanningAgent()

# Analyze test
analysis = agent.analyze_test_requirements(test_case_id=123)
print(f"Complexity: {analysis.complexity_score}")

# Get dependencies
deps = agent.identify_dependencies(test_case_id=123)

# Decompose into subtasks
subtasks = agent.decompose_into_subtasks(test_case_id=123)

# Create plan
plan = agent.plan_execution_order(subtasks, deps)

# Identify risks
risks = agent.identify_failure_points(plan)

# Save plan
plan_id = agent.save_plan(test_case_id=123, plan=plan)
```

---

### ConversationManager
**Purpose**: Multi-turn reasoning with ReAct pattern  
**File**: `/auroqa/Services/ConversationManager.py`

```python
from Services.ConversationManager import ConversationManager, ConversationTurn

manager = ConversationManager()

# Start conversation
conv = manager.start_conversation(
    test_case_id=123,
    overall_strategy="Test login flow"
)

# Add turns
turn = ConversationTurn(
    turn_number=1,
    thought="Need to find email field",
    action="Analyze page",
    observation="Found email field",
    tool_used="analyze_page_elements"
)
manager.add_turn(conv, turn)

# Get history
history = manager.get_conversation_history(test_case_id=123)

# Generate trace
trace = manager.generate_reasoning_trace(conv)

# Complete conversation
manager.complete_conversation(conv, status='completed')
```

---

### ToolRegistry
**Purpose**: Register and execute tools  
**File**: `/auroqa/Services/ToolRegistry.py`

```python
from Services.ToolRegistry import ToolRegistry

registry = ToolRegistry()

# Get available tools
tools = registry.get_available_tools()

# Execute tool
result = registry.execute_tool(
    'validate_selector',
    {'selector': '//input[@id="email"]', 'selector_type': 'xpath'}
)

# Register custom tool
def my_tool(param1):
    return {"result": param1}

registry.register_tool(
    name='my_tool',
    func=my_tool,
    description='My custom tool',
    params={'param1': 'str'},
    returns='dict'
)

# Get execution history
history = registry.get_execution_history(limit=10)
```

---

### TestGenerationStateMachine
**Purpose**: Manage test generation workflow  
**File**: `/auroqa/Services/TestGenerationStateMachine.py`

```python
from Services.TestGenerationStateMachine import TestGenerationStateMachine, Event

machine = TestGenerationStateMachine(test_case_id=123)

# Transition through states
machine.transition(Event.ANALYZE)
machine.transition(Event.PLAN)
machine.transition(Event.GENERATE)

# Update context
machine.update_context(step_number=5, total_steps=10)

# Increment counters
machine.increment_step()
machine.increment_error_count()

# Set confidence
machine.set_confidence(0.95)

# Check state
if machine.is_complete():
    print("Test generation complete!")

if machine.is_error():
    if machine.can_retry():
        machine.transition(Event.RETRY)

# Get summary
summary = machine.get_summary()
print(f"State: {summary['current_state']}")
```

---

### ErrorRecoveryAgent
**Purpose**: Detect and recover from errors  
**File**: `/auroqa/Services/ErrorRecoveryAgent.py`

```python
from Services.ErrorRecoveryAgent import ErrorRecoveryAgent

agent = ErrorRecoveryAgent()

# Detect failure
failure = {'error': 'Element not found: //input[@id="email"]'}
if agent.detect_failure(failure):
    # Analyze root cause
    analysis = agent.analyze_root_cause(failure)
    print(f"Error type: {analysis.error_type.value}")
    print(f"Root cause: {analysis.root_cause}")
    
    # Suggest strategy
    strategy = agent.suggest_recovery_strategy(analysis)
    
    # Implement recovery
    result = agent.implement_recovery(
        test_case_id=123,
        analysis=analysis,
        strategy=strategy
    )
    
    if not result['success']:
        # Escalate to human
        agent.escalate_to_human(test_case_id=123, analysis=analysis)

# Get statistics
stats = agent.get_recovery_stats()
print(f"Success rate: {stats['success_rate']:.2%}")
```

---

## Common Workflows

### Complete Test Planning
```python
from Services.PlanningAgent import PlanningAgent

agent = PlanningAgent()

# 1. Analyze
analysis = agent.analyze_test_requirements(test_case_id=123)

# 2. Identify dependencies
dependencies = agent.identify_dependencies(test_case_id=123)

# 3. Decompose
subtasks = agent.decompose_into_subtasks(test_case_id=123)

# 4. Plan
plan = agent.plan_execution_order(subtasks, dependencies)

# 5. Identify risks
risks = agent.identify_failure_points(plan)

# 6. Save
plan_id = agent.save_plan(test_case_id=123, plan=plan)

print(f"Plan created: {plan_id}")
print(f"Confidence: {plan.confidence:.2f}")
print(f"Risks: {len(risks)}")
```

### Multi-Turn Reasoning
```python
from Services.ConversationManager import ConversationManager, ConversationTurn
from Services.ToolRegistry import ToolRegistry

manager = ConversationManager()
registry = ToolRegistry()

# Start
conv = manager.start_conversation(test_case_id=123)

# Turn 1: Analyze
result = registry.execute_tool('analyze_page_elements', {'page_html': '<html>...'})
turn1 = ConversationTurn(
    turn_number=1,
    thought="Need to find elements",
    action="Analyze page",
    observation=str(result),
    tool_used="analyze_page_elements"
)
manager.add_turn(conv, turn1)

# Turn 2: Validate
result = registry.execute_tool('validate_selector', {'selector': '//input'})
turn2 = ConversationTurn(
    turn_number=2,
    thought="Need to validate selector",
    action="Validate",
    observation=str(result),
    tool_used="validate_selector"
)
manager.add_turn(conv, turn2)

# Complete
manager.complete_conversation(conv)

# Get trace
trace = manager.generate_reasoning_trace(conv)
```

### Error Recovery Workflow
```python
from Services.ErrorRecoveryAgent import ErrorRecoveryAgent

agent = ErrorRecoveryAgent()

# Simulate failure
failure = {'error': 'Element not found: //button[@id="submit"]'}

# Detect
if agent.detect_failure(failure):
    # Analyze
    analysis = agent.analyze_root_cause(failure)
    
    # Suggest
    strategy = agent.suggest_recovery_strategy(analysis)
    
    # Implement
    result = agent.implement_recovery(123, analysis, strategy)
    
    if result['success']:
        print(f"Recovered using: {result['strategy']}")
    else:
        print("Recovery failed, escalating...")
        agent.escalate_to_human(123, analysis)
```

---

## Database Tables

### conversations
```sql
SELECT * FROM conversations WHERE test_case_id = 123;
```

### conversation_turns
```sql
SELECT * FROM conversation_turns WHERE conversation_id = 1;
```

### reasoning_traces
```sql
SELECT * FROM reasoning_traces WHERE test_case_id = 123;
```

### error_recovery_attempts
```sql
SELECT * FROM error_recovery_attempts WHERE test_case_id = 123;
```

### execution_plans
```sql
SELECT * FROM execution_plans WHERE test_case_id = 123;
```

### tool_execution_history
```sql
SELECT * FROM tool_execution_history WHERE conversation_id = 1;
```

---

## Testing

### Run All Tests
```bash
pytest tests/test_phase3_reasoning_system.py -v
```

### Run Specific Service Tests
```bash
# PlanningAgent
pytest tests/test_phase3_reasoning_system.py::TestPlanningAgent -v

# ConversationManager
pytest tests/test_phase3_reasoning_system.py::TestConversationManager -v

# ToolRegistry
pytest tests/test_phase3_reasoning_system.py::TestToolRegistry -v

# State Machine
pytest tests/test_phase3_reasoning_system.py::TestGenerationStateMachine -v

# Error Recovery
pytest tests/test_phase3_reasoning_system.py::TestErrorRecoveryAgent -v
```

### Run with Coverage
```bash
pytest tests/test_phase3_reasoning_system.py --cov --cov-report=html
```

---

## Performance Targets

| Operation | Target | Status |
|-----------|--------|--------|
| Analyze requirements | <150ms | ✅ |
| Identify dependencies | <200ms | ✅ |
| Decompose subtasks | <250ms | ✅ |
| Create plan | <100ms | ✅ |
| Add conversation turn | <100ms | ✅ |
| Analyze error | <100ms | ✅ |
| State transition | <10ms | ✅ |
| Tool execution | <50ms | ✅ |

---

## Error Types & Recovery Strategies

### Error Types
- `element_not_found` - Element selector issue
- `timeout` - Page load timeout
- `invalid_selector` - Bad XPath/CSS
- `assertion_failed` - Validation failed
- `api_error` - API request failed
- `navigation_error` - URL navigation failed
- `data_validation_error` - Data validation failed

### Recovery Strategies
1. `RETRY_PROMPT` - Retry with different phrasing
2. `ALTERNATIVE_SELECTOR` - Try CSS instead of XPath
3. `DECOMPOSE_STEP` - Break into smaller steps
4. `FEW_SHOT_EXAMPLE` - Use examples
5. `WAIT_AND_RETRY` - Add wait and retry
6. `SKIP_STEP` - Skip problematic step
7. `ESCALATE` - Escalate to human review

---

## Useful Commands

### Deploy Phase 3
```bash
bash scripts/deploy_phase3.sh
```

### Apply Database Migration
```bash
psql -h localhost -U postgres -d postgres -f auroqa/migrations/20251125_reasoning_system.sql
```

### Check Database Tables
```bash
psql -h localhost -U postgres -d postgres -c "\dt conversations conversation_turns reasoning_traces error_recovery_attempts execution_plans tool_execution_history"
```

### View Service Logs
```bash
tail -f logs/phase3.log
```

---

## Documentation Links

- **Implementation**: `/auroqa/docs/ai-agent/PHASE3_IMPLEMENTATION_SUMMARY.md`
- **Testing Guide**: `/auroqa/docs/ai-agent/PHASE3_TESTING_GUIDE.md`
- **Completion Summary**: `/PHASE3_COMPLETION_SUMMARY.md`
- **AI Agent Plan**: `/auroqa/docs/ai-agent/AI_AGENT_PLAN_PART2.md`

---

## Quick Troubleshooting

### Import Error
```python
import sys
sys.path.insert(0, '/Users/aragossa/dzrprj/auroqa')
```

### Database Connection Error
```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -c "SELECT 1"
```

### Test Failures
```bash
# Run with verbose output
pytest tests/test_phase3_reasoning_system.py -vv --tb=long
```

### Performance Issues
```bash
# Run performance tests only
pytest tests/test_phase3_reasoning_system.py::TestPhase3Performance -v
```

---

**Last Updated**: November 16, 2025  
**Status**: ✅ Phase 3 Complete
