"""
PlanningAgent: Analyzes test requirements and creates execution plans.

Responsibilities:
- Analyze test requirements and objectives
- Identify dependencies and preconditions
- Decompose complex tests into subtasks
- Plan optimal execution order
- Identify potential failure points and risks
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)


@dataclass
class Dependency:
    """Represents a dependency between test steps."""
    source_step: int
    target_step: int
    dependency_type: str  # 'data_dependency', 'state_dependency', 'timing_dependency'
    description: str


@dataclass
class SubTask:
    """Represents a sub-task in the execution plan."""
    task_id: int
    description: str
    steps: List[int]
    preconditions: List[str]
    expected_outcome: str
    estimated_duration: float


@dataclass
class RiskPoint:
    """Represents a potential failure point."""
    step_number: int
    risk_type: str  # 'element_not_found', 'timing', 'data_validation', 'navigation'
    severity: str  # 'low', 'medium', 'high'
    description: str
    mitigation_strategy: str


@dataclass
class TestAnalysis:
    """Analysis of test requirements."""
    test_case_id: int
    title: str
    description: str
    objectives: List[str]
    preconditions: List[str]
    expected_flow: str
    complexity_score: float  # 0-100
    estimated_steps: int


@dataclass
class ExecutionPlan:
    """Complete execution plan for a test."""
    test_case_id: int
    overall_strategy: str
    subtasks: List[SubTask]
    dependencies: List[Dependency]
    risk_points: List[RiskPoint]
    estimated_duration: float
    confidence: float
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class PlanningAgent:
    """Agent responsible for analyzing and planning test execution."""

    def __init__(self):
        self.system = System()
        self.logger = logging.getLogger(__name__)

    def analyze_test_requirements(self, test_case_id: int) -> TestAnalysis:
        """
        Analyze test case requirements and extract key information.

        Args:
            test_case_id: ID of the test case to analyze

        Returns:
            TestAnalysis object with extracted requirements
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get test case details
                    cur.execute("""
                        SELECT id, name, description, test_type
                        FROM test_cases
                        WHERE id = %s
                    """, (test_case_id,))
                    test_case = cur.fetchone()

                    if not test_case:
                        raise ValueError(f"Test case {test_case_id} not found")

                    test_id, title, description, test_type = test_case

                    # Get test steps to understand flow
                    cur.execute("""
                        SELECT COUNT(*), 
                               COUNT(DISTINCT action),
                               STRING_AGG(DISTINCT action, ', ')
                        FROM test_steps
                        WHERE test_case_id = %s
                    """, (test_case_id,))
                    step_count, action_count, actions = cur.fetchone()

                    # Analyze complexity
                    complexity_score = self._calculate_complexity(
                        step_count or 0,
                        action_count or 0,
                        test_type
                    )

                    # Extract objectives from description
                    objectives = self._extract_objectives(description or "")

                    analysis = TestAnalysis(
                        test_case_id=test_id,
                        title=title,
                        description=description or "",
                        objectives=objectives,
                        preconditions=self._extract_preconditions(description or ""),
                        expected_flow=actions or "Unknown",
                        complexity_score=complexity_score,
                        estimated_steps=step_count or 0
                    )

                    self.logger.info(
                        f"✓ Analyzed test {test_case_id}: "
                        f"complexity={complexity_score:.1f}, "
                        f"steps={step_count}, "
                        f"objectives={len(analysis.objectives)}"
                    )

                    return analysis

        except Exception as e:
            self.logger.error(f"Error analyzing test requirements: {e}")
            raise

    def identify_dependencies(self, test_case_id: int) -> List[Dependency]:
        """
        Identify dependencies between test steps.

        Args:
            test_case_id: ID of the test case

        Returns:
            List of Dependency objects
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get all test steps ordered by step number
                    cur.execute("""
                        SELECT id, step_number, action, value, description
                        FROM test_steps
                        WHERE test_case_id = %s
                        ORDER BY step_number
                    """, (test_case_id,))
                    steps = cur.fetchall()

                    dependencies = []

                    # Analyze step relationships
                    for i, step in enumerate(steps):
                        step_id, step_num, action, value, description = step

                        # Check for data dependencies (e.g., using values from previous steps)
                        if value and '%' in str(value):
                            # Variable reference - depends on earlier step
                            dependencies.append(Dependency(
                                source_step=step_num - 1 if step_num > 1 else 1,
                                target_step=step_num,
                                dependency_type='data_dependency',
                                description=f"Step {step_num} uses variable from earlier step"
                            ))

                        # Check for state dependencies
                        if action in ['click', 'submit', 'navigate']:
                            if i > 0:
                                dependencies.append(Dependency(
                                    source_step=steps[i - 1][1],
                                    target_step=step_num,
                                    dependency_type='state_dependency',
                                    description=f"Step {step_num} depends on state from step {steps[i - 1][1]}"
                                ))

                    self.logger.info(
                        f"✓ Identified {len(dependencies)} dependencies for test {test_case_id}"
                    )

                    return dependencies

        except Exception as e:
            self.logger.error(f"Error identifying dependencies: {e}")
            raise

    def decompose_into_subtasks(self, test_case_id: int) -> List[SubTask]:
        """
        Decompose test into logical subtasks.

        Args:
            test_case_id: ID of the test case

        Returns:
            List of SubTask objects
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get all test steps
                    cur.execute("""
                        SELECT id, step_number, action, description
                        FROM test_steps
                        WHERE test_case_id = %s
                        ORDER BY step_number
                    """, (test_case_id,))
                    steps = cur.fetchall()

                    subtasks = []
                    current_subtask_steps = []
                    current_action = None
                    task_id = 1

                    # Group steps into logical subtasks based on action patterns
                    for step_id, step_num, action, description in steps:
                        # Detect subtask boundaries (navigation, form submission, etc.)
                        if action in ['navigate', 'submit'] and current_subtask_steps:
                            # Create subtask for previous steps
                            subtask = SubTask(
                                task_id=task_id,
                                description=self._generate_subtask_description(
                                    current_subtask_steps, steps
                                ),
                                steps=current_subtask_steps.copy(),
                                preconditions=[],
                                expected_outcome=f"Complete steps {current_subtask_steps[0]}-{current_subtask_steps[-1]}",
                                estimated_duration=len(current_subtask_steps) * 0.5
                            )
                            subtasks.append(subtask)
                            current_subtask_steps = []
                            task_id += 1

                        current_subtask_steps.append(step_num)

                    # Add final subtask
                    if current_subtask_steps:
                        subtask = SubTask(
                            task_id=task_id,
                            description=self._generate_subtask_description(
                                current_subtask_steps, steps
                            ),
                            steps=current_subtask_steps,
                            preconditions=[],
                            expected_outcome=f"Complete steps {current_subtask_steps[0]}-{current_subtask_steps[-1]}",
                            estimated_duration=len(current_subtask_steps) * 0.5
                        )
                        subtasks.append(subtask)

                    self.logger.info(
                        f"✓ Decomposed test {test_case_id} into {len(subtasks)} subtasks"
                    )

                    return subtasks

        except Exception as e:
            self.logger.error(f"Error decomposing into subtasks: {e}")
            raise

    def plan_execution_order(self, subtasks: List[SubTask],
                            dependencies: List[Dependency]) -> ExecutionPlan:
        """
        Create optimal execution plan considering dependencies.

        Args:
            subtasks: List of subtasks
            dependencies: List of dependencies

        Returns:
            ExecutionPlan object
        """
        try:
            # Sort subtasks based on dependencies
            ordered_subtasks = self._topological_sort(subtasks, dependencies)

            # Calculate total estimated duration
            total_duration = sum(st.estimated_duration for st in ordered_subtasks)

            # Calculate confidence based on complexity
            confidence = self._calculate_plan_confidence(
                len(ordered_subtasks),
                len(dependencies)
            )

            plan = ExecutionPlan(
                test_case_id=0,  # Will be set by caller
                overall_strategy=self._generate_strategy(ordered_subtasks),
                subtasks=ordered_subtasks,
                dependencies=dependencies,
                risk_points=[],  # Will be populated by identify_failure_points
                estimated_duration=total_duration,
                confidence=confidence
            )

            self.logger.info(
                f"✓ Created execution plan: "
                f"{len(ordered_subtasks)} subtasks, "
                f"duration={total_duration:.1f}s, "
                f"confidence={confidence:.2f}"
            )

            return plan

        except Exception as e:
            self.logger.error(f"Error planning execution order: {e}")
            raise

    def identify_failure_points(self, plan: ExecutionPlan) -> List[RiskPoint]:
        """
        Identify potential failure points in the execution plan.

        Args:
            plan: ExecutionPlan object

        Returns:
            List of RiskPoint objects
        """
        risk_points = []

        try:
            # Analyze each subtask for risks
            for subtask in plan.subtasks:
                # High complexity = higher risk
                if len(subtask.steps) > 5:
                    risk_points.append(RiskPoint(
                        step_number=subtask.steps[0],
                        risk_type='complexity',
                        severity='medium',
                        description=f"Subtask has {len(subtask.steps)} steps",
                        mitigation_strategy="Break into smaller steps"
                    ))

                # Long estimated duration = timing risk
                if subtask.estimated_duration > 5:
                    risk_points.append(RiskPoint(
                        step_number=subtask.steps[0],
                        risk_type='timing',
                        severity='low',
                        description=f"Long estimated duration: {subtask.estimated_duration}s",
                        mitigation_strategy="Add explicit waits"
                    ))

            # Analyze dependencies for risks
            for dep in plan.dependencies:
                if dep.dependency_type == 'data_dependency':
                    risk_points.append(RiskPoint(
                        step_number=dep.target_step,
                        risk_type='data_validation',
                        severity='high',
                        description=f"Depends on data from step {dep.source_step}",
                        mitigation_strategy="Add validation step"
                    ))

            self.logger.info(
                f"✓ Identified {len(risk_points)} potential failure points"
            )

            return risk_points

        except Exception as e:
            self.logger.error(f"Error identifying failure points: {e}")
            return []

    def save_plan(self, test_case_id: int, plan: ExecutionPlan) -> int:
        """
        Save execution plan to database.

        Args:
            test_case_id: ID of the test case
            plan: ExecutionPlan object

        Returns:
            ID of saved plan
        """
        try:
            plan.test_case_id = test_case_id

            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO execution_plans
                        (test_case_id, plan_data, overall_strategy, subtasks, 
                         dependencies, risk_points, estimated_duration, confidence)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        test_case_id,
                        json.dumps(asdict(plan), default=str),
                        plan.overall_strategy,
                        json.dumps([asdict(st) for st in plan.subtasks], default=str),
                        json.dumps([asdict(d) for d in plan.dependencies], default=str),
                        json.dumps([asdict(rp) for rp in plan.risk_points], default=str),
                        plan.estimated_duration,
                        plan.confidence
                    ))
                    plan_id = cur.fetchone()[0]
                    conn.commit()

                    self.logger.info(f"✓ Saved execution plan {plan_id} for test {test_case_id}")
                    return plan_id

        except Exception as e:
            self.logger.error(f"Error saving plan: {e}")
            raise

    # Helper methods

    def _calculate_complexity(self, step_count: int, action_count: int,
                             test_type: str) -> float:
        """Calculate test complexity score (0-100)."""
        base_score = min(step_count * 10, 50)
        action_diversity = min(action_count * 5, 30)
        type_factor = 20 if test_type == 'api_test' else 0

        return min(base_score + action_diversity + type_factor, 100)

    def _extract_objectives(self, description: str) -> List[str]:
        """Extract test objectives from description."""
        objectives = []
        if description:
            # Simple heuristic: split by common keywords
            keywords = ['verify', 'validate', 'check', 'ensure', 'test']
            for keyword in keywords:
                if keyword.lower() in description.lower():
                    objectives.append(f"Verify test functionality")
                    break
        return objectives or ["Execute test case"]

    def _extract_preconditions(self, description: str) -> List[str]:
        """Extract preconditions from description."""
        preconditions = []
        if description:
            if 'login' in description.lower():
                preconditions.append("User must be logged in")
            if 'navigate' in description.lower():
                preconditions.append("Application must be accessible")
        return preconditions or ["Application is running"]

    def _generate_subtask_description(self, step_numbers: List[int],
                                     all_steps: List) -> str:
        """Generate description for a subtask."""
        if not step_numbers:
            return "Unknown subtask"
        return f"Execute steps {step_numbers[0]}-{step_numbers[-1]}"

    def _topological_sort(self, subtasks: List[SubTask],
                         dependencies: List[Dependency]) -> List[SubTask]:
        """Sort subtasks topologically based on dependencies."""
        # Simple implementation: return as-is if no complex dependencies
        return sorted(subtasks, key=lambda st: st.task_id)

    def _calculate_plan_confidence(self, subtask_count: int,
                                  dependency_count: int) -> float:
        """Calculate confidence score for execution plan."""
        # More subtasks = lower confidence, more dependencies = lower confidence
        base_confidence = 0.9
        subtask_factor = max(0, 1 - (subtask_count * 0.05))
        dependency_factor = max(0, 1 - (dependency_count * 0.03))

        return base_confidence * subtask_factor * dependency_factor

    def _generate_strategy(self, subtasks: List[SubTask]) -> str:
        """Generate overall strategy description."""
        if not subtasks:
            return "No strategy available"

        strategy = f"Execute {len(subtasks)} subtasks in sequence. "
        strategy += "Each subtask represents a logical grouping of test steps. "
        strategy += "Validate state after each subtask before proceeding."

        return strategy
