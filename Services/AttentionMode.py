"""
Attention Mode Service

Implements "heightened attention mode" for complex tests (complexity > 80).
This mode provides stricter validation, more frequent DOM checks, and enhanced error handling.

Features:
- Automatic activation for high-complexity tests
- Stricter element validation
- Frequent DOM state checks
- Enhanced confidence thresholds
- More detailed logging
- Automatic recovery strategies
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class ValidationLevel(Enum):
    """Validation strictness levels."""
    NORMAL = "normal"          # Standard validation
    STRICT = "strict"          # Stricter validation (complexity 60-80)
    HEIGHTENED = "heightened"  # Heightened attention (complexity > 80)


@dataclass
class AttentionModeConfig:
    """Configuration for attention mode."""
    enabled: bool = False
    complexity_score: float = 0.0
    validation_level: ValidationLevel = ValidationLevel.NORMAL
    dom_check_frequency: int = 1  # Check DOM every N steps
    confidence_threshold: float = 0.75  # Minimum confidence for proceeding
    max_retries: int = 3
    enable_detailed_logging: bool = False
    enable_auto_recovery: bool = True
    enable_frequent_screenshots: bool = False


class AttentionMode:
    """
    Heightened Attention Mode for complex tests.
    
    Automatically enables stricter validation and more frequent checks
    when test complexity exceeds threshold.
    """
    
    # Complexity thresholds
    NORMAL_THRESHOLD = 60
    STRICT_THRESHOLD = 80
    HEIGHTENED_THRESHOLD = 80
    
    def __init__(self):
        """Initialize Attention Mode service."""
        self.logger = logging.getLogger(__name__)
        self.config = AttentionModeConfig()
        self.step_counter = 0
        self.dom_check_counter = 0
        self.validation_failures = []
        self.recovery_attempts = []
        self.logger.info("AttentionMode service initialized")
    
    def activate(self, complexity_score: float) -> AttentionModeConfig:
        """
        Activate attention mode based on complexity score.
        
        Args:
            complexity_score: Test complexity score (0-100)
            
        Returns:
            Updated AttentionModeConfig
        """
        self.config.complexity_score = complexity_score
        
        if complexity_score >= self.HEIGHTENED_THRESHOLD:
            self.config.enabled = True
            self.config.validation_level = ValidationLevel.HEIGHTENED
            self.config.dom_check_frequency = 1  # Check every step
            self.config.confidence_threshold = 0.85  # Higher threshold
            self.config.max_retries = 4  # More retries
            self.config.enable_detailed_logging = True
            self.config.enable_auto_recovery = True
            self.config.enable_frequent_screenshots = True
            
            self.logger.warning(
                f"🔴 HEIGHTENED ATTENTION MODE ACTIVATED (complexity: {complexity_score:.1f})"
            )
        elif complexity_score >= self.STRICT_THRESHOLD:
            self.config.enabled = True
            self.config.validation_level = ValidationLevel.STRICT
            self.config.dom_check_frequency = 2  # Check every 2 steps
            self.config.confidence_threshold = 0.80  # Higher threshold
            self.config.max_retries = 3
            self.config.enable_detailed_logging = True
            self.config.enable_auto_recovery = True
            self.config.enable_frequent_screenshots = False
            
            self.logger.warning(
                f"🟡 STRICT ATTENTION MODE ACTIVATED (complexity: {complexity_score:.1f})"
            )
        else:
            self.config.enabled = False
            self.config.validation_level = ValidationLevel.NORMAL
            self.config.dom_check_frequency = 5  # Check every 5 steps
            self.config.confidence_threshold = 0.75  # Standard threshold
            self.config.max_retries = 3
            self.config.enable_detailed_logging = False
            self.config.enable_auto_recovery = True
            self.config.enable_frequent_screenshots = False
            
            self.logger.info(
                f"Normal mode (complexity: {complexity_score:.1f})"
            )
        
        return self.config
    
    def should_check_dom(self) -> bool:
        """
        Determine if DOM check should be performed.
        
        Returns:
            True if DOM check should be performed
        """
        self.step_counter += 1
        
        if not self.config.enabled:
            return self.step_counter % self.config.dom_check_frequency == 0
        
        # In heightened mode, check every step
        if self.config.validation_level == ValidationLevel.HEIGHTENED:
            return True
        
        # In strict mode, check every 2 steps
        if self.config.validation_level == ValidationLevel.STRICT:
            return self.step_counter % 2 == 0
        
        return self.step_counter % self.config.dom_check_frequency == 0
    
    def should_take_screenshot(self) -> bool:
        """
        Determine if screenshot should be taken.
        
        Returns:
            True if screenshot should be taken
        """
        if self.config.enable_frequent_screenshots:
            return True  # Every step in heightened mode
        
        if self.config.validation_level == ValidationLevel.STRICT:
            return self.step_counter % 2 == 0  # Every 2 steps
        
        return self.step_counter % 5 == 0  # Every 5 steps in normal mode
    
    def validate_element(self, element_found: bool, confidence: float, 
                        element_locator: str = "") -> Dict[str, Any]:
        """
        Validate element with attention mode rules.
        
        Args:
            element_found: Whether element was found
            confidence: AI confidence score (0-1)
            element_locator: Element locator for logging
            
        Returns:
            Validation result dictionary
        """
        result = {
            'valid': False,
            'reason': '',
            'should_retry': False,
            'should_escalate': False
        }
        
        # Check if element was found
        if not element_found:
            result['reason'] = f"Element not found: {element_locator}"
            result['should_retry'] = True
            self.validation_failures.append({
                'type': 'element_not_found',
                'locator': element_locator,
                'timestamp': datetime.now().isoformat()
            })
            
            if self.config.enabled:
                self.logger.warning(f"[AttentionMode] Element not found: {element_locator}")
            
            return result
        
        # Check confidence threshold
        if confidence < self.config.confidence_threshold:
            result['reason'] = f"Low confidence: {confidence:.2f} < {self.config.confidence_threshold}"
            result['should_retry'] = True
            self.validation_failures.append({
                'type': 'low_confidence',
                'confidence': confidence,
                'threshold': self.config.confidence_threshold,
                'timestamp': datetime.now().isoformat()
            })
            
            if self.config.enabled:
                self.logger.warning(
                    f"[AttentionMode] Low confidence: {confidence:.2f} < {self.config.confidence_threshold}"
                )
            
            return result
        
        # Validation passed
        result['valid'] = True
        result['reason'] = "Validation passed"
        
        if self.config.enable_detailed_logging:
            self.logger.debug(
                f"[AttentionMode] Validation passed: {element_locator} (confidence: {confidence:.2f})"
            )
        
        return result
    
    def validate_dom_state(self, dom_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate DOM state with attention mode rules.
        
        Args:
            dom_state: Dictionary with DOM state information
                - element_count: Number of elements on page
                - has_changed: Whether DOM has changed
                - stability_score: DOM stability (0-1)
                
        Returns:
            Validation result dictionary
        """
        result = {
            'valid': True,
            'reason': '',
            'warnings': [],
            'should_wait': False
        }
        
        # Check element count
        element_count = dom_state.get('element_count', 0)
        if element_count == 0:
            result['valid'] = False
            result['reason'] = "DOM appears to be empty"
            result['warnings'].append("No elements found on page")
            return result
        
        # Check DOM stability
        stability_score = dom_state.get('stability_score', 1.0)
        if stability_score < 0.7:
            result['warnings'].append(
                f"DOM unstable (stability: {stability_score:.2f})"
            )
            result['should_wait'] = True
            
            if self.config.enabled:
                self.logger.warning(
                    f"[AttentionMode] DOM unstable: {stability_score:.2f}"
                )
        
        # Check if DOM has changed
        if dom_state.get('has_changed', False):
            result['warnings'].append("DOM has changed since last check")
            
            if self.config.enabled:
                self.logger.info("[AttentionMode] DOM state changed")
        
        if self.config.enable_detailed_logging and result['warnings']:
            self.logger.debug(f"[AttentionMode] DOM warnings: {result['warnings']}")
        
        return result
    
    def get_recovery_strategy(self, failure_type: str, 
                            attempt_count: int) -> Optional[str]:
        """
        Get recovery strategy for a failure.
        
        Args:
            failure_type: Type of failure (element_not_found, low_confidence, etc.)
            attempt_count: Number of attempts made
            
        Returns:
            Recovery strategy name or None
        """
        if not self.config.enable_auto_recovery:
            return None
        
        if attempt_count >= self.config.max_retries:
            return "escalate"
        
        strategies = {
            'element_not_found': [
                'wait_and_retry',
                'alternative_selector',
                'decompose_step',
                'escalate'
            ],
            'low_confidence': [
                'few_shot_example',
                'retry_prompt',
                'alternative_selector',
                'escalate'
            ],
            'timeout': [
                'wait_and_retry',
                'skip_step',
                'escalate'
            ],
            'assertion_failed': [
                'retry_prompt',
                'decompose_step',
                'escalate'
            ]
        }
        
        strategy_list = strategies.get(failure_type, ['retry_prompt', 'escalate'])
        
        if attempt_count < len(strategy_list):
            strategy = strategy_list[attempt_count]
            self.recovery_attempts.append({
                'failure_type': failure_type,
                'attempt': attempt_count,
                'strategy': strategy,
                'timestamp': datetime.now().isoformat()
            })
            
            if self.config.enable_detailed_logging:
                self.logger.info(
                    f"[AttentionMode] Recovery strategy: {strategy} (attempt {attempt_count})"
                )
            
            return strategy
        
        return "escalate"
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of attention mode activity.
        
        Returns:
            Summary dictionary
        """
        return {
            'enabled': self.config.enabled,
            'complexity_score': self.config.complexity_score,
            'validation_level': self.config.validation_level.value,
            'steps_processed': self.step_counter,
            'validation_failures': len(self.validation_failures),
            'recovery_attempts': len(self.recovery_attempts),
            'failure_types': self._count_failure_types(),
            'recovery_strategies': self._count_recovery_strategies(),
            'config': {
                'dom_check_frequency': self.config.dom_check_frequency,
                'confidence_threshold': self.config.confidence_threshold,
                'max_retries': self.config.max_retries,
                'detailed_logging': self.config.enable_detailed_logging,
                'auto_recovery': self.config.enable_auto_recovery,
                'frequent_screenshots': self.config.enable_frequent_screenshots
            }
        }
    
    def _count_failure_types(self) -> Dict[str, int]:
        """Count failures by type."""
        counts = {}
        for failure in self.validation_failures:
            failure_type = failure.get('type', 'unknown')
            counts[failure_type] = counts.get(failure_type, 0) + 1
        return counts
    
    def _count_recovery_strategies(self) -> Dict[str, int]:
        """Count recovery strategies used."""
        counts = {}
        for attempt in self.recovery_attempts:
            strategy = attempt.get('strategy', 'unknown')
            counts[strategy] = counts.get(strategy, 0) + 1
        return counts
    
    def reset(self):
        """Reset attention mode for new test."""
        self.step_counter = 0
        self.dom_check_counter = 0
        self.validation_failures = []
        self.recovery_attempts = []
        self.logger.debug("AttentionMode reset")
