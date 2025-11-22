"""
Confidence-based Decision Making Service

Implements intelligent decision making based on AI confidence scores.
When confidence is low, automatically suggests alternative approaches.

Features:
- Confidence threshold management
- Alternative path finding
- Few-shot example selection
- Decision logging and tracking
- Confidence trend analysis
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class ConfidenceLevel(Enum):
    """Confidence level categories."""
    VERY_LOW = "very_low"      # < 0.50
    LOW = "low"                # 0.50-0.75
    MEDIUM = "medium"          # 0.75-0.85
    HIGH = "high"              # 0.85-0.95
    VERY_HIGH = "very_high"    # >= 0.95


class DecisionAction(Enum):
    """Actions to take based on confidence."""
    PROCEED = "proceed"                          # Proceed normally
    USE_FEW_SHOT = "use_few_shot"               # Use few-shot examples
    FIND_ALTERNATIVE = "find_alternative"       # Find alternative approach
    DECOMPOSE = "decompose"                     # Decompose into smaller steps
    WAIT_AND_RETRY = "wait_and_retry"           # Wait and retry
    ESCALATE = "escalate"                       # Escalate to human review


@dataclass
class ConfidenceDecision:
    """Decision based on confidence score."""
    confidence: float
    level: ConfidenceLevel
    action: DecisionAction
    reason: str
    alternative_strategies: List[str]
    recommended_few_shot_count: int
    should_log_detailed: bool


class ConfidenceDecisionMaker:
    """
    Intelligent decision maker based on confidence scores.
    
    Makes decisions about how to proceed based on AI confidence levels.
    """
    
    # Confidence thresholds
    VERY_LOW_THRESHOLD = 0.50
    LOW_THRESHOLD = 0.75
    MEDIUM_THRESHOLD = 0.85
    HIGH_THRESHOLD = 0.95
    
    def __init__(self):
        """Initialize Confidence Decision Maker."""
        self.logger = logging.getLogger(__name__)
        self.confidence_history = []
        self.decision_history = []
        self.few_shot_usage = {}
        self.alternative_attempts = {}
        self.logger.info("ConfidenceDecisionMaker initialized")
    
    def make_decision(self, confidence: float, context: Dict[str, Any] = None) -> ConfidenceDecision:
        """
        Make decision based on confidence score.
        
        Args:
            confidence: Confidence score (0-1)
            context: Additional context (step_number, action, etc.)
            
        Returns:
            ConfidenceDecision with action and recommendations
        """
        context = context or {}
        
        # Determine confidence level
        level = self._get_confidence_level(confidence)
        
        # Make decision based on level
        if confidence >= self.HIGH_THRESHOLD:
            decision = ConfidenceDecision(
                confidence=confidence,
                level=level,
                action=DecisionAction.PROCEED,
                reason=f"High confidence ({confidence:.2f}), proceeding normally",
                alternative_strategies=[],
                recommended_few_shot_count=0,
                should_log_detailed=False
            )
        
        elif confidence >= self.MEDIUM_THRESHOLD:
            decision = ConfidenceDecision(
                confidence=confidence,
                level=level,
                action=DecisionAction.PROCEED,
                reason=f"Medium confidence ({confidence:.2f}), proceeding with caution",
                alternative_strategies=["few_shot_example", "alternative_selector"],
                recommended_few_shot_count=1,
                should_log_detailed=True
            )
        
        elif confidence >= self.LOW_THRESHOLD:
            decision = ConfidenceDecision(
                confidence=confidence,
                level=level,
                action=DecisionAction.USE_FEW_SHOT,
                reason=f"Low confidence ({confidence:.2f}), using few-shot examples",
                alternative_strategies=["few_shot_example", "alternative_selector", "decompose_step"],
                recommended_few_shot_count=2,
                should_log_detailed=True
            )
        
        elif confidence >= self.VERY_LOW_THRESHOLD:
            decision = ConfidenceDecision(
                confidence=confidence,
                level=level,
                action=DecisionAction.FIND_ALTERNATIVE,
                reason=f"Very low confidence ({confidence:.2f}), finding alternative approach",
                alternative_strategies=["alternative_selector", "decompose_step", "few_shot_example"],
                recommended_few_shot_count=3,
                should_log_detailed=True
            )
        
        else:
            decision = ConfidenceDecision(
                confidence=confidence,
                level=level,
                action=DecisionAction.ESCALATE,
                reason=f"Extremely low confidence ({confidence:.2f}), escalating",
                alternative_strategies=["escalate", "skip_step"],
                recommended_few_shot_count=0,
                should_log_detailed=True
            )
        
        # Record decision
        self._record_decision(decision, context)
        
        return decision
    
    def should_stop_and_reconsider(self, confidence: float) -> bool:
        """
        Determine if should stop and reconsider approach.
        
        Args:
            confidence: Confidence score (0-1)
            
        Returns:
            True if should stop and reconsider
        """
        return confidence < self.LOW_THRESHOLD
    
    def get_alternative_strategies(self, confidence: float, 
                                  failure_type: str = None) -> List[str]:
        """
        Get alternative strategies based on confidence and failure type.
        
        Args:
            confidence: Confidence score (0-1)
            failure_type: Type of failure (optional)
            
        Returns:
            List of alternative strategies
        """
        level = self._get_confidence_level(confidence)
        
        # Base strategies by confidence level
        strategies_by_level = {
            ConfidenceLevel.VERY_HIGH: [],
            ConfidenceLevel.HIGH: ["few_shot_example"],
            ConfidenceLevel.MEDIUM: ["few_shot_example", "alternative_selector"],
            ConfidenceLevel.LOW: ["few_shot_example", "alternative_selector", "decompose_step"],
            ConfidenceLevel.VERY_LOW: ["alternative_selector", "decompose_step", "escalate"]
        }
        
        strategies = strategies_by_level.get(level, [])
        
        # Add failure-specific strategies
        if failure_type:
            failure_strategies = self._get_failure_specific_strategies(failure_type)
            strategies = list(set(strategies + failure_strategies))
        
        return strategies
    
    def select_few_shot_count(self, confidence: float) -> int:
        """
        Select number of few-shot examples based on confidence.
        
        Args:
            confidence: Confidence score (0-1)
            
        Returns:
            Recommended number of few-shot examples
        """
        if confidence >= self.MEDIUM_THRESHOLD:
            return 1  # One example for medium confidence
        elif confidence >= self.LOW_THRESHOLD:
            return 2  # Two examples for low confidence
        elif confidence >= self.VERY_LOW_THRESHOLD:
            return 3  # Three examples for very low confidence
        else:
            return 5  # Five examples for extremely low confidence
    
    def analyze_confidence_trend(self, window_size: int = 5) -> Dict[str, Any]:
        """
        Analyze confidence trend over recent steps.
        
        Args:
            window_size: Number of recent steps to analyze
            
        Returns:
            Trend analysis dictionary
        """
        if not self.confidence_history:
            return {
                'trend': 'no_data',
                'average': 0.0,
                'min': 0.0,
                'max': 0.0,
                'direction': 'unknown'
            }
        
        # Get recent confidence scores
        recent = self.confidence_history[-window_size:]
        
        if len(recent) < 2:
            return {
                'trend': 'insufficient_data',
                'average': recent[0] if recent else 0.0,
                'min': recent[0] if recent else 0.0,
                'max': recent[0] if recent else 0.0,
                'direction': 'unknown'
            }
        
        # Calculate statistics
        average = sum(recent) / len(recent)
        min_conf = min(recent)
        max_conf = max(recent)
        
        # Determine direction
        if recent[-1] > recent[0]:
            direction = 'improving'
        elif recent[-1] < recent[0]:
            direction = 'declining'
        else:
            direction = 'stable'
        
        # Determine trend
        if average >= self.MEDIUM_THRESHOLD:
            trend = 'healthy'
        elif average >= self.LOW_THRESHOLD:
            trend = 'concerning'
        else:
            trend = 'critical'
        
        return {
            'trend': trend,
            'average': average,
            'min': min_conf,
            'max': max_conf,
            'direction': direction,
            'recent_scores': recent
        }
    
    def should_use_alternative_selector(self, confidence: float, 
                                       attempt_count: int = 1) -> bool:
        """
        Determine if should use alternative selector.
        
        Args:
            confidence: Confidence score (0-1)
            attempt_count: Number of attempts made
            
        Returns:
            True if should use alternative selector
        """
        if confidence >= self.MEDIUM_THRESHOLD:
            return attempt_count > 2
        elif confidence >= self.LOW_THRESHOLD:
            return attempt_count > 1
        else:
            return True
    
    def should_decompose_step(self, confidence: float, 
                             step_complexity: float = 0.5) -> bool:
        """
        Determine if should decompose step into smaller parts.
        
        Args:
            confidence: Confidence score (0-1)
            step_complexity: Step complexity (0-1)
            
        Returns:
            True if should decompose
        """
        # Decompose if confidence is low AND step is complex
        if confidence < self.LOW_THRESHOLD and step_complexity > 0.7:
            return True
        
        # Decompose if confidence is very low
        if confidence < self.VERY_LOW_THRESHOLD:
            return True
        
        return False
    
    def should_wait_and_retry(self, confidence: float, 
                             retry_count: int = 0) -> Tuple[bool, int]:
        """
        Determine if should wait and retry.
        
        Args:
            confidence: Confidence score (0-1)
            retry_count: Number of retries already attempted
            
        Returns:
            Tuple of (should_retry, wait_seconds)
        """
        if confidence >= self.MEDIUM_THRESHOLD:
            return False, 0
        
        if retry_count >= 3:
            return False, 0
        
        # Calculate wait time based on confidence
        wait_seconds = int((1 - confidence) * 10)  # 0-10 seconds
        
        return True, wait_seconds
    
    def get_decision_summary(self) -> Dict[str, Any]:
        """
        Get summary of decision making activity.
        
        Returns:
            Summary dictionary
        """
        if not self.decision_history:
            return {
                'total_decisions': 0,
                'decisions_by_action': {},
                'average_confidence': 0.0,
                'confidence_trend': self.analyze_confidence_trend()
            }
        
        # Count decisions by action
        action_counts = {}
        for decision in self.decision_history:
            action = decision['action'].value
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Calculate average confidence
        avg_confidence = sum(self.confidence_history) / len(self.confidence_history)
        
        return {
            'total_decisions': len(self.decision_history),
            'decisions_by_action': action_counts,
            'average_confidence': avg_confidence,
            'confidence_trend': self.analyze_confidence_trend(),
            'few_shot_usage': self.few_shot_usage,
            'alternative_attempts': self.alternative_attempts
        }
    
    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Determine confidence level from score."""
        if confidence >= self.HIGH_THRESHOLD:
            return ConfidenceLevel.VERY_HIGH
        elif confidence >= self.MEDIUM_THRESHOLD:
            return ConfidenceLevel.HIGH
        elif confidence >= self.LOW_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        elif confidence >= self.VERY_LOW_THRESHOLD:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def _record_decision(self, decision: ConfidenceDecision, context: Dict[str, Any]):
        """Record decision for analysis."""
        self.confidence_history.append(decision.confidence)
        
        decision_record = {
            'confidence': decision.confidence,
            'level': decision.level.value,
            'action': decision.action,
            'reason': decision.reason,
            'timestamp': datetime.now().isoformat(),
            'context': context
        }
        self.decision_history.append(decision_record)
        
        # Log decision
        if decision.should_log_detailed:
            self.logger.warning(
                f"[ConfidenceDecision] {decision.reason} | "
                f"Action: {decision.action.value} | "
                f"Alternatives: {', '.join(decision.alternative_strategies)}"
            )
        else:
            self.logger.debug(
                f"[ConfidenceDecision] {decision.reason} | "
                f"Action: {decision.action.value}"
            )
    
    def _get_failure_specific_strategies(self, failure_type: str) -> List[str]:
        """Get strategies specific to failure type."""
        strategies_map = {
            'element_not_found': ['alternative_selector', 'wait_and_retry', 'decompose_step'],
            'low_confidence': ['few_shot_example', 'alternative_selector'],
            'timeout': ['wait_and_retry', 'decompose_step'],
            'assertion_failed': ['few_shot_example', 'decompose_step'],
            'navigation_error': ['wait_and_retry', 'alternative_selector'],
            'data_validation': ['few_shot_example', 'decompose_step']
        }
        
        return strategies_map.get(failure_type, [])
    
    def record_few_shot_usage(self, step_number: int, count: int):
        """Record few-shot example usage."""
        self.few_shot_usage[f"step_{step_number}"] = count
    
    def record_alternative_attempt(self, step_number: int, strategy: str):
        """Record alternative strategy attempt."""
        key = f"step_{step_number}"
        if key not in self.alternative_attempts:
            self.alternative_attempts[key] = []
        self.alternative_attempts[key].append(strategy)
    
    def reset(self):
        """Reset for new test."""
        self.confidence_history = []
        self.decision_history = []
        self.few_shot_usage = {}
        self.alternative_attempts = {}
        self.logger.debug("ConfidenceDecisionMaker reset")
