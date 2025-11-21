"""
ErrorRecoveryAgent: Handles error detection and recovery strategies.

Responsibilities:
- Detect generation failures
- Analyze root causes
- Suggest alternative approaches
- Implement recovery strategies
- Escalate to human review when necessary

Recovery strategies:
1. Retry with different prompt phrasing
2. Use alternative tool (CSS instead of XPath)
3. Decompose problem into smaller steps
4. Use few-shot examples
5. Escalate to human review
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Types of errors that can occur."""
    ELEMENT_NOT_FOUND = "element_not_found"
    TIMEOUT = "timeout"
    INVALID_SELECTOR = "invalid_selector"
    ASSERTION_FAILED = "assertion_failed"
    API_ERROR = "api_error"
    NAVIGATION_ERROR = "navigation_error"
    DATA_VALIDATION_ERROR = "data_validation_error"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Recovery strategies."""
    RETRY_PROMPT = "retry_prompt"
    ALTERNATIVE_SELECTOR = "alternative_selector"
    DECOMPOSE_STEP = "decompose_step"
    FEW_SHOT_EXAMPLE = "few_shot_example"
    WAIT_AND_RETRY = "wait_and_retry"
    SKIP_STEP = "skip_step"
    ESCALATE = "escalate"


@dataclass
class ErrorAnalysis:
    """Analysis of an error."""
    error_type: ErrorType
    error_message: str
    root_cause: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    step_number: int
    context: Dict[str, Any]
    suggested_strategies: List[RecoveryStrategy]


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    test_case_id: int
    step_number: int
    error_type: str
    recovery_strategy: str
    recovery_details: Dict[str, Any]
    success: bool
    attempt_number: int
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class ErrorRecoveryAgent:
    """Agent responsible for error detection and recovery."""

    def __init__(self):
        self.system = System()
        self.logger = logging.getLogger(__name__)
        self.recovery_history: List[RecoveryAttempt] = []

    def detect_failure(self, result: Dict[str, Any]) -> bool:
        """
        Detect if a step execution failed.

        Args:
            result: Execution result

        Returns:
            True if failure detected, False otherwise
        """
        if not result:
            return True

        # Check for error indicators
        if result.get('success') is False:
            return True

        if result.get('error'):
            return True

        if result.get('status') == 'failed':
            return True

        if 'exception' in result:
            return True

        return False

    def analyze_root_cause(self, failure: Dict[str, Any],
                          step_context: Dict[str, Any] = None) -> ErrorAnalysis:
        """
        Analyze root cause of failure.

        Args:
            failure: Failure information
            step_context: Context of the step that failed

        Returns:
            ErrorAnalysis object
        """
        error_message = failure.get('error', 'Unknown error')
        error_type = self._classify_error(error_message)

        root_cause = self._determine_root_cause(error_type, error_message)
        severity = self._assess_severity(error_type, error_message)

        suggested_strategies = self._suggest_recovery_strategies(
            error_type, error_message, step_context or {}
        )

        analysis = ErrorAnalysis(
            error_type=error_type,
            error_message=error_message,
            root_cause=root_cause,
            severity=severity,
            step_number=step_context.get('step_number', 0) if step_context else 0,
            context=step_context or {},
            suggested_strategies=suggested_strategies
        )

        self.logger.info(
            f"✓ Analyzed error: type={error_type.value}, "
            f"severity={severity}, "
            f"strategies={len(suggested_strategies)}"
        )

        return analysis

    def suggest_recovery_strategy(self, analysis: ErrorAnalysis) -> RecoveryStrategy:
        """
        Suggest best recovery strategy.

        Args:
            analysis: ErrorAnalysis object

        Returns:
            Recommended RecoveryStrategy
        """
        if not analysis.suggested_strategies:
            return RecoveryStrategy.ESCALATE

        # Prioritize strategies based on severity and type
        if analysis.severity == 'critical':
            return RecoveryStrategy.ESCALATE

        # Return first suggested strategy
        return analysis.suggested_strategies[0]

    def implement_recovery(self, test_case_id: int, analysis: ErrorAnalysis,
                          strategy: RecoveryStrategy) -> Dict[str, Any]:
        """
        Implement recovery strategy.

        Args:
            test_case_id: ID of test case
            analysis: ErrorAnalysis object
            strategy: RecoveryStrategy to implement

        Returns:
            Recovery result
        """
        try:
            self.logger.info(
                f"🔧 Implementing recovery strategy: {strategy.value} "
                f"for error: {analysis.error_type.value}"
            )

            recovery_details = {}

            if strategy == RecoveryStrategy.RETRY_PROMPT:
                recovery_details = self._recover_retry_prompt(analysis)

            elif strategy == RecoveryStrategy.ALTERNATIVE_SELECTOR:
                recovery_details = self._recover_alternative_selector(analysis)

            elif strategy == RecoveryStrategy.DECOMPOSE_STEP:
                recovery_details = self._recover_decompose_step(analysis)

            elif strategy == RecoveryStrategy.FEW_SHOT_EXAMPLE:
                recovery_details = self._recover_few_shot_example(analysis)

            elif strategy == RecoveryStrategy.WAIT_AND_RETRY:
                recovery_details = self._recover_wait_and_retry(analysis)

            elif strategy == RecoveryStrategy.SKIP_STEP:
                recovery_details = self._recover_skip_step(analysis)

            elif strategy == RecoveryStrategy.ESCALATE:
                recovery_details = self._recover_escalate(analysis)

            # Record recovery attempt
            attempt = RecoveryAttempt(
                test_case_id=test_case_id,
                step_number=analysis.step_number,
                error_type=analysis.error_type.value,
                recovery_strategy=strategy.value,
                recovery_details=recovery_details,
                success=recovery_details.get('success', False)
            )
            self.recovery_history.append(attempt)

            # Save to database
            self._save_recovery_attempt(attempt)

            return {
                'success': recovery_details.get('success', False),
                'strategy': strategy.value,
                'details': recovery_details,
                'message': recovery_details.get('message', 'Recovery attempted')
            }

        except Exception as e:
            self.logger.error(f"Error implementing recovery: {e}")
            return {
                'success': False,
                'strategy': strategy.value,
                'error': str(e)
            }

    def escalate_to_human(self, test_case_id: int, analysis: ErrorAnalysis) -> None:
        """
        Escalate error to human review.

        Args:
            test_case_id: ID of test case
            analysis: ErrorAnalysis object
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO error_recovery_attempts
                        (test_case_id, step_number, error_type, recovery_strategy, 
                         recovery_details, success)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        test_case_id,
                        analysis.step_number,
                        analysis.error_type.value,
                        'escalate',
                        json.dumps({
                            'error_message': analysis.error_message,
                            'root_cause': analysis.root_cause,
                            'severity': analysis.severity,
                            'context': analysis.context
                        }),
                        False
                    ))
                    conn.commit()

                    self.logger.warning(
                        f"⚠ Escalated error to human review: "
                        f"test={test_case_id}, step={analysis.step_number}, "
                        f"error={analysis.error_type.value}"
                    )

        except Exception as e:
            self.logger.error(f"Error escalating to human: {e}")

    def get_recovery_history(self, test_case_id: int = None) -> List[RecoveryAttempt]:
        """
        Get recovery history.

        Args:
            test_case_id: Optional filter by test case

        Returns:
            List of RecoveryAttempt objects
        """
        if test_case_id:
            return [a for a in self.recovery_history if a.test_case_id == test_case_id]
        return self.recovery_history

    def get_recovery_stats(self) -> Dict[str, Any]:
        """
        Get recovery statistics.

        Returns:
            Statistics dictionary
        """
        total_attempts = len(self.recovery_history)
        successful = sum(1 for a in self.recovery_history if a.success)
        failed = total_attempts - successful

        strategy_counts = {}
        for attempt in self.recovery_history:
            strategy = attempt.recovery_strategy
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        return {
            'total_attempts': total_attempts,
            'successful': successful,
            'failed': failed,
            'success_rate': successful / total_attempts if total_attempts > 0 else 0,
            'strategy_distribution': strategy_counts
        }

    # Private methods

    def _classify_error(self, error_message: str) -> ErrorType:
        """Classify error type based on message."""
        error_lower = error_message.lower()

        if 'element' in error_lower or 'not found' in error_lower:
            return ErrorType.ELEMENT_NOT_FOUND

        if 'timeout' in error_lower:
            return ErrorType.TIMEOUT

        if 'xpath' in error_lower or 'css' in error_lower or 'selector' in error_lower:
            return ErrorType.INVALID_SELECTOR

        if 'assert' in error_lower or 'expected' in error_lower:
            return ErrorType.ASSERTION_FAILED

        if 'api' in error_lower or 'http' in error_lower or 'request' in error_lower:
            return ErrorType.API_ERROR

        if 'navigate' in error_lower or 'url' in error_lower:
            return ErrorType.NAVIGATION_ERROR

        if 'validation' in error_lower or 'invalid' in error_lower:
            return ErrorType.DATA_VALIDATION_ERROR

        return ErrorType.UNKNOWN

    def _determine_root_cause(self, error_type: ErrorType,
                             error_message: str) -> str:
        """Determine root cause of error."""
        causes = {
            ErrorType.ELEMENT_NOT_FOUND: "Element selector is incorrect or element not visible",
            ErrorType.TIMEOUT: "Page load or element visibility took too long",
            ErrorType.INVALID_SELECTOR: "XPath or CSS selector syntax is invalid",
            ErrorType.ASSERTION_FAILED: "Actual value doesn't match expected value",
            ErrorType.API_ERROR: "API request failed or returned error status",
            ErrorType.NAVIGATION_ERROR: "Failed to navigate to URL",
            ErrorType.DATA_VALIDATION_ERROR: "Data validation failed",
            ErrorType.UNKNOWN: "Unknown error - check logs for details"
        }

        return causes.get(error_type, "Unknown root cause")

    def _assess_severity(self, error_type: ErrorType, error_message: str) -> str:
        """Assess error severity."""
        if error_type in [ErrorType.API_ERROR, ErrorType.NAVIGATION_ERROR]:
            return 'high'

        if error_type == ErrorType.ELEMENT_NOT_FOUND:
            return 'medium'

        if error_type == ErrorType.TIMEOUT:
            return 'low'

        return 'medium'

    def _suggest_recovery_strategies(self, error_type: ErrorType,
                                    error_message: str,
                                    context: Dict) -> List[RecoveryStrategy]:
        """Suggest recovery strategies."""
        strategies = []

        if error_type == ErrorType.ELEMENT_NOT_FOUND:
            strategies = [
                RecoveryStrategy.ALTERNATIVE_SELECTOR,
                RecoveryStrategy.WAIT_AND_RETRY,
                RecoveryStrategy.FEW_SHOT_EXAMPLE,
                RecoveryStrategy.ESCALATE
            ]

        elif error_type == ErrorType.TIMEOUT:
            strategies = [
                RecoveryStrategy.WAIT_AND_RETRY,
                RecoveryStrategy.RETRY_PROMPT,
                RecoveryStrategy.ESCALATE
            ]

        elif error_type == ErrorType.INVALID_SELECTOR:
            strategies = [
                RecoveryStrategy.ALTERNATIVE_SELECTOR,
                RecoveryStrategy.FEW_SHOT_EXAMPLE,
                RecoveryStrategy.ESCALATE
            ]

        elif error_type == ErrorType.ASSERTION_FAILED:
            strategies = [
                RecoveryStrategy.RETRY_PROMPT,
                RecoveryStrategy.DECOMPOSE_STEP,
                RecoveryStrategy.ESCALATE
            ]

        else:
            strategies = [
                RecoveryStrategy.RETRY_PROMPT,
                RecoveryStrategy.DECOMPOSE_STEP,
                RecoveryStrategy.ESCALATE
            ]

        return strategies

    def _recover_retry_prompt(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Retry with different prompt phrasing."""
        return {
            'success': True,
            'message': 'Retrying with alternative prompt phrasing',
            'action': 'regenerate_with_different_prompt',
            'details': {
                'original_error': analysis.error_message,
                'retry_count': 1
            }
        }

    def _recover_alternative_selector(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Try alternative selector (CSS instead of XPath)."""
        return {
            'success': True,
            'message': 'Trying alternative selector type',
            'action': 'try_alternative_selector',
            'details': {
                'original_selector_type': 'xpath',
                'alternative_selector_type': 'css'
            }
        }

    def _recover_decompose_step(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Decompose step into smaller steps."""
        return {
            'success': True,
            'message': 'Decomposing step into smaller steps',
            'action': 'decompose_step',
            'details': {
                'original_step': analysis.step_number,
                'decomposed_into': 'multiple_smaller_steps'
            }
        }

    def _recover_few_shot_example(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Use few-shot examples for recovery."""
        return {
            'success': True,
            'message': 'Regenerating with few-shot examples',
            'action': 'regenerate_with_few_shot',
            'details': {
                'error_type': analysis.error_type.value,
                'example_count': 3
            }
        }

    def _recover_wait_and_retry(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Wait and retry."""
        return {
            'success': True,
            'message': 'Adding wait and retrying',
            'action': 'wait_and_retry',
            'details': {
                'wait_time_seconds': 2,
                'retry_count': 1
            }
        }

    def _recover_skip_step(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Skip problematic step."""
        return {
            'success': True,
            'message': 'Skipping problematic step',
            'action': 'skip_step',
            'details': {
                'skipped_step': analysis.step_number,
                'reason': 'Unable to recover'
            }
        }

    def _recover_escalate(self, analysis: ErrorAnalysis) -> Dict[str, Any]:
        """Escalate to human review."""
        return {
            'success': False,
            'message': 'Escalating to human review',
            'action': 'escalate',
            'details': {
                'error_type': analysis.error_type.value,
                'severity': analysis.severity,
                'requires_human_review': True
            }
        }

    def _save_recovery_attempt(self, attempt: RecoveryAttempt) -> None:
        """Save recovery attempt to database."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO error_recovery_attempts
                        (test_case_id, step_number, error_type, recovery_strategy,
                         recovery_details, success, attempt_number)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        attempt.test_case_id,
                        attempt.step_number,
                        attempt.error_type,
                        attempt.recovery_strategy,
                        json.dumps(attempt.recovery_details),
                        attempt.success,
                        attempt.attempt_number
                    ))
                    conn.commit()

        except Exception as e:
            self.logger.error(f"Error saving recovery attempt: {e}")
