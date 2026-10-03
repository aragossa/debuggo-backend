"""
ConfidenceScorer Service

Scores confidence in generated test steps.
Helps determine which steps are likely to work and which need review.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.BrowserAutomation.StepActions import action_names


@dataclass
class ConfidenceScore:
    """Confidence score for a test step"""
    step_id: int
    overall_confidence: float  # 0-100
    selector_confidence: float  # 0-100
    action_confidence: float  # 0-100
    data_confidence: float  # 0-100
    pattern_confidence: float  # 0-100
    factors: Dict[str, Any]  # Detailed factors
    risk_level: str  # 'low', 'medium', 'high'
    recommendations: list  # List of recommendations


class ConfidenceScorer:
    """
    Scores confidence in test steps based on various factors.
    Higher confidence = more likely to work on first try.
    """
    
    # Confidence thresholds
    CONFIDENCE_THRESHOLDS = {
        'high': (80, 100),      # 80-100
        'medium': (60, 79),     # 60-79
        'low': (40, 59),        # 40-59
        'very_low': (0, 39)     # 0-39
    }
    
    # Scoring weights
    WEIGHTS = {
        'selector': 0.30,
        'action': 0.20,
        'data': 0.25,
        'pattern': 0.25
    }
    
    def __init__(self):
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        """Setup logger for ConfidenceScorer."""
        logger = logging.getLogger('ConfidenceScorer')
        logger.setLevel(logging.DEBUG)
        # The app configures root logging (main.py); an own handler here would print every line twice
        if logging.getLogger().handlers:
            return logger
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def score_step(self, step: Dict[str, Any]) -> ConfidenceScore:
        """
        Score confidence in a test step.
        
        Args:
            step: Test step dictionary
            
        Returns:
            ConfidenceScore with detailed breakdown
        """
        step_id = step.get('id', 0)
        
        # Score each component
        selector_score = self._score_selector(step)
        action_score = self._score_action(step)
        data_score = self._score_data(step)
        pattern_score = self._score_pattern_match(step)
        
        # Calculate weighted overall score
        overall_score = (
            selector_score * self.WEIGHTS['selector'] +
            action_score * self.WEIGHTS['action'] +
            data_score * self.WEIGHTS['data'] +
            pattern_score * self.WEIGHTS['pattern']
        )
        
        # Determine risk level
        risk_level = self._get_risk_level(overall_score)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            step, selector_score, action_score, data_score, pattern_score
        )
        
        factors = {
            'selector_quality': selector_score,
            'action_validity': action_score,
            'data_quality': data_score,
            'pattern_match': pattern_score,
            'step_complexity': self._calculate_complexity(step),
            'has_fallback': 'css_selector' in step and step['css_selector'],
            'has_wait': 'wait_before' in step or 'wait_after' in step
        }
        
        score = ConfidenceScore(
            step_id=step_id,
            overall_confidence=overall_score,
            selector_confidence=selector_score,
            action_confidence=action_score,
            data_confidence=data_score,
            pattern_confidence=pattern_score,
            factors=factors,
            risk_level=risk_level,
            recommendations=recommendations
        )
        
        self.logger.info(
            f"Scored step {step_id}: {overall_score:.1f}% confidence ({risk_level} risk)"
        )
        
        return score
    
    def _score_selector(self, step: Dict[str, Any]) -> float:
        """Score selector quality."""
        score = 50.0  # Base score
        
        xpath = (step.get('element_locator') or '')
        css = (step.get('css_selector') or '')
        
        # Has XPath
        if xpath:
            score += 20
            
            # XPath quality checks
            if len(xpath) > 500:
                score -= 15  # Too long
            elif len(xpath) < 10:
                score -= 10  # Too short
            
            # Check for specificity
            if '//' in xpath:
                score += 5  # Relative path
            if xpath.count('[') > 3:
                score -= 5  # Too many conditions
            if xpath.count("'") > 5:
                score -= 5  # Too many quotes
            
            # Check for common patterns
            if 'text()' in xpath:
                score += 5  # Text-based is good
            if '@id' in xpath:
                score += 5  # ID-based is specific
            if 'contains' in xpath:
                score += 3  # Flexible matching
        
        # Has CSS fallback
        if css:
            score += 10
            
            # CSS quality checks
            if len(css) > 200:
                score -= 5
            if css.count(' ') > 5:
                score -= 3  # Too many descendants
        
        # Penalize if no selector
        if not xpath and not css:
            score = 10
        
        return max(0, min(100, score))
    
    def _score_action(self, step: Dict[str, Any]) -> float:
        """Score action validity."""
        score = 50.0  # Base score
        
        action = (step.get('action') or '').lower()
        
        # Known actions: every catalogued action counts, the common ones a bit more
        valid_actions = {name: 15 for name in action_names()}
        valid_actions.update({'click': 20, 'type': 18, 'select': 18, 'wait': 10})
        
        if action in valid_actions:
            score += valid_actions[action]
        else:
            score -= 20  # Unknown action
        
        # Check for action-specific issues
        if action == 'type' and not step.get('value'):
            score -= 15  # Type without value
        
        if action == 'select' and not step.get('value'):
            score -= 15  # Select without value
        
        if action == 'wait':
            try:
                wait_time = float(step.get('value', 0))
                if wait_time > 60:
                    score -= 10  # Very long wait
            except:
                score -= 10  # Invalid wait time
        
        return max(0, min(100, score))
    
    def _score_data(self, step: Dict[str, Any]) -> float:
        """Score data quality."""
        score = 50.0  # Base score
        
        value = (step.get('value') or '')
        
        # Check for proper variable usage
        if value:
            if value.startswith('%') and value.endswith('%'):
                score += 25  # Proper variable format
            elif value.startswith('{') and value.endswith('}'):
                score += 25  # Proper variable format
            elif any(keyword in value.lower() for keyword in ['password', 'email', 'user']):
                score -= 15  # Looks like should be variable
            
            # Check for hardcoded IDs
            if re.search(r'_\d+$', value):
                score -= 10  # Looks like hardcoded ID
            
            # Check for reasonable length
            if len(value) > 1000:
                score -= 10  # Too long
            elif len(value) > 0:
                score += 5  # Has value
        
        # Check for API-specific data
        if step.get('method'):
            if step.get('endpoint'):
                score += 10
            else:
                score -= 15
            
            if step.get('request_body'):
                score += 10
            
            if step.get('expected_status'):
                score += 10
        
        return max(0, min(100, score))
    
    def _score_pattern_match(self, step: Dict[str, Any]) -> float:
        """Score pattern match with known patterns."""
        score = 50.0  # Base score
        
        action = (step.get('action') or '').lower()
        
        # Common patterns that work well
        common_patterns = {
            'click_button': ['button', 'submit', 'click'],
            'fill_input': ['input', 'type', 'text'],
            'select_dropdown': ['select', 'dropdown', 'option'],
            'verify_text': ['verify', 'assert', 'text'],
        }
        
        # Check if step matches known patterns
        element = (step.get('element_locator') or '').lower()
        
        for pattern_name, keywords in common_patterns.items():
            if any(keyword in element or keyword == action for keyword in keywords):
                score += 15
                break
        
        # Penalize unusual combinations
        if action == 'click' and 'input' in element:
            score -= 10  # Clicking input is unusual
        
        if action == 'type' and 'button' in element:
            score -= 15  # Typing on button is wrong
        
        return max(0, min(100, score))
    
    def _calculate_complexity(self, step: Dict[str, Any]) -> str:
        """Calculate step complexity."""
        xpath = (step.get('element_locator') or '')
        
        # Count complexity factors
        factors = 0
        if xpath.count('[') > 2:
            factors += 1
        if xpath.count('or') > 0 or xpath.count('and') > 0:
            factors += 1
        if xpath.count('//') > 1:
            factors += 1
        if len(xpath) > 200:
            factors += 1
        
        if factors >= 3:
            return 'high'
        elif factors >= 1:
            return 'medium'
        else:
            return 'low'
    
    def _get_risk_level(self, score: float) -> str:
        """Get risk level from confidence score."""
        for level, (min_score, max_score) in self.CONFIDENCE_THRESHOLDS.items():
            if min_score <= score <= max_score:
                return level
        return 'very_low'
    
    def _generate_recommendations(
        self,
        step: Dict[str, Any],
        selector_score: float,
        action_score: float,
        data_score: float,
        pattern_score: float
    ) -> list:
        """Generate recommendations based on scores."""
        recommendations = []
        
        if selector_score < 60:
            recommendations.append("Consider improving selector specificity")
            if not step.get('css_selector'):
                recommendations.append("Add CSS selector as fallback")
        
        if action_score < 60:
            recommendations.append("Verify action is appropriate for element")
        
        if data_score < 60:
            recommendations.append("Review data values for correctness")
            if step.get('value') and not (step['value'].startswith('%') or step['value'].startswith('{')):
                recommendations.append("Consider using variables instead of hardcoded values")
        
        if pattern_score < 60:
            recommendations.append("This step pattern is unusual - verify it's correct")
        
        if not step.get('wait_before') and selector_score < 70:
            recommendations.append("Consider adding wait before this step")
        
        return recommendations
    
    def save_confidence_score(self, test_case_id: int, score: ConfidenceScore) -> bool:
        """
        Save confidence score to database.
        
        Args:
            test_case_id: ID of test case
            score: ConfidenceScore to save
            
        Returns:
            True if saved successfully
        """
        try:
            # Skip saving if step_id is 0 (unsaved step)
            if score.step_id <= 0:
                self.logger.warning(f"Skipping confidence score save for invalid step_id: {score.step_id}")
                return False

            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO confidence_scores
                        (test_case_id, step_id, overall_confidence, selector_confidence,
                         action_confidence, data_confidence, pattern_confidence,
                         risk_level, factors, recommendations)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (test_case_id, step_id)
                        DO UPDATE SET
                            overall_confidence = EXCLUDED.overall_confidence,
                            selector_confidence = EXCLUDED.selector_confidence,
                            action_confidence = EXCLUDED.action_confidence,
                            data_confidence = EXCLUDED.data_confidence,
                            pattern_confidence = EXCLUDED.pattern_confidence,
                            risk_level = EXCLUDED.risk_level,
                            factors = EXCLUDED.factors,
                            recommendations = EXCLUDED.recommendations,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        test_case_id,
                        score.step_id,
                        score.overall_confidence,
                        score.selector_confidence,
                        score.action_confidence,
                        score.data_confidence,
                        score.pattern_confidence,
                        score.risk_level,
                        str(score.factors),
                        str(score.recommendations)
                    ))
                    conn.commit()
            
            return True
        except Exception as e:
            self.logger.error(f"Error saving confidence score: {str(e)}")
            return False
    
    def get_average_confidence(self, test_case_id: int) -> Optional[float]:
        """
        Get average confidence for all steps in a test case.
        
        Args:
            test_case_id: ID of test case
            
        Returns:
            Average confidence score or None
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT AVG(overall_confidence)
                        FROM confidence_scores
                        WHERE test_case_id = %s
                    """, (test_case_id,))
                    
                    result = cursor.fetchone()
                    return result[0] if result and result[0] else None
        except Exception as e:
            self.logger.error(f"Error getting average confidence: {str(e)}")
            return None
    
    def get_low_confidence_steps(self, test_case_id: int, threshold: float = 60) -> list:
        """
        Get steps with low confidence scores.
        
        Args:
            test_case_id: ID of test case
            threshold: Confidence threshold (default 60)
            
        Returns:
            List of low-confidence steps
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT step_id, overall_confidence, risk_level, recommendations
                        FROM confidence_scores
                        WHERE test_case_id = %s AND overall_confidence < %s
                        ORDER BY overall_confidence ASC
                    """, (test_case_id, threshold))
                    
                    rows = cursor.fetchall()
            
            steps = []
            for row in rows:
                step = {
                    'step_id': row[0],
                    'confidence': row[1],
                    'risk_level': row[2],
                    'recommendations': eval(row[3]) if row[3] else []
                }
                steps.append(step)
            
            return steps
        except Exception as e:
            self.logger.error(f"Error getting low confidence steps: {str(e)}")
            return []
