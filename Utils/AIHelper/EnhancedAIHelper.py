"""
EnhancedAIHelper: AIHelper with Phase 3 Integration

Wraps AIHelper with Phase 3 services for:
- Planning-guided test generation
- Multi-turn reasoning conversations
- Tool-assisted generation
- Error recovery and escalation
- Execution tracking

Maintains backward compatibility with existing AIHelper.
"""

import logging
from typing import Dict, Any, Optional, List
from auroqa.Utils.AIHelper.AIHelper import AIHelper
from auroqa.Utils.AIHelper.Phase3Integration import Phase3AIHelper

logger = logging.getLogger(__name__)


class EnhancedAIHelper(AIHelper):
    """
    Enhanced AIHelper with Phase 3 integration.
    
    Extends AIHelper with planning, reasoning, and error recovery capabilities
    while maintaining full backward compatibility.
    
    Usage:
        helper = EnhancedAIHelper()
        
        # Use like regular AIHelper
        steps = helper.analyze_screenshot(image_path, test_case_id)
        
        # Or use Phase 3 features
        planning = helper.get_planning_context(test_case_id)
        enhanced_prompt = helper.enhance_prompt_with_planning(prompt, test_case_id)
    """

    def __init__(self):
        """Initialize EnhancedAIHelper with Phase 3 integration."""
        super().__init__()
        self.phase3 = Phase3AIHelper()
        self.logger = logging.getLogger(__name__)
        self.logger.info("✓ EnhancedAIHelper initialized with Phase 3 integration")

    # ========================================================================
    # Planning Integration
    # ========================================================================

    def get_planning_context(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get planning context for a test case.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            Planning context with analysis, plan, and risks
        """
        return self.phase3.get_planning_context(test_case_id)

    def enhance_prompt_with_planning(
        self, base_prompt: str, test_case_id: int
    ) -> str:
        """
        Enhance Gemini prompt with planning context.
        
        Args:
            base_prompt: Original prompt
            test_case_id: Test case ID
            
        Returns:
            Enhanced prompt with planning guidance
        """
        return self.phase3.enhance_prompt_with_planning(base_prompt, test_case_id)

    # ========================================================================
    # Conversation Management
    # ========================================================================

    def start_reasoning_conversation(
        self, test_case_id: int, overall_strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start a multi-turn reasoning conversation.
        
        Args:
            test_case_id: Test case ID
            overall_strategy: Optional strategy description
            
        Returns:
            Conversation details
        """
        return self.phase3.start_reasoning_conversation(test_case_id, overall_strategy)

    def add_reasoning_turn(
        self,
        conversation_id: int,
        thought: str,
        action: str,
        observation: str,
        tool_used: Optional[str] = None,
        tool_params: Optional[Dict] = None,
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Add a turn to the reasoning conversation.
        
        Args:
            conversation_id: Conversation ID
            thought: AI's reasoning
            action: Action to take
            observation: Result of action
            tool_used: Optional tool used
            tool_params: Optional tool parameters
            confidence: Confidence score
            
        Returns:
            Turn details
        """
        return self.phase3.add_reasoning_turn(
            conversation_id, thought, action, observation, tool_used, tool_params, confidence
        )

    def get_conversation_context(self, conversation_id: int) -> Dict[str, Any]:
        """
        Extract context from conversation for next turn.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Context for next turn
        """
        return self.phase3.get_conversation_context(conversation_id)

    def get_reasoning_trace(self, conversation_id: int) -> str:
        """
        Get formatted reasoning trace for debugging.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Formatted reasoning trace
        """
        return self.phase3.get_reasoning_trace(conversation_id)

    # ========================================================================
    # Tool Integration
    # ========================================================================

    def execute_generation_tool(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool for test generation.
        
        Args:
            tool_name: Tool name
            params: Tool parameters
            
        Returns:
            Tool execution result
        """
        return self.phase3.execute_generation_tool(tool_name, params)

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools.
        
        Returns:
            List of tool definitions
        """
        return self.phase3.get_available_tools()

    # ========================================================================
    # State Machine Management
    # ========================================================================

    def create_generation_state_machine(self, test_case_id: int) -> Dict[str, Any]:
        """
        Create a state machine for test generation workflow.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            State machine details
        """
        return self.phase3.create_generation_state_machine(test_case_id)

    def transition_state(self, test_case_id: int, event: str) -> Dict[str, Any]:
        """
        Transition state machine to next state.
        
        Args:
            test_case_id: Test case ID
            event: Event to trigger transition
            
        Returns:
            Updated state machine details
        """
        return self.phase3.transition_state(test_case_id, event)

    def get_state_machine_status(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get current state machine status.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            State machine status
        """
        return self.phase3.get_state_machine_status(test_case_id)

    # ========================================================================
    # Error Recovery
    # ========================================================================

    def handle_generation_error(
        self,
        test_case_id: int,
        failure: Dict[str, Any],
        step_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Handle generation error with recovery strategies.
        
        Args:
            test_case_id: Test case ID
            failure: Failure details
            step_context: Optional step context
            
        Returns:
            Error analysis and recovery recommendation
        """
        return self.phase3.handle_generation_error(test_case_id, failure, step_context)

    def implement_error_recovery(
        self, test_case_id: int, error_type: str, recovery_strategy: str
    ) -> Dict[str, Any]:
        """
        Implement error recovery strategy.
        
        Args:
            test_case_id: Test case ID
            error_type: Error type
            recovery_strategy: Recovery strategy
            
        Returns:
            Recovery result
        """
        return self.phase3.implement_error_recovery(
            test_case_id, error_type, recovery_strategy
        )

    # ========================================================================
    # Workflow Management
    # ========================================================================

    def execute_full_generation_workflow(
        self, test_case_id: int, description: str
    ) -> Dict[str, Any]:
        """
        Execute full test generation workflow with planning and reasoning.
        
        Args:
            test_case_id: Test case ID
            description: Test description
            
        Returns:
            Workflow execution result
        """
        return self.phase3.execute_full_generation_workflow(test_case_id, description)

    def get_workflow_summary(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get summary of workflow execution.
        
        Args:
            test_case_id: Test case ID
            
        Returns:
            Workflow summary
        """
        return self.phase3.get_workflow_summary(test_case_id)

    # ========================================================================
    # Enhanced Analysis Methods
    # ========================================================================

    def analyze_screenshot_with_planning(
        self, image_path: str, test_case_id: int
    ) -> Dict[str, Any]:
        """
        Analyze screenshot with planning guidance.
        
        Combines regular screenshot analysis with Phase 3 planning context
        for more intelligent test generation.
        
        Args:
            image_path: Path to screenshot
            test_case_id: Test case ID
            
        Returns:
            Analysis result with planning context
        """
        try:
            # Get planning context
            planning = self.get_planning_context(test_case_id)
            
            # Analyze screenshot (parent method)
            analysis = self.analyze_screenshot(image_path, test_case_id)
            
            # Enhance with planning
            analysis["planning_context"] = planning
            
            self.logger.info(
                f"✓ Screenshot analyzed with planning: "
                f"test_id={test_case_id}, "
                f"complexity={planning.get('analysis', {}).get('complexity_score', 'N/A')}"
            )
            
            return analysis
        except Exception as e:
            self.logger.error(f"Error analyzing screenshot with planning: {e}")
            # Fall back to regular analysis
            return self.analyze_screenshot(image_path, test_case_id)

    def analyze_text_with_planning(
        self, description: str, test_case_id: int
    ) -> Dict[str, Any]:
        """
        Analyze text description with planning guidance.
        
        Args:
            description: Test description
            test_case_id: Test case ID
            
        Returns:
            Analysis result with planning context
        """
        try:
            # Get planning context
            planning = self.get_planning_context(test_case_id)
            
            # Analyze text (parent method)
            analysis = self.analyze_text(description, test_case_id)
            
            # Enhance with planning
            analysis["planning_context"] = planning
            
            self.logger.info(
                f"✓ Text analyzed with planning: "
                f"test_id={test_case_id}, "
                f"complexity={planning.get('analysis', {}).get('complexity_score', 'N/A')}"
            )
            
            return analysis
        except Exception as e:
            self.logger.error(f"Error analyzing text with planning: {e}")
            # Fall back to regular analysis
            return self.analyze_text(description, test_case_id)

    # ========================================================================
    # Phase 3 Status
    # ========================================================================

    def is_phase3_enabled(self) -> bool:
        """
        Check if Phase 3 is enabled.
        
        Returns:
            True if Phase 3 is available
        """
        return self.phase3 is not None

    def get_phase3_status(self) -> Dict[str, Any]:
        """
        Get Phase 3 integration status.
        
        Returns:
            Phase 3 status information
        """
        return {
            "enabled": self.is_phase3_enabled(),
            "services": {
                "planning_agent": "ready",
                "conversation_manager": "ready",
                "tool_registry": "ready",
                "error_recovery_agent": "ready",
                "state_machine": "ready",
            },
        }
