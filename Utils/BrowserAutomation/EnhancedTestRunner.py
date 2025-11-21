"""
EnhancedTestRunner: TestRunner with Phase 3 Integration

Wraps TestRunner with Phase 3 services for:
- State machine-driven test execution
- Execution plan following
- Error detection and recovery
- Confidence tracking
- Execution history and analytics

Maintains backward compatibility with existing TestRunner.
"""

import logging
from typing import Dict, Any, Optional, List, Callable
from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
from auroqa.Utils.BrowserAutomation.Phase3TestRunner import Phase3TestRunner

logger = logging.getLogger(__name__)


class EnhancedTestRunner(TestRunner):
    """
    Enhanced TestRunner with Phase 3 integration.
    
    Extends TestRunner with state machine-driven execution, error recovery,
    and execution analytics while maintaining full backward compatibility.
    
    Usage:
        runner = EnhancedTestRunner()
        
        # Use like regular TestRunner
        result = runner.run_test(test_case_id, steps)
        
        # Or use Phase 3 features
        runner.initialize_execution(test_case_id, total_steps=10)
        runner.execute_step_with_tracking(step_number, step_data, execute_fn)
    """

    def __init__(self, user_id=None, test_case_id=None):
        """Initialize EnhancedTestRunner with Phase 3 integration."""
        super().__init__(user_id=user_id, test_case_id=test_case_id)
        self.phase3_runners: Dict[int, Phase3TestRunner] = {}
        self.logger = logging.getLogger(__name__)
        self.logger.info("✓ EnhancedTestRunner initialized with Phase 3 integration")

    # ========================================================================
    # Execution Initialization
    # ========================================================================

    def initialize_execution(
        self, test_case_id: int, total_steps: int, plan: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Initialize test execution with state machine.
        
        Args:
            test_case_id: Test case ID
            total_steps: Total number of steps
            plan: Optional execution plan
            
        Returns:
            Initialization result
        """
        try:
            # Create Phase 3 runner
            phase3_runner = Phase3TestRunner(test_case_id=test_case_id)
            self.phase3_runners[test_case_id] = phase3_runner
            
            # Initialize execution
            result = phase3_runner.initialize_execution(total_steps)
            
            # Start planning phase if plan provided
            if plan:
                phase3_runner.start_planning_phase(plan)
            
            self.logger.info(
                f"✓ Execution initialized: "
                f"test_id={test_case_id}, "
                f"total_steps={total_steps}"
            )
            
            return result
        except Exception as e:
            self.logger.error(f"Error initializing execution: {e}")
            return {"status": "error", "error": str(e)}

    def start_planning_phase(
        self, test_case_id: int, plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Start planning phase with execution plan.
        
        Args:
            test_case_id: Test case ID
            plan: Execution plan
            
        Returns:
            Planning phase result
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            result = phase3_runner.start_planning_phase(plan)
            
            self.logger.info(
                f"✓ Planning phase started: test_id={test_case_id}"
            )
            
            return result
        except Exception as e:
            self.logger.error(f"Error starting planning phase: {e}")
            return {"status": "error", "error": str(e)}

    def start_generation_phase(self, test_case_id: int) -> Dict[str, Any]:
        """
        Start generation phase.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            Generation phase result
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            result = phase3_runner.start_generation_phase()
            
            self.logger.info(
                f"✓ Generation phase started: test_id={test_case_id}"
            )
            
            return result
        except Exception as e:
            self.logger.error(f"Error starting generation phase: {e}")
            return {"status": "error", "error": str(e)}

    # ========================================================================
    # Step Execution with Tracking
    # ========================================================================

    def execute_step_with_tracking(
        self,
        test_case_id: int,
        step_number: int,
        step_data: Dict[str, Any],
        execute_fn: Callable,
    ) -> Dict[str, Any]:
        """
        Execute a step with Phase 3 tracking.
        
        Args:
            test_case_id: Test case ID
            step_number: Step number
            step_data: Step details
            execute_fn: Function to execute step
            
        Returns:
            Step execution result
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            # Execute with Phase 3 tracking
            result = phase3_runner.execute_step(step_number, step_data, execute_fn)
            
            return result
        except Exception as e:
            self.logger.error(f"Error executing step with tracking: {e}")
            return {
                "step_number": step_number,
                "success": False,
                "error": str(e),
            }

    def validate_step(
        self, test_case_id: int, step_number: int, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate step execution result.
        
        Args:
            test_case_id: Test case ID
            step_number: Step number
            result: Step result
            
        Returns:
            Validation result
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            validation = phase3_runner.validate_step(step_number, result)
            
            return validation
        except Exception as e:
            self.logger.error(f"Error validating step: {e}")
            return {"is_valid": False, "error": str(e)}

    # ========================================================================
    # Execution Completion
    # ========================================================================

    def complete_execution(
        self, test_case_id: int, success: bool = True
    ) -> Dict[str, Any]:
        """
        Complete test execution.
        
        Args:
            test_case_id: Test case ID
            success: Whether execution was successful
            
        Returns:
            Completion result
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            result = phase3_runner.complete_execution(success)
            
            self.logger.info(
                f"✓ Execution completed: test_id={test_case_id}, success={success}"
            )
            
            return result
        except Exception as e:
            self.logger.error(f"Error completing execution: {e}")
            return {"status": "error", "error": str(e)}

    # ========================================================================
    # Conversation Tracking
    # ========================================================================

    def start_execution_conversation(
        self, test_case_id: int, strategy: str
    ) -> Dict[str, Any]:
        """
        Start conversation to track execution reasoning.
        
        Args:
            test_case_id: Test case ID
            strategy: Execution strategy
            
        Returns:
            Conversation details
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            result = phase3_runner.start_execution_conversation(strategy)
            
            return result
        except Exception as e:
            self.logger.error(f"Error starting execution conversation: {e}")
            return {"error": str(e)}

    def track_step_execution(
        self,
        test_case_id: int,
        conversation_id: int,
        step_number: int,
        step_data: Dict[str, Any],
        result: Dict[str, Any],
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Track step execution in conversation.
        
        Args:
            test_case_id: Test case ID
            conversation_id: Conversation ID
            step_number: Step number
            step_data: Step details
            result: Step result
            confidence: Confidence score
            
        Returns:
            Tracking result
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            tracking = phase3_runner.track_step_execution(
                conversation_id, step_number, step_data, result, confidence
            )
            
            return tracking
        except Exception as e:
            self.logger.error(f"Error tracking step execution: {e}")
            return {"error": str(e)}

    # ========================================================================
    # Execution Analytics
    # ========================================================================

    def get_execution_status(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get current execution status.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            Execution status
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            return phase3_runner.get_execution_status()
        except Exception as e:
            self.logger.error(f"Error getting execution status: {e}")
            return {"error": str(e)}

    def get_execution_summary(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get execution summary.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            Execution summary
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            return phase3_runner.get_execution_summary()
        except Exception as e:
            self.logger.error(f"Error getting execution summary: {e}")
            return {"error": str(e)}

    def get_execution_history(self, test_case_id: int) -> List[Dict[str, Any]]:
        """
        Get execution history.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            Execution history
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            return phase3_runner.get_execution_history()
        except Exception as e:
            self.logger.error(f"Error getting execution history: {e}")
            return []

    def get_errors_encountered(self, test_case_id: int) -> List[Dict[str, Any]]:
        """
        Get errors encountered during execution.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            List of errors
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            return phase3_runner.get_errors_encountered()
        except Exception as e:
            self.logger.error(f"Error getting errors: {e}")
            return []

    def get_recovery_attempts(self, test_case_id: int) -> List[Dict[str, Any]]:
        """
        Get recovery attempts.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            List of recovery attempts
        """
        try:
            phase3_runner = self.phase3_runners.get(test_case_id)
            if not phase3_runner:
                raise ValueError(f"No Phase 3 runner for test {test_case_id}")
            
            return phase3_runner.get_recovery_attempts()
        except Exception as e:
            self.logger.error(f"Error getting recovery attempts: {e}")
            return []

    # ========================================================================
    # Phase 3 Status
    # ========================================================================

    def is_phase3_enabled(self) -> bool:
        """
        Check if Phase 3 is enabled.
        
        Returns:
            True if Phase 3 is available
        """
        return len(self.phase3_runners) > 0

    def get_phase3_status(self) -> Dict[str, Any]:
        """
        Get Phase 3 integration status.
        
        Returns:
            Phase 3 status information
        """
        return {
            "enabled": True,
            "active_runners": len(self.phase3_runners),
            "services": {
                "state_machine": "ready",
                "error_recovery_agent": "ready",
                "conversation_manager": "ready",
            },
        }
