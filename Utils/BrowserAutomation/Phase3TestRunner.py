"""
Phase 3 Integration for TestRunner

Integrates Phase 3 state machine and error recovery with TestRunner
for intelligent test execution with planning, state tracking, and recovery.

Features:
- State machine-driven test execution
- Execution plan following
- Error detection and recovery
- Confidence tracking
- Execution history and analytics
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from auroqa.Services.TestGenerationStateMachine import TestGenerationStateMachine, State, Event
from auroqa.Services.ErrorRecoveryAgent import ErrorRecoveryAgent
from auroqa.Services.ConversationManager import ConversationManager, ConversationTurn
from auroqa.Utils.System import System

logger = logging.getLogger(__name__)


class Phase3TestRunner:
    """
    Integrates Phase 3 services with TestRunner for intelligent execution.
    
    Provides:
    - State machine-driven execution flow
    - Execution plan following
    - Error detection and recovery
    - Confidence tracking
    - Execution analytics
    """

    def __init__(self, test_case_id: int):
        """
        Initialize Phase 3 TestRunner.
        
        Args:
            test_case_id: Test case ID
        """
        self.test_case_id = test_case_id
        self.state_machine = TestGenerationStateMachine(test_case_id=test_case_id)
        self.error_recovery_agent = ErrorRecoveryAgent()
        self.conversation_manager = ConversationManager()
        self.system = System()
        self.logger = logging.getLogger(__name__)
        
        # Execution tracking
        self.execution_history: List[Dict[str, Any]] = []
        self.step_results: List[Dict[str, Any]] = []
        self.errors_encountered: List[Dict[str, Any]] = []
        self.recovery_attempts: List[Dict[str, Any]] = []

    # ========================================================================
    # State Machine Integration
    # ========================================================================

    def initialize_execution(self, total_steps: int) -> Dict[str, Any]:
        """
        Initialize test execution with state machine.
        
        Args:
            total_steps: Total number of steps to execute
            
        Returns:
            Initialization result
        """
        try:
            # Update context
            self.state_machine.update_context(total_steps=total_steps)
            
            # Transition to ANALYZE
            self.state_machine.transition(Event.ANALYZE)
            
            ctx = self.state_machine.get_context()
            
            self.logger.info(
                f"✓ Test execution initialized: "
                f"test_id={self.test_case_id}, "
                f"total_steps={total_steps}, "
                f"state={self.state_machine.state.value}"
            )
            
            return {
                "status": "initialized",
                "test_case_id": self.test_case_id,
                "total_steps": total_steps,
                "state": self.state_machine.state.value,
                "confidence": ctx.confidence,
            }
        except Exception as e:
            self.logger.error(f"Error initializing execution: {e}")
            return {"status": "error", "error": str(e)}

    def start_planning_phase(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start planning phase with execution plan.
        
        Args:
            plan_data: Execution plan data
            
        Returns:
            Planning phase result
        """
        try:
            # Transition to PLAN
            success = self.state_machine.transition(Event.PLAN)
            if not success:
                raise ValueError(f"Cannot transition to PLAN from {self.state_machine.state.value}")
            
            # Update context with plan
            self.state_machine.update_context(context_data={"plan": plan_data})
            
            self.logger.info(
                f"✓ Planning phase started: "
                f"test_id={self.test_case_id}, "
                f"strategy={plan_data.get('overall_strategy', 'N/A')}"
            )
            
            return {
                "status": "planning_started",
                "state": self.state_machine.state.value,
                "plan": plan_data,
            }
        except Exception as e:
            self.logger.error(f"Error starting planning phase: {e}")
            return {"status": "error", "error": str(e)}

    def start_generation_phase(self) -> Dict[str, Any]:
        """
        Start generation phase.
        
        Returns:
            Generation phase result
        """
        try:
            # Transition to GENERATE
            success = self.state_machine.transition(Event.GENERATE)
            if not success:
                raise ValueError(f"Cannot transition to GENERATE from {self.state_machine.state.value}")
            
            self.logger.info(
                f"✓ Generation phase started: test_id={self.test_case_id}"
            )
            
            return {
                "status": "generation_started",
                "state": self.state_machine.state.value,
            }
        except Exception as e:
            self.logger.error(f"Error starting generation phase: {e}")
            return {"status": "error", "error": str(e)}

    def execute_step(
        self,
        step_number: int,
        step_data: Dict[str, Any],
        execute_fn: callable,
    ) -> Dict[str, Any]:
        """
        Execute a single test step with state tracking.
        
        Args:
            step_number: Step number
            step_data: Step details
            execute_fn: Function to execute step
            
        Returns:
            Step execution result
        """
        try:
            # Transition to GENERATE if needed
            if self.state_machine.state != State.GENERATE:
                self.state_machine.transition(Event.GENERATE)
            
            # Update step number
            self.state_machine.update_context(step_number=step_number)
            
            self.logger.info(
                f"→ Executing step {step_number}: {step_data.get('action', 'N/A')}"
            )
            
            # Execute step
            start_time = datetime.now()
            result = execute_fn(step_data)
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Track result
            step_result = {
                "step_number": step_number,
                "action": step_data.get("action"),
                "success": result.get("success", False),
                "execution_time": execution_time,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
            self.step_results.append(step_result)
            
            # Update confidence
            if result.get("success"):
                new_confidence = min(1.0, self.state_machine.context.confidence + 0.05)
                self.state_machine.set_confidence(new_confidence)
                self.logger.info(
                    f"✓ Step {step_number} succeeded: "
                    f"time={execution_time:.2f}s, "
                    f"confidence={new_confidence:.2f}"
                )
            else:
                # Step failed - handle error
                self.logger.warning(
                    f"✗ Step {step_number} failed: {result.get('error', 'Unknown error')}"
                )
                return self._handle_step_failure(step_number, step_data, result)
            
            return step_result
            
        except Exception as e:
            self.logger.error(f"Error executing step {step_number}: {e}")
            return {
                "step_number": step_number,
                "success": False,
                "error": str(e),
            }

    def validate_step(self, step_number: int, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate step execution result.
        
        Args:
            step_number: Step number
            result: Step result
            
        Returns:
            Validation result
        """
        try:
            # Transition to VALIDATE
            success = self.state_machine.transition(Event.VALIDATE)
            if not success:
                self.logger.warning(f"Cannot transition to VALIDATE from {self.state_machine.state.value}")
            
            # Validate result
            is_valid = result.get("success", False)
            
            if is_valid:
                self.logger.info(f"✓ Step {step_number} validated successfully")
            else:
                self.logger.warning(f"✗ Step {step_number} validation failed")
            
            return {
                "step_number": step_number,
                "is_valid": is_valid,
                "validation_time": datetime.now().isoformat(),
            }
            
        except Exception as e:
            self.logger.error(f"Error validating step: {e}")
            return {"is_valid": False, "error": str(e)}

    def complete_execution(self, success: bool = True) -> Dict[str, Any]:
        """
        Complete test execution.
        
        Args:
            success: Whether execution was successful
            
        Returns:
            Completion result
        """
        try:
            # Transition to COMPLETE
            event = Event.COMPLETE if success else Event.ERROR
            self.state_machine.transition(event)
            
            # Get summary
            summary = self.state_machine.get_summary()
            
            self.logger.info(
                f"✓ Test execution completed: "
                f"test_id={self.test_case_id}, "
                f"success={success}, "
                f"steps_completed={summary['step_number']}, "
                f"final_confidence={summary['confidence']:.2f}"
            )
            
            return {
                "status": "completed",
                "success": success,
                "summary": summary,
                "steps_executed": len(self.step_results),
                "errors_encountered": len(self.errors_encountered),
                "recoveries_attempted": len(self.recovery_attempts),
            }
            
        except Exception as e:
            self.logger.error(f"Error completing execution: {e}")
            return {"status": "error", "error": str(e)}

    # ========================================================================
    # Error Handling and Recovery
    # ========================================================================

    def _handle_step_failure(
        self,
        step_number: int,
        step_data: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle step failure with error recovery.
        
        Args:
            step_number: Step number
            step_data: Step details
            result: Step result
            
        Returns:
            Failure handling result
        """
        try:
            # Increment error count
            self.state_machine.increment_error_count()
            
            # Detect and analyze error
            failure = {
                "error": result.get("error", "Unknown error"),
                "step_number": step_number,
            }
            
            error_info = self.error_recovery_agent.handle_generation_error(
                self.test_case_id,
                failure,
                step_context=step_data,
            )
            
            # Track error
            error_record = {
                "step_number": step_number,
                "error_type": error_info.get("error_type"),
                "severity": error_info.get("severity"),
                "suggested_strategy": error_info.get("suggested_strategy"),
                "timestamp": datetime.now().isoformat(),
            }
            self.errors_encountered.append(error_record)
            
            self.logger.warning(
                f"⚠ Error detected at step {step_number}: "
                f"type={error_info.get('error_type')}, "
                f"severity={error_info.get('severity')}, "
                f"strategy={error_info.get('suggested_strategy')}"
            )
            
            # Check if can retry
            if self.state_machine.can_retry():
                # Attempt recovery
                recovery_result = self.error_recovery_agent.implement_error_recovery(
                    self.test_case_id,
                    error_info.get("error_type"),
                    error_info.get("suggested_strategy"),
                )
                
                recovery_record = {
                    "step_number": step_number,
                    "strategy": error_info.get("suggested_strategy"),
                    "success": recovery_result.get("success", False),
                    "timestamp": datetime.now().isoformat(),
                }
                self.recovery_attempts.append(recovery_record)
                
                if recovery_result.get("success"):
                    self.logger.info(
                        f"✓ Recovery successful at step {step_number}: "
                        f"strategy={error_info.get('suggested_strategy')}"
                    )
                    # Increment retry count
                    self.state_machine.context.retry_count += 1
                    return {
                        "step_number": step_number,
                        "success": False,
                        "error": result.get("error"),
                        "recovery_attempted": True,
                        "recovery_success": True,
                    }
                else:
                    self.logger.warning(
                        f"✗ Recovery failed at step {step_number}"
                    )
            
            # Cannot recover - escalate
            self.logger.error(
                f"✗ Cannot recover from error at step {step_number} - escalating"
            )
            self.error_recovery_agent.escalate_to_human(
                self.test_case_id,
                error_info,
            )
            
            return {
                "step_number": step_number,
                "success": False,
                "error": result.get("error"),
                "recovery_attempted": True,
                "recovery_success": False,
                "escalated": True,
            }
            
        except Exception as e:
            self.logger.error(f"Error handling step failure: {e}")
            return {
                "step_number": step_number,
                "success": False,
                "error": str(e),
            }

    # ========================================================================
    # Conversation Tracking
    # ========================================================================

    def start_execution_conversation(self, strategy: str) -> Dict[str, Any]:
        """
        Start conversation to track execution reasoning.
        
        Args:
            strategy: Execution strategy
            
        Returns:
            Conversation details
        """
        try:
            conversation = self.conversation_manager.start_conversation(
                test_case_id=self.test_case_id,
                overall_strategy=strategy,
            )
            
            self.logger.info(
                f"✓ Execution conversation started: "
                f"conversation_id={conversation.id}"
            )
            
            return {
                "conversation_id": conversation.id,
                "test_case_id": self.test_case_id,
                "status": conversation.status,
            }
        except Exception as e:
            self.logger.error(f"Error starting execution conversation: {e}")
            return {"error": str(e)}

    def track_step_execution(
        self,
        conversation_id: int,
        step_number: int,
        step_data: Dict[str, Any],
        result: Dict[str, Any],
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Track step execution in conversation.
        
        Args:
            conversation_id: Conversation ID
            step_number: Step number
            step_data: Step details
            result: Step result
            confidence: Confidence score
            
        Returns:
            Tracking result
        """
        try:
            conversation = self.conversation_manager.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
            
            # Create turn
            turn = ConversationTurn(
                turn_number=step_number,
                thought=f"Executing step {step_number}: {step_data.get('action')}",
                action=step_data.get("action", "execute"),
                observation=f"Result: {result.get('success', False)}",
                tool_used=None,
                confidence=confidence,
            )
            
            self.conversation_manager.add_turn(conversation, turn)
            
            self.logger.info(
                f"✓ Step {step_number} tracked in conversation: "
                f"confidence={confidence:.2f}"
            )
            
            return {
                "turn_number": step_number,
                "conversation_id": conversation_id,
                "tracked": True,
            }
        except Exception as e:
            self.logger.error(f"Error tracking step execution: {e}")
            return {"error": str(e)}

    # ========================================================================
    # Execution Analytics
    # ========================================================================

    def get_execution_status(self) -> Dict[str, Any]:
        """
        Get current execution status.
        
        Returns:
            Execution status
        """
        try:
            ctx = self.state_machine.get_context()
            
            return {
                "test_case_id": self.test_case_id,
                "current_state": self.state_machine.state.value,
                "step_number": ctx.step_number,
                "total_steps": ctx.total_steps,
                "confidence": ctx.confidence,
                "error_count": ctx.error_count,
                "retry_count": ctx.retry_count,
                "steps_executed": len(self.step_results),
                "errors_encountered": len(self.errors_encountered),
                "recoveries_attempted": len(self.recovery_attempts),
                "is_complete": self.state_machine.is_complete(),
                "is_error": self.state_machine.is_error(),
            }
        except Exception as e:
            self.logger.error(f"Error getting execution status: {e}")
            return {"error": str(e)}

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        Get execution summary.
        
        Returns:
            Execution summary
        """
        try:
            summary = self.state_machine.get_summary()
            
            # Calculate statistics
            successful_steps = sum(1 for s in self.step_results if s.get("success"))
            failed_steps = len(self.step_results) - successful_steps
            total_time = sum(s.get("execution_time", 0) for s in self.step_results)
            
            successful_recoveries = sum(
                1 for r in self.recovery_attempts if r.get("success")
            )
            
            return {
                "test_case_id": self.test_case_id,
                "state_machine_summary": summary,
                "execution_statistics": {
                    "total_steps": len(self.step_results),
                    "successful_steps": successful_steps,
                    "failed_steps": failed_steps,
                    "success_rate": successful_steps / len(self.step_results)
                    if self.step_results
                    else 0,
                    "total_execution_time": total_time,
                    "average_step_time": total_time / len(self.step_results)
                    if self.step_results
                    else 0,
                },
                "error_statistics": {
                    "total_errors": len(self.errors_encountered),
                    "error_types": list(set(e.get("error_type") for e in self.errors_encountered)),
                    "high_severity_errors": sum(
                        1 for e in self.errors_encountered if e.get("severity") == "high"
                    ),
                },
                "recovery_statistics": {
                    "total_attempts": len(self.recovery_attempts),
                    "successful_recoveries": successful_recoveries,
                    "recovery_success_rate": successful_recoveries / len(self.recovery_attempts)
                    if self.recovery_attempts
                    else 0,
                },
            }
        except Exception as e:
            self.logger.error(f"Error getting execution summary: {e}")
            return {"error": str(e)}

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """
        Get execution history.
        
        Returns:
            Execution history
        """
        return self.step_results

    def get_errors_encountered(self) -> List[Dict[str, Any]]:
        """
        Get errors encountered during execution.
        
        Returns:
            List of errors
        """
        return self.errors_encountered

    def get_recovery_attempts(self) -> List[Dict[str, Any]]:
        """
        Get recovery attempts.
        
        Returns:
            List of recovery attempts
        """
        return self.recovery_attempts
