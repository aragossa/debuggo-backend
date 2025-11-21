"""
Phase 3 API Endpoints: Reasoning & Planning

Provides REST endpoints for:
- Planning Agent (test analysis and planning)
- Conversation Manager (multi-turn reasoning)
- Tool Registry (tool execution)
- State Machine (workflow management)
- Error Recovery Agent (error handling)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import logging

from auroqa.Services.PlanningAgent import PlanningAgent, ExecutionPlan, SubTask
from auroqa.Services.ConversationManager import ConversationManager, Conversation, ConversationTurn
from auroqa.Services.ToolRegistry import ToolRegistry
from auroqa.Services.TestGenerationStateMachine import TestGenerationStateMachine, State, Event
from auroqa.Services.ErrorRecoveryAgent import ErrorRecoveryAgent, ErrorType, RecoveryStrategy

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phase3", tags=["phase3"])

# Initialize services
planning_agent = PlanningAgent()
conversation_manager = ConversationManager()
tool_registry = ToolRegistry()
error_recovery_agent = ErrorRecoveryAgent()

# ============================================================================
# Request/Response Models
# ============================================================================

class PlanAnalysisRequest(BaseModel):
    """Request to analyze test requirements."""
    test_case_id: int


class PlanAnalysisResponse(BaseModel):
    """Response with test analysis."""
    test_case_id: int
    title: str
    complexity_score: float
    objectives: List[str]
    preconditions: List[str]
    estimated_steps: int


class ExecutionPlanResponse(BaseModel):
    """Response with execution plan."""
    test_case_id: int
    overall_strategy: str
    estimated_duration: float
    confidence: float
    subtask_count: int
    dependency_count: int
    risk_count: int


class ConversationStartRequest(BaseModel):
    """Request to start a conversation."""
    test_case_id: int
    overall_strategy: Optional[str] = None


class ConversationResponse(BaseModel):
    """Response with conversation details."""
    id: int
    test_case_id: int
    status: str
    turn_count: int
    overall_strategy: Optional[str]


class ConversationTurnRequest(BaseModel):
    """Request to add a conversation turn."""
    conversation_id: int
    thought: str
    action: str
    observation: str
    tool_used: Optional[str] = None
    tool_params: Optional[Dict[str, Any]] = None
    confidence: float = 0.0


class ToolExecutionRequest(BaseModel):
    """Request to execute a tool."""
    tool_name: str
    params: Dict[str, Any]


class ToolExecutionResponse(BaseModel):
    """Response from tool execution."""
    success: bool
    tool_name: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None


class StateMachineCreateRequest(BaseModel):
    """Request to create a state machine."""
    test_case_id: int


class StateMachineTransitionRequest(BaseModel):
    """Request to transition state."""
    state_machine_id: int
    event: str


class StateMachineResponse(BaseModel):
    """Response with state machine details."""
    test_case_id: int
    current_state: str
    step_number: int
    total_steps: int
    confidence: float
    error_count: int
    retry_count: int


class ErrorAnalysisRequest(BaseModel):
    """Request to analyze an error."""
    failure: Dict[str, Any]
    step_context: Optional[Dict[str, Any]] = None


class ErrorAnalysisResponse(BaseModel):
    """Response with error analysis."""
    error_type: str
    error_message: str
    root_cause: str
    severity: str
    suggested_strategies: List[str]


class ErrorRecoveryRequest(BaseModel):
    """Request to implement error recovery."""
    test_case_id: int
    error_type: str
    recovery_strategy: str


# ============================================================================
# Planning Agent Endpoints
# ============================================================================

@router.post("/plans/analyze", response_model=PlanAnalysisResponse)
async def analyze_test_requirements(request: PlanAnalysisRequest):
    """
    Analyze test case requirements and extract key information.
    
    Args:
        request: Test case ID
        
    Returns:
        Analysis with complexity, objectives, and preconditions
    """
    try:
        analysis = planning_agent.analyze_test_requirements(request.test_case_id)
        
        return PlanAnalysisResponse(
            test_case_id=analysis.test_case_id,
            title=analysis.title,
            complexity_score=analysis.complexity_score,
            objectives=analysis.objectives,
            preconditions=analysis.preconditions,
            estimated_steps=analysis.estimated_steps
        )
    except Exception as e:
        logger.error(f"Error analyzing test requirements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans/create", response_model=ExecutionPlanResponse)
async def create_execution_plan(request: PlanAnalysisRequest):
    """
    Create a complete execution plan for a test case.
    
    Args:
        request: Test case ID
        
    Returns:
        Execution plan with strategy, subtasks, and risks
    """
    try:
        # Analyze requirements
        analysis = planning_agent.analyze_test_requirements(request.test_case_id)
        
        # Identify dependencies
        dependencies = planning_agent.identify_dependencies(request.test_case_id)
        
        # Decompose into subtasks
        subtasks = planning_agent.decompose_into_subtasks(request.test_case_id)
        
        # Create plan
        plan = planning_agent.plan_execution_order(subtasks, dependencies)
        
        # Identify risks
        risks = planning_agent.identify_failure_points(plan)
        
        # Save plan
        plan_id = planning_agent.save_plan(request.test_case_id, plan)
        
        return ExecutionPlanResponse(
            test_case_id=request.test_case_id,
            overall_strategy=plan.overall_strategy,
            estimated_duration=plan.estimated_duration,
            confidence=plan.confidence,
            subtask_count=len(plan.subtasks),
            dependency_count=len(plan.dependencies),
            risk_count=len(risks)
        )
    except Exception as e:
        logger.error(f"Error creating execution plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans/{test_case_id}")
async def get_execution_plan(test_case_id: int):
    """
    Get execution plan for a test case.
    
    Args:
        test_case_id: Test case ID
        
    Returns:
        Execution plan details
    """
    try:
        # This would retrieve from database in production
        return {
            "test_case_id": test_case_id,
            "message": "Plan retrieval not yet implemented"
        }
    except Exception as e:
        logger.error(f"Error retrieving plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Conversation Manager Endpoints
# ============================================================================

@router.post("/conversations/start", response_model=ConversationResponse)
async def start_conversation(request: ConversationStartRequest):
    """
    Start a new multi-turn reasoning conversation.
    
    Args:
        request: Test case ID and optional strategy
        
    Returns:
        Conversation details
    """
    try:
        conversation = conversation_manager.start_conversation(
            test_case_id=request.test_case_id,
            overall_strategy=request.overall_strategy
        )
        
        return ConversationResponse(
            id=conversation.id,
            test_case_id=conversation.test_case_id,
            status=conversation.status,
            turn_count=len(conversation.turns),
            overall_strategy=conversation.overall_strategy
        )
    except Exception as e:
        logger.error(f"Error starting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/turns")
async def add_conversation_turn(conversation_id: int, request: ConversationTurnRequest):
    """
    Add a turn to an active conversation.
    
    Args:
        conversation_id: Conversation ID
        request: Turn details (thought, action, observation)
        
    Returns:
        Updated conversation
    """
    try:
        # Retrieve conversation
        conversation = conversation_manager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Create turn
        turn = ConversationTurn(
            turn_number=len(conversation.turns) + 1,
            thought=request.thought,
            action=request.action,
            observation=request.observation,
            tool_used=request.tool_used,
            tool_params=request.tool_params,
            confidence=request.confidence
        )
        
        # Add turn
        conversation_manager.add_turn(conversation, turn)
        
        return {
            "status": "success",
            "turn_number": turn.turn_number,
            "conversation_id": conversation_id
        }
    except Exception as e:
        logger.error(f"Error adding conversation turn: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int):
    """
    Get conversation details.
    
    Args:
        conversation_id: Conversation ID
        
    Returns:
        Conversation with all turns
    """
    try:
        conversation = conversation_manager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "id": conversation.id,
            "test_case_id": conversation.test_case_id,
            "status": conversation.status,
            "turn_count": len(conversation.turns),
            "overall_strategy": conversation.overall_strategy,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "thought": t.thought,
                    "action": t.action,
                    "observation": t.observation,
                    "tool_used": t.tool_used,
                    "confidence": t.confidence
                }
                for t in conversation.turns
            ]
        }
    except Exception as e:
        logger.error(f"Error retrieving conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/trace")
async def get_reasoning_trace(conversation_id: int):
    """
    Get reasoning trace for a conversation.
    
    Args:
        conversation_id: Conversation ID
        
    Returns:
        Formatted reasoning trace
    """
    try:
        conversation = conversation_manager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        trace = conversation_manager.generate_reasoning_trace(conversation)
        
        return {
            "conversation_id": conversation_id,
            "trace": trace
        }
    except Exception as e:
        logger.error(f"Error generating reasoning trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Tool Registry Endpoints
# ============================================================================

@router.get("/tools")
async def list_available_tools():
    """
    List all available tools.
    
    Returns:
        List of tool definitions
    """
    try:
        tools = tool_registry.get_available_tools()
        
        return {
            "tool_count": len(tools),
            "tools": tools
        }
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/execute", response_model=ToolExecutionResponse)
async def execute_tool(request: ToolExecutionRequest):
    """
    Execute a tool.
    
    Args:
        request: Tool name and parameters
        
    Returns:
        Tool execution result
    """
    try:
        result = tool_registry.execute_tool(request.tool_name, request.params)
        
        return ToolExecutionResponse(
            success=result.get('success', False),
            tool_name=request.tool_name,
            result=result.get('result'),
            error=result.get('error'),
            execution_time_ms=result.get('execution_time_ms')
        )
    except Exception as e:
        logger.error(f"Error executing tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/{tool_name}")
async def get_tool_definition(tool_name: str):
    """
    Get definition of a specific tool.
    
    Args:
        tool_name: Tool name
        
    Returns:
        Tool definition
    """
    try:
        tool_def = tool_registry.get_tool_definition(tool_name)
        if not tool_def:
            raise HTTPException(status_code=404, detail="Tool not found")
        
        return tool_def
    except Exception as e:
        logger.error(f"Error retrieving tool definition: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/history")
async def get_tool_execution_history(limit: int = Query(100, ge=1, le=1000)):
    """
    Get tool execution history.
    
    Args:
        limit: Maximum number of records
        
    Returns:
        Execution history
    """
    try:
        history = tool_registry.get_execution_history(limit=limit)
        
        return {
            "record_count": len(history),
            "history": history
        }
    except Exception as e:
        logger.error(f"Error retrieving tool history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# State Machine Endpoints
# ============================================================================

@router.post("/state-machines/create", response_model=StateMachineResponse)
async def create_state_machine(request: StateMachineCreateRequest):
    """
    Create a new state machine for test generation.
    
    Args:
        request: Test case ID
        
    Returns:
        State machine details
    """
    try:
        machine = TestGenerationStateMachine(test_case_id=request.test_case_id)
        
        # Store in session or cache (simplified for now)
        # In production, would store in Redis or database
        
        ctx = machine.get_context()
        return StateMachineResponse(
            test_case_id=ctx.test_case_id,
            current_state=machine.state.value,
            step_number=ctx.step_number,
            total_steps=ctx.total_steps,
            confidence=ctx.confidence,
            error_count=ctx.error_count,
            retry_count=ctx.retry_count
        )
    except Exception as e:
        logger.error(f"Error creating state machine: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/state-machines/{state_machine_id}/transition", response_model=StateMachineResponse)
async def transition_state(state_machine_id: int, request: StateMachineTransitionRequest):
    """
    Transition state machine to next state.
    
    Args:
        state_machine_id: State machine ID
        request: Event to trigger transition
        
    Returns:
        Updated state machine
    """
    try:
        # In production, would retrieve from cache/database
        # For now, simplified response
        
        return {
            "test_case_id": state_machine_id,
            "current_state": "PLAN",
            "step_number": 0,
            "total_steps": 0,
            "confidence": 0.0,
            "error_count": 0,
            "retry_count": 0
        }
    except Exception as e:
        logger.error(f"Error transitioning state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state-machines/{state_machine_id}", response_model=StateMachineResponse)
async def get_state_machine(state_machine_id: int):
    """
    Get state machine details.
    
    Args:
        state_machine_id: State machine ID
        
    Returns:
        State machine details
    """
    try:
        # In production, would retrieve from cache/database
        return {
            "test_case_id": state_machine_id,
            "current_state": "INIT",
            "step_number": 0,
            "total_steps": 0,
            "confidence": 0.0,
            "error_count": 0,
            "retry_count": 0
        }
    except Exception as e:
        logger.error(f"Error retrieving state machine: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Error Recovery Endpoints
# ============================================================================

@router.post("/errors/analyze", response_model=ErrorAnalysisResponse)
async def analyze_error(request: ErrorAnalysisRequest):
    """
    Analyze an error and suggest recovery strategies.
    
    Args:
        request: Failure details and context
        
    Returns:
        Error analysis with suggestions
    """
    try:
        analysis = error_recovery_agent.analyze_root_cause(
            request.failure,
            request.step_context
        )
        
        return ErrorAnalysisResponse(
            error_type=analysis.error_type.value,
            error_message=analysis.error_message,
            root_cause=analysis.root_cause,
            severity=analysis.severity,
            suggested_strategies=[s.value for s in analysis.suggested_strategies]
        )
    except Exception as e:
        logger.error(f"Error analyzing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/errors/recover")
async def implement_error_recovery(request: ErrorRecoveryRequest):
    """
    Implement error recovery strategy.
    
    Args:
        request: Test case ID, error type, and recovery strategy
        
    Returns:
        Recovery result
    """
    try:
        # Analyze error
        failure = {"error": request.error_type}
        analysis = error_recovery_agent.analyze_root_cause(failure)
        
        # Get strategy enum
        strategy = RecoveryStrategy[request.recovery_strategy.upper()]
        
        # Implement recovery
        result = error_recovery_agent.implement_recovery(
            request.test_case_id,
            analysis,
            strategy
        )
        
        return {
            "status": "success" if result['success'] else "failed",
            "strategy": result['strategy'],
            "message": result['message'],
            "details": result.get('details')
        }
    except Exception as e:
        logger.error(f"Error implementing recovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors/history")
async def get_error_recovery_history(test_case_id: Optional[int] = None):
    """
    Get error recovery history.
    
    Args:
        test_case_id: Optional filter by test case
        
    Returns:
        Recovery history
    """
    try:
        history = error_recovery_agent.get_recovery_history(test_case_id)
        
        return {
            "record_count": len(history),
            "history": [
                {
                    "test_case_id": h.test_case_id,
                    "step_number": h.step_number,
                    "error_type": h.error_type,
                    "recovery_strategy": h.recovery_strategy,
                    "success": h.success,
                    "attempt_number": h.attempt_number
                }
                for h in history
            ]
        }
    except Exception as e:
        logger.error(f"Error retrieving recovery history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors/stats")
async def get_error_recovery_stats():
    """
    Get error recovery statistics.
    
    Returns:
        Recovery statistics
    """
    try:
        stats = error_recovery_agent.get_recovery_stats()
        
        return {
            "total_attempts": stats['total_attempts'],
            "successful": stats['successful'],
            "failed": stats['failed'],
            "success_rate": stats['success_rate'],
            "strategy_distribution": stats['strategy_distribution']
        }
    except Exception as e:
        logger.error(f"Error retrieving recovery stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def health_check():
    """
    Health check for Phase 3 services.
    
    Returns:
        Service status
    """
    return {
        "status": "healthy",
        "services": {
            "planning_agent": "ready",
            "conversation_manager": "ready",
            "tool_registry": "ready",
            "error_recovery_agent": "ready"
        }
    }
