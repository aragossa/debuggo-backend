"""
ReasoningCollector Service

Collects and manages AI reasoning, planning, and thought process data during test generation.
Stores reasoning data in Redis for real-time access and provides structured reasoning information
about how AI splits test cases and generates steps.
"""

import json
import redis
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class PhaseStatus(Enum):
    """Status of a generation phase"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Phase:
    """Represents a generation phase"""
    name: str
    status: str
    description: Optional[str] = None
    details: Optional[List[str]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class TestSplit:
    """Represents how the test case is split into steps"""
    total_steps_planned: int
    current_step_number: int
    phases: Optional[List[str]] = None
    strategy: Optional[str] = None


@dataclass
class CurrentStep:
    """Represents the current step being generated"""
    step_number: int
    action: str
    description: Optional[str] = None
    reasoning: Optional[str] = None
    element_info: Optional[str] = None


@dataclass
class TimelineItem:
    """Represents a timeline event"""
    timestamp: str
    message: str
    type: str = "info"  # info, success, error, warning


class ReasoningCollector:
    """
    Collects and manages AI reasoning data during test generation.
    
    Features:
    - Tracks test case splitting strategy
    - Records AI thoughts and reasoning
    - Monitors generation phases
    - Tracks current step generation
    - Maintains timeline of events
    - Provides statistics
    """

    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0):
        """Initialize ReasoningCollector with Redis connection"""
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.logger = logging.getLogger(__name__)

    def _get_reasoning_key(self, test_case_id: int) -> str:
        """Get Redis key for reasoning data"""
        return f"reasoning:{test_case_id}"

    def _get_reasoning_data(self, test_case_id: int) -> Dict[str, Any]:
        """Get current reasoning data from Redis"""
        key = self._get_reasoning_key(test_case_id)
        data = self.redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return self._create_empty_reasoning()
        return self._create_empty_reasoning()

    def _create_empty_reasoning(self) -> Dict[str, Any]:
        """Create empty reasoning structure"""
        return {
            "overall_status": None,
            "thoughts": [],
            "test_split": None,
            "phases": [],
            "current_step": None,
            "timeline": [],
            "statistics": {
                "total_steps_generated": 0,
                "total_steps_planned": 0,
                "generation_start_time": None,
                "generation_end_time": None,
                "total_duration_seconds": 0,
                "average_step_duration_ms": 0
            }
        }

    def _save_reasoning_data(self, test_case_id: int, data: Dict[str, Any]) -> None:
        """Save reasoning data to Redis"""
        key = self._get_reasoning_key(test_case_id)
        try:
            self.redis_client.setex(
                key,
                86400,  # 24 hour expiry
                json.dumps(data)
            )
        except Exception as e:
            self.logger.error(f"Error saving reasoning data: {e}")

    def start_generation(self, test_case_id: int, test_name: str, test_description: str) -> None:
        """
        Initialize reasoning collection for a new test case generation.
        
        Args:
            test_case_id: ID of the test case being generated
            test_name: Name of the test case
            test_description: Description of the test case
        """
        data = self._create_empty_reasoning()
        data["overall_status"] = f"Starting generation for: {test_name}"
        data["statistics"]["generation_start_time"] = datetime.now().isoformat()
        
        self._add_timeline_event(
            test_case_id,
            f"Generation started for test: {test_name}",
            "info"
        )
        
        self._save_reasoning_data(test_case_id, data)
        self.logger.info(f"Started reasoning collection for test case {test_case_id}")

    def add_thought(self, test_case_id: int, thought: str) -> None:
        """
        Add an AI thought/reasoning to the collection.
        
        Args:
            test_case_id: ID of the test case
            thought: The AI thought or reasoning
        """
        data = self._get_reasoning_data(test_case_id)
        if thought not in data["thoughts"]:
            data["thoughts"].append(thought)
        self._save_reasoning_data(test_case_id, data)

    def set_test_split_strategy(
        self,
        test_case_id: int,
        total_steps: int,
        phases: Optional[List[str]] = None,
        strategy: Optional[str] = None
    ) -> None:
        """
        Set the test case split strategy.
        
        Args:
            test_case_id: ID of the test case
            total_steps: Total number of steps planned
            phases: List of test phases
            strategy: Description of the splitting strategy
        """
        data = self._get_reasoning_data(test_case_id)
        data["test_split"] = {
            "total_steps_planned": total_steps,
            "current_step_number": 0,
            "phases": phases or [],
            "strategy": strategy
        }
        data["statistics"]["total_steps_planned"] = total_steps
        
        self._add_timeline_event(
            test_case_id,
            f"Test split into {total_steps} steps with strategy: {strategy or 'default'}",
            "info"
        )
        
        self._save_reasoning_data(test_case_id, data)
        self.logger.info(f"Set test split strategy for {test_case_id}: {total_steps} steps")

    def start_phase(self, test_case_id: int, phase_name: str, description: Optional[str] = None) -> None:
        """
        Mark the start of a generation phase.
        
        Args:
            test_case_id: ID of the test case
            phase_name: Name of the phase
            description: Description of what this phase does
        """
        data = self._get_reasoning_data(test_case_id)
        
        # Mark previous phase as completed if it was in progress
        for phase in data["phases"]:
            if phase["status"] == PhaseStatus.IN_PROGRESS.value:
                phase["status"] = PhaseStatus.COMPLETED.value
                phase["end_time"] = datetime.now().isoformat()
        
        # Add new phase
        new_phase = {
            "name": phase_name,
            "status": PhaseStatus.IN_PROGRESS.value,
            "description": description,
            "details": [],
            "start_time": datetime.now().isoformat(),
            "end_time": None
        }
        data["phases"].append(new_phase)
        
        self._add_timeline_event(
            test_case_id,
            f"Started phase: {phase_name}",
            "info"
        )
        
        self._save_reasoning_data(test_case_id, data)
        self.logger.info(f"Started phase '{phase_name}' for test case {test_case_id}")

    def add_phase_detail(self, test_case_id: int, detail: str) -> None:
        """
        Add a detail to the current phase.
        
        Args:
            test_case_id: ID of the test case
            detail: Detail message to add
        """
        data = self._get_reasoning_data(test_case_id)
        
        # Find the current phase
        for phase in data["phases"]:
            if phase["status"] == PhaseStatus.IN_PROGRESS.value:
                if "details" not in phase:
                    phase["details"] = []
                phase["details"].append(detail)
                break
        
        self._save_reasoning_data(test_case_id, data)

    def complete_phase(self, test_case_id: int, phase_name: Optional[str] = None) -> None:
        """
        Mark a phase as completed.
        
        Args:
            test_case_id: ID of the test case
            phase_name: Name of the phase to complete (if None, completes current phase)
        """
        data = self._get_reasoning_data(test_case_id)
        
        for phase in data["phases"]:
            if phase_name is None or phase["name"] == phase_name:
                if phase["status"] == PhaseStatus.IN_PROGRESS.value:
                    phase["status"] = PhaseStatus.COMPLETED.value
                    phase["end_time"] = datetime.now().isoformat()
                    
                    self._add_timeline_event(
                        test_case_id,
                        f"Completed phase: {phase['name']}",
                        "success"
                    )
                    break
        
        self._save_reasoning_data(test_case_id, data)

    def set_current_step(
        self,
        test_case_id: int,
        step_number: int,
        action: str,
        description: Optional[str] = None,
        reasoning: Optional[str] = None,
        element_info: Optional[str] = None
    ) -> None:
        """
        Set the current step being generated.
        
        Args:
            test_case_id: ID of the test case
            step_number: Step number
            action: Action being performed
            description: Step description
            reasoning: Why this step is needed
            element_info: Information about the target element
        """
        data = self._get_reasoning_data(test_case_id)
        
        data["current_step"] = {
            "step_number": step_number,
            "action": action,
            "description": description,
            "reasoning": reasoning,
            "element_info": element_info
        }
        
        # Update test split progress
        if data["test_split"]:
            data["test_split"]["current_step_number"] = step_number
        
        # Update statistics
        data["statistics"]["total_steps_generated"] = step_number
        
        self._add_timeline_event(
            test_case_id,
            f"Generating step {step_number}: {action}",
            "info"
        )
        
        self._save_reasoning_data(test_case_id, data)

    def _add_timeline_event(
        self,
        test_case_id: int,
        message: str,
        event_type: str = "info"
    ) -> None:
        """
        Add an event to the timeline.
        
        Args:
            test_case_id: ID of the test case
            message: Event message
            event_type: Type of event (info, success, error, warning)
        """
        data = self._get_reasoning_data(test_case_id)
        
        timeline_item = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "type": event_type
        }
        
        data["timeline"].append(timeline_item)
        
        # Keep only last 50 timeline items
        if len(data["timeline"]) > 50:
            data["timeline"] = data["timeline"][-50:]
        
        self._save_reasoning_data(test_case_id, data)

    def set_overall_status(self, test_case_id: int, status: str) -> None:
        """
        Set the overall generation status message.
        
        Args:
            test_case_id: ID of the test case
            status: Status message
        """
        data = self._get_reasoning_data(test_case_id)
        data["overall_status"] = status
        self._save_reasoning_data(test_case_id, data)

    def complete_generation(self, test_case_id: int, total_steps: int) -> None:
        """
        Mark generation as complete.
        
        Args:
            test_case_id: ID of the test case
            total_steps: Total number of steps generated
        """
        data = self._get_reasoning_data(test_case_id)
        
        # Mark any in-progress phase as completed
        for phase in data["phases"]:
            if phase["status"] == PhaseStatus.IN_PROGRESS.value:
                phase["status"] = PhaseStatus.COMPLETED.value
                phase["end_time"] = datetime.now().isoformat()
        
        # Update statistics
        end_time = datetime.now()
        start_time_str = data["statistics"]["generation_start_time"]
        if start_time_str:
            start_time = datetime.fromisoformat(start_time_str)
            duration = (end_time - start_time).total_seconds()
            data["statistics"]["total_duration_seconds"] = duration
            if total_steps > 0:
                data["statistics"]["average_step_duration_ms"] = (duration * 1000) / total_steps
        
        data["statistics"]["generation_end_time"] = end_time.isoformat()
        data["statistics"]["total_steps_generated"] = total_steps
        data["overall_status"] = f"✅ Generation complete: {total_steps} steps generated"
        
        self._add_timeline_event(
            test_case_id,
            f"Generation complete: {total_steps} steps generated",
            "success"
        )
        
        self._save_reasoning_data(test_case_id, data)
        self.logger.info(f"Completed generation for test case {test_case_id}: {total_steps} steps")

    def get_reasoning_data(self, test_case_id: int) -> Dict[str, Any]:
        """
        Get all reasoning data for a test case.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            Dictionary containing all reasoning data
        """
        return self._get_reasoning_data(test_case_id)

    def clear_reasoning(self, test_case_id: int) -> None:
        """
        Clear reasoning data for a test case.
        
        Args:
            test_case_id: ID of the test case
        """
        key = self._get_reasoning_key(test_case_id)
        self.redis_client.delete(key)
        self.logger.info(f"Cleared reasoning data for test case {test_case_id}")
