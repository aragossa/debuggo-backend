"""
PlanningCollector Service

Collects and manages AI planning, reasoning, and error recovery data during test generation.
Stores planning data in Redis for real-time access and provides structured information about:
- Strategic planning (requirement analysis, decomposition, dependencies, risk assessment)
- Multi-turn reasoning (ReAct pattern, tool usage, reasoning traces)
- Error recovery (failure analysis, recovery strategies)
"""

import json
import redis
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class PlanningCollector:
    """
    Collects and manages AI planning and reasoning data during test generation.
    
    Features:
    - Tracks strategic planning decisions
    - Records multi-turn reasoning with ReAct pattern
    - Logs error recovery attempts and strategies
    - Stores data in Redis for fast access
    """

    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0):
        """Initialize PlanningCollector with Redis connection"""
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.logger = logging.getLogger(__name__)

    def _get_planning_key(self, test_case_id: int) -> str:
        """Get Redis key for planning data"""
        return f"planning:{test_case_id}"

    def _get_planning_data(self, test_case_id: int) -> Dict[str, Any]:
        """Get current planning data from Redis"""
        key = self._get_planning_key(test_case_id)
        data = self.redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return self._create_empty_planning()
        return self._create_empty_planning()

    def _create_empty_planning(self) -> Dict[str, Any]:
        """Create empty planning structure"""
        return {
            "strategic_planning": {
                "requirement_analysis": None,
                "decomposition": None,
                "dependencies": None,
                "risk_assessment": None,
                "plan_summary": None
            },
            "multi_turn_reasoning": {
                "react_traces": [],
                "tool_usage": [],
                "reasoning_traces": [],
                "context_accumulation": None
            },
            "error_recovery": {
                "failure_analysis": None,
                "recovery_strategies": None,
                "recovery_stats": None
            }
        }

    def _save_planning_data(self, test_case_id: int, data: Dict[str, Any]) -> None:
        """Save planning data to Redis"""
        key = self._get_planning_key(test_case_id)
        try:
            self.redis_client.setex(
                key,
                86400,  # 24 hour expiry
                json.dumps(data)
            )
        except Exception as e:
            self.logger.error(f"Error saving planning data: {e}")

    # ==================== STRATEGIC PLANNING ====================

    def set_requirement_analysis(
        self,
        test_case_id: int,
        complexity_score: int,
        factors: List[str],
        description: Optional[str] = None
    ) -> None:
        """
        Set requirement analysis data.
        
        Args:
            test_case_id: ID of the test case
            complexity_score: Complexity score (0-100)
            factors: List of complexity factors
            description: Analysis description
        """
        data = self._get_planning_data(test_case_id)
        data["strategic_planning"]["requirement_analysis"] = {
            "complexity_score": complexity_score,
            "factors": factors,
            "description": description
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set requirement analysis for test case {test_case_id}: score={complexity_score}")

    def set_decomposition(
        self,
        test_case_id: int,
        strategy: str,
        subtasks: List[Dict[str, Any]]
    ) -> None:
        """
        Set decomposition and ordering strategy.
        
        Args:
            test_case_id: ID of the test case
            strategy: Description of decomposition strategy
            subtasks: List of subtasks with order
        """
        data = self._get_planning_data(test_case_id)
        data["strategic_planning"]["decomposition"] = {
            "strategy": strategy,
            "subtasks": subtasks
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set decomposition for test case {test_case_id}: {len(subtasks)} subtasks")

    def set_dependencies(
        self,
        test_case_id: int,
        data_dependencies: Optional[List[Dict[str, str]]] = None,
        state_dependencies: Optional[List[Dict[str, str]]] = None
    ) -> None:
        """
        Set dependency identification.
        
        Args:
            test_case_id: ID of the test case
            data_dependencies: List of data dependencies
            state_dependencies: List of state dependencies
        """
        data = self._get_planning_data(test_case_id)
        data["strategic_planning"]["dependencies"] = {
            "data_dependencies": data_dependencies or [],
            "state_dependencies": state_dependencies or []
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set dependencies for test case {test_case_id}")

    def set_risk_assessment(
        self,
        test_case_id: int,
        identified_risks: List[Dict[str, Any]]
    ) -> None:
        """
        Set risk assessment.
        
        Args:
            test_case_id: ID of the test case
            identified_risks: List of identified risks with severity and mitigation
        """
        data = self._get_planning_data(test_case_id)
        data["strategic_planning"]["risk_assessment"] = {
            "identified_risks": identified_risks
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set risk assessment for test case {test_case_id}: {len(identified_risks)} risks")

    def set_plan_summary(
        self,
        test_case_id: int,
        total_steps: int,
        estimated_duration: str,
        test_type: str,
        execution_plan: Optional[str] = None
    ) -> None:
        """
        Set completed plan summary.
        
        Args:
            test_case_id: ID of the test case
            total_steps: Total steps planned
            estimated_duration: Estimated duration
            test_type: Type of test (UI/API)
            execution_plan: Description of execution plan
        """
        data = self._get_planning_data(test_case_id)
        data["strategic_planning"]["plan_summary"] = {
            "total_steps": total_steps,
            "estimated_duration": estimated_duration,
            "test_type": test_type,
            "execution_plan": execution_plan
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set plan summary for test case {test_case_id}: {total_steps} steps")

    # ==================== MULTI-TURN REASONING ====================

    def add_react_trace(
        self,
        test_case_id: int,
        thought: str,
        action: str,
        action_params: Optional[Dict[str, Any]] = None,
        observation: Optional[str] = None,
        reflection: Optional[str] = None
    ) -> None:
        """
        Add a ReAct pattern trace (Thought → Action → Observation → Reflection).
        
        Args:
            test_case_id: ID of the test case
            thought: AI thought/reasoning
            action: Action taken
            action_params: Parameters for the action
            observation: Result of the action
            reflection: Reflection on the result
        """
        data = self._get_planning_data(test_case_id)
        trace = {
            "thought": thought,
            "action": action,
            "action_params": action_params,
            "observation": observation,
            "reflection": reflection,
            "timestamp": datetime.now().isoformat()
        }
        data["multi_turn_reasoning"]["react_traces"].append(trace)
        self._save_planning_data(test_case_id, data)

    def add_tool_usage(
        self,
        test_case_id: int,
        tool_name: str,
        description: str,
        status: str = "completed",
        result: Optional[str] = None
    ) -> None:
        """
        Add tool usage record.
        
        Args:
            test_case_id: ID of the test case
            tool_name: Name of the tool used
            description: Description of what the tool does
            status: Status of tool execution
            result: Result of tool execution
        """
        data = self._get_planning_data(test_case_id)
        tool = {
            "name": tool_name,
            "description": description,
            "status": status,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
        data["multi_turn_reasoning"]["tool_usage"].append(tool)
        self._save_planning_data(test_case_id, data)

    def add_reasoning_trace(
        self,
        test_case_id: int,
        message: str,
        trace_type: str = "info",
        details: Optional[str] = None
    ) -> None:
        """
        Add reasoning trace for debugging.
        
        Args:
            test_case_id: ID of the test case
            message: Trace message
            trace_type: Type of trace (info, success, error, warning)
            details: Additional details
        """
        data = self._get_planning_data(test_case_id)
        trace = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "type": trace_type,
            "details": details
        }
        data["multi_turn_reasoning"]["reasoning_traces"].append(trace)
        
        # Keep only last 100 traces
        if len(data["multi_turn_reasoning"]["reasoning_traces"]) > 100:
            data["multi_turn_reasoning"]["reasoning_traces"] = data["multi_turn_reasoning"]["reasoning_traces"][-100:]
        
        self._save_planning_data(test_case_id, data)

    def set_context_accumulation(
        self,
        test_case_id: int,
        context: str
    ) -> None:
        """
        Set accumulated context for multi-turn reasoning.
        
        Args:
            test_case_id: ID of the test case
            context: Accumulated context string
        """
        data = self._get_planning_data(test_case_id)
        data["multi_turn_reasoning"]["context_accumulation"] = context
        self._save_planning_data(test_case_id, data)

    # ==================== ERROR RECOVERY ====================

    def set_failure_analysis(
        self,
        test_case_id: int,
        failures: List[Dict[str, Any]],
        summary: Optional[str] = None
    ) -> None:
        """
        Set failure analysis.
        
        Args:
            test_case_id: ID of the test case
            failures: List of failures with analysis
            summary: Summary of failures
        """
        data = self._get_planning_data(test_case_id)
        data["error_recovery"]["failure_analysis"] = {
            "failures": failures,
            "summary": summary
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set failure analysis for test case {test_case_id}: {len(failures)} failures")

    def set_recovery_strategies(
        self,
        test_case_id: int,
        automated: Optional[List[Dict[str, Any]]] = None,
        escalation: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Set recovery strategies.
        
        Args:
            test_case_id: ID of the test case
            automated: List of automated recovery strategies
            escalation: List of escalation strategies
        """
        data = self._get_planning_data(test_case_id)
        data["error_recovery"]["recovery_strategies"] = {
            "automated": automated or [],
            "escalation": escalation or []
        }
        self._save_planning_data(test_case_id, data)
        self.logger.info(f"Set recovery strategies for test case {test_case_id}")

    def set_recovery_statistics(
        self,
        test_case_id: int,
        total_failures: int,
        automated_recoveries: int,
        escalations: int,
        recovery_rate: float
    ) -> None:
        """
        Set recovery statistics.
        
        Args:
            test_case_id: ID of the test case
            total_failures: Total number of failures
            automated_recoveries: Number of automated recoveries
            escalations: Number of escalations
            recovery_rate: Recovery rate percentage
        """
        data = self._get_planning_data(test_case_id)
        data["error_recovery"]["recovery_stats"] = {
            "total_failures": total_failures,
            "automated_recoveries": automated_recoveries,
            "escalations": escalations,
            "recovery_rate": recovery_rate
        }
        self._save_planning_data(test_case_id, data)

    def get_planning_data(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get all planning data for a test case.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            Dictionary containing all planning data
        """
        return self._get_planning_data(test_case_id)

    def clear_planning(self, test_case_id: int) -> None:
        """
        Clear planning data for a test case.
        
        Args:
            test_case_id: ID of the test case
        """
        key = self._get_planning_key(test_case_id)
        self.redis_client.delete(key)
        self.logger.info(f"Cleared planning data for test case {test_case_id}")
