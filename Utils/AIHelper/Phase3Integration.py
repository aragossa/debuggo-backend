"""
Phase 3 Integration for AIHelper

Integrates Phase 3 planning, conversation, and error recovery services
with AIHelper to enhance test generation with reasoning and planning.

Features:
- Use planning output to guide Gemini prompts
- Maintain conversation context across turns
- Track reasoning traces for debugging
- Implement error recovery strategies
- Manage execution plans
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from auroqa.Services.PlanningAgent import PlanningAgent
from auroqa.Services.ConversationManager import ConversationManager, ConversationTurn
from auroqa.Services.ToolRegistry import ToolRegistry
from auroqa.Services.TestGenerationStateMachine import TestGenerationStateMachine, State, Event
from auroqa.Services.ErrorRecoveryAgent import ErrorRecoveryAgent

logger = logging.getLogger(__name__)


class Phase3AIHelper:
    """
    Integrates Phase 3 services with AIHelper for enhanced test generation.
    
    Provides:
    - Planning-guided prompt generation
    - Multi-turn reasoning conversations
    - Tool-assisted generation
    - Error recovery and escalation
    - Execution tracking
    """

    def __init__(self):
        """Initialize Phase 3 integration services."""
        self.planning_agent = PlanningAgent()
        self.conversation_manager = ConversationManager()
        self.tool_registry = ToolRegistry()
        self.error_recovery_agent = ErrorRecoveryAgent()
        self.state_machines: Dict[int, TestGenerationStateMachine] = {}
        self.logger = logging.getLogger(__name__)

    # ========================================================================
    # Planning Integration
    # ========================================================================

    def get_planning_context(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get planning context for a test case to guide prompt generation.

        Args:
            test_case_id: Test case ID

        Returns:
            Planning context with analysis, plan, and recommendations
        """
        try:
            # Analyze test requirements
            analysis = self.planning_agent.analyze_test_requirements(test_case_id)

            # Identify dependencies
            dependencies = self.planning_agent.identify_dependencies(test_case_id)

            # Decompose into subtasks
            subtasks = self.planning_agent.decompose_into_subtasks(test_case_id)

            # Create execution plan
            plan = self.planning_agent.plan_execution_order(subtasks, dependencies)

            # Identify risks
            risks = self.planning_agent.identify_failure_points(plan)

            self.logger.info(
                f"✓ Planning context generated for test {test_case_id}: "
                f"complexity={analysis.complexity_score:.1f}, "
                f"subtasks={len(plan.subtasks)}, "
                f"risks={len(risks)}"
            )

            return {
                "test_case_id": test_case_id,
                "analysis": {
                    "title": analysis.title,
                    "complexity_score": analysis.complexity_score,
                    "objectives": analysis.objectives,
                    "preconditions": analysis.preconditions,
                    "estimated_steps": analysis.estimated_steps,
                },
                "plan": {
                    "overall_strategy": plan.overall_strategy,
                    "subtask_count": len(plan.subtasks),
                    "dependency_count": len(plan.dependencies),
                    "estimated_duration": plan.estimated_duration,
                    "confidence": plan.confidence,
                },
                "risks": [
                    {
                        "description": r.description,
                        "severity": r.severity,
                        "mitigation": r.mitigation_strategy,
                    }
                    for r in risks
                ],
            }
        except Exception as e:
            self.logger.error(f"Error getting planning context: {e}")
            return {"error": str(e)}

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
        try:
            context = self.get_planning_context(test_case_id)

            if "error" in context:
                return base_prompt

            # Build enhanced prompt
            enhanced = f"""{base_prompt}

## Test Planning Context

### Analysis
- **Complexity**: {context['analysis']['complexity_score']:.1f}/100
- **Objectives**: {', '.join(context['analysis']['objectives'])}
- **Preconditions**: {', '.join(context['analysis']['preconditions'])}
- **Estimated Steps**: {context['analysis']['estimated_steps']}

### Execution Plan
- **Strategy**: {context['plan']['overall_strategy']}
- **Subtasks**: {context['plan']['subtask_count']}
- **Dependencies**: {context['plan']['dependency_count']}
- **Confidence**: {context['plan']['confidence']:.2%}

### Risk Points
{chr(10).join([f"- **{r['description']}** (Severity: {r['severity']}) - Mitigation: {r['mitigation']}" for r in context['risks']])}

Use this planning context to:
1. Generate steps aligned with the overall strategy
2. Respect identified dependencies
3. Anticipate and mitigate risk points
4. Maintain confidence levels above {context['plan']['confidence']:.2%}
"""

            self.logger.info(f"✓ Prompt enhanced with planning context for test {test_case_id}")
            return enhanced

        except Exception as e:
            self.logger.error(f"Error enhancing prompt: {e}")
            return base_prompt

    # ========================================================================
    # Conversation Management
    # ========================================================================

    def start_reasoning_conversation(
        self, test_case_id: int, overall_strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start a multi-turn reasoning conversation for test generation.

        Args:
            test_case_id: Test case ID
            overall_strategy: Optional strategy description

        Returns:
            Conversation details
        """
        try:
            conversation = self.conversation_manager.start_conversation(
                test_case_id=test_case_id, overall_strategy=overall_strategy
            )

            self.logger.info(
                f"✓ Reasoning conversation started for test {test_case_id}: "
                f"conversation_id={conversation.id}"
            )

            return {
                "conversation_id": conversation.id,
                "test_case_id": conversation.test_case_id,
                "status": conversation.status,
                "overall_strategy": conversation.overall_strategy,
            }
        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            return {"error": str(e)}

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
        Add a turn to the reasoning conversation (ReAct pattern).

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
        try:
            conversation = self.conversation_manager.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            turn = ConversationTurn(
                turn_number=len(conversation.turns) + 1,
                thought=thought,
                action=action,
                observation=observation,
                tool_used=tool_used,
                tool_params=tool_params,
                confidence=confidence,
            )

            self.conversation_manager.add_turn(conversation, turn)

            self.logger.info(
                f"✓ Turn {turn.turn_number} added to conversation {conversation_id}: "
                f"tool={tool_used}, confidence={confidence:.2f}"
            )

            return {
                "turn_number": turn.turn_number,
                "conversation_id": conversation_id,
                "confidence": confidence,
            }
        except Exception as e:
            self.logger.error(f"Error adding reasoning turn: {e}")
            return {"error": str(e)}

    def get_conversation_context(self, conversation_id: int) -> Dict[str, Any]:
        """
        Extract context from conversation for next turn.

        Args:
            conversation_id: Conversation ID

        Returns:
            Context for next turn
        """
        try:
            conversation = self.conversation_manager.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            context = self.conversation_manager.extract_context(conversation)

            self.logger.info(
                f"✓ Context extracted from conversation {conversation_id}: "
                f"turns={context['turn_count']}, "
                f"avg_confidence={context['average_confidence']:.2f}"
            )

            return context
        except Exception as e:
            self.logger.error(f"Error extracting conversation context: {e}")
            return {"error": str(e)}

    def get_reasoning_trace(self, conversation_id: int) -> str:
        """
        Get formatted reasoning trace for debugging.

        Args:
            conversation_id: Conversation ID

        Returns:
            Formatted reasoning trace
        """
        try:
            conversation = self.conversation_manager.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            trace = self.conversation_manager.generate_reasoning_trace(conversation)

            self.logger.info(f"✓ Reasoning trace generated for conversation {conversation_id}")

            return trace
        except Exception as e:
            self.logger.error(f"Error generating reasoning trace: {e}")
            return f"Error: {str(e)}"

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
        try:
            result = self.tool_registry.execute_tool(tool_name, params)

            self.logger.info(
                f"✓ Tool executed: {tool_name}, "
                f"success={result.get('success')}, "
                f"time={result.get('execution_time_ms', 0):.1f}ms"
            )

            return result
        except Exception as e:
            self.logger.error(f"Error executing tool: {e}")
            return {"success": False, "error": str(e)}

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools.

        Returns:
            List of tool definitions
        """
        try:
            tools = self.tool_registry.get_available_tools()
            self.logger.info(f"✓ Retrieved {len(tools)} available tools")
            return tools
        except Exception as e:
            self.logger.error(f"Error getting available tools: {e}")
            return []

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
        try:
            machine = TestGenerationStateMachine(test_case_id=test_case_id)
            self.state_machines[test_case_id] = machine

            ctx = machine.get_context()
            self.logger.info(
                f"✓ State machine created for test {test_case_id}: "
                f"state={machine.state.value}"
            )

            return {
                "test_case_id": test_case_id,
                "state": machine.state.value,
                "step_number": ctx.step_number,
                "total_steps": ctx.total_steps,
                "confidence": ctx.confidence,
            }
        except Exception as e:
            self.logger.error(f"Error creating state machine: {e}")
            return {"error": str(e)}

    def transition_state(self, test_case_id: int, event: str) -> Dict[str, Any]:
        """
        Transition state machine to next state.

        Args:
            test_case_id: Test case ID
            event: Event to trigger transition

        Returns:
            Updated state machine details
        """
        try:
            machine = self.state_machines.get(test_case_id)
            if not machine:
                raise ValueError(f"State machine for test {test_case_id} not found")

            # Get event enum
            event_enum = Event[event.upper()]

            # Transition
            success = machine.transition(event_enum)
            if not success:
                raise ValueError(f"Invalid transition from {machine.state.value} with event {event}")

            ctx = machine.get_context()
            self.logger.info(
                f"✓ State transitioned for test {test_case_id}: "
                f"{machine.context.previous_state.value} → {machine.state.value}"
            )

            return {
                "test_case_id": test_case_id,
                "state": machine.state.value,
                "step_number": ctx.step_number,
                "total_steps": ctx.total_steps,
                "confidence": ctx.confidence,
                "error_count": ctx.error_count,
            }
        except Exception as e:
            self.logger.error(f"Error transitioning state: {e}")
            return {"error": str(e)}

    def get_state_machine_status(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get current state machine status.

        Args:
            test_case_id: Test case ID

        Returns:
            State machine status
        """
        try:
            machine = self.state_machines.get(test_case_id)
            if not machine:
                raise ValueError(f"State machine for test {test_case_id} not found")

            ctx = machine.get_context()
            return {
                "test_case_id": test_case_id,
                "state": machine.state.value,
                "step_number": ctx.step_number,
                "total_steps": ctx.total_steps,
                "confidence": ctx.confidence,
                "error_count": ctx.error_count,
                "retry_count": ctx.retry_count,
                "is_complete": machine.is_complete(),
                "is_error": machine.is_error(),
            }
        except Exception as e:
            self.logger.error(f"Error getting state machine status: {e}")
            return {"error": str(e)}

    # ========================================================================
    # Error Recovery
    # ========================================================================

    def handle_generation_error(
        self, test_case_id: int, failure: Dict[str, Any], step_context: Optional[Dict] = None
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
        try:
            # Detect and analyze error
            if not self.error_recovery_agent.detect_failure(failure):
                return {"status": "no_error"}

            analysis = self.error_recovery_agent.analyze_root_cause(failure, step_context)

            # Suggest recovery strategy
            strategy = self.error_recovery_agent.suggest_recovery_strategy(analysis)

            self.logger.info(
                f"✓ Error analyzed for test {test_case_id}: "
                f"type={analysis.error_type.value}, "
                f"severity={analysis.severity}, "
                f"strategy={strategy.value}"
            )

            return {
                "error_type": analysis.error_type.value,
                "error_message": analysis.error_message,
                "root_cause": analysis.root_cause,
                "severity": analysis.severity,
                "suggested_strategy": strategy.value,
                "suggested_strategies": [s.value for s in analysis.suggested_strategies],
            }
        except Exception as e:
            self.logger.error(f"Error handling generation error: {e}")
            return {"error": str(e)}

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
        try:
            # Analyze error
            failure = {"error": error_type}
            analysis = self.error_recovery_agent.analyze_root_cause(failure)

            # Get strategy enum
            from Services.ErrorRecoveryAgent import RecoveryStrategy

            strategy = RecoveryStrategy[recovery_strategy.upper()]

            # Implement recovery
            result = self.error_recovery_agent.implement_recovery(
                test_case_id, analysis, strategy
            )

            self.logger.info(
                f"✓ Error recovery implemented for test {test_case_id}: "
                f"strategy={strategy.value}, "
                f"success={result['success']}"
            )

            return result
        except Exception as e:
            self.logger.error(f"Error implementing recovery: {e}")
            return {"success": False, "error": str(e)}

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
        try:
            self.logger.info(f"🚀 Starting full generation workflow for test {test_case_id}")

            # Step 1: Create state machine
            sm_result = self.create_generation_state_machine(test_case_id)
            if "error" in sm_result:
                return sm_result

            # Step 2: Get planning context
            planning_context = self.get_planning_context(test_case_id)
            if "error" in planning_context:
                return planning_context

            # Step 3: Start reasoning conversation
            conv_result = self.start_reasoning_conversation(
                test_case_id, planning_context["plan"]["overall_strategy"]
            )
            if "error" in conv_result:
                return conv_result

            # Step 4: Transition to ANALYZE state
            self.transition_state(test_case_id, "analyze")

            # Step 5: Transition to PLAN state
            self.transition_state(test_case_id, "plan")

            # Step 6: Transition to GENERATE state
            self.transition_state(test_case_id, "generate")

            self.logger.info(
                f"✓ Full generation workflow completed for test {test_case_id}: "
                f"planning_done, conversation_started, state_machine_ready"
            )

            return {
                "status": "success",
                "test_case_id": test_case_id,
                "state_machine": sm_result,
                "planning_context": planning_context,
                "conversation": conv_result,
                "next_state": "GENERATE",
            }
        except Exception as e:
            self.logger.error(f"Error executing workflow: {e}")
            return {"status": "error", "error": str(e)}

    def get_workflow_summary(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get summary of workflow execution.

        Args:
            test_case_id: Test case ID

        Returns:
            Workflow summary
        """
        try:
            machine = self.state_machines.get(test_case_id)
            if not machine:
                return {"error": "State machine not found"}

            summary = machine.get_summary()

            self.logger.info(
                f"✓ Workflow summary retrieved for test {test_case_id}: "
                f"state={summary['current_state']}, "
                f"steps={summary['step_number']}/{summary['total_steps']}"
            )

            return summary
        except Exception as e:
            self.logger.error(f"Error getting workflow summary: {e}")
            return {"error": str(e)}
