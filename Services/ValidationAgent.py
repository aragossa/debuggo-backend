"""
ValidationAgent Service

Validates generated test steps before execution to catch errors early.
Checks for:
- Valid selectors (XPath/CSS)
- Valid actions
- Data type correctness
- No hardcoded values
- API schema compliance
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from auroqa.Utils.Connectors.db_utils import get_db_connection_context


@dataclass
class ValidationResult:
    """Result of step validation"""
    is_valid: bool
    step_id: Optional[int] = None
    errors: List[str] = None
    warnings: List[str] = None
    confidence: float = 0.0  # 0-100
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.suggestions is None:
            self.suggestions = []


class ValidationAgent:
    """
    Validates test steps for correctness and best practices.
    Prevents invalid steps from being executed.
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.validation_rules = self._load_validation_rules()
    
    def _setup_logger(self):
        """Setup logger for ValidationAgent."""
        logger = logging.getLogger('ValidationAgent')
        logger.setLevel(logging.DEBUG)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _load_validation_rules(self) -> Dict[str, Any]:
        """Load validation rules."""
        return {
            'min_selector_length': 5,
            'max_selector_length': 500,
            'valid_actions': [
                'click', 'type', 'select', 'submit', 'wait', 'scroll',
                'hover', 'double_click', 'right_click', 'clear', 'check',
                'uncheck', 'upload_file', 'take_screenshot', 'verify_text',
                'verify_element', 'get_text', 'get_attribute', 'execute_script'
            ],
            'valid_by_strategies': ['xpath', 'css', 'id', 'name', 'class', 'tag'],
            'hardcoded_patterns': [
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',  # IP addresses
                r'user_\w+',  # Hardcoded user IDs
                r'client_\d+',  # Hardcoded client IDs
                r'group_\w+',  # Hardcoded group IDs
            ]
        }
    
    def validate_step(self, step: Dict[str, Any]) -> ValidationResult:
        """
        Validate a single test step.
        
        Args:
            step: Test step dictionary with action, selector, value, etc.
            
        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        suggestions = []
        confidence = 100.0
        
        try:
            # Validate required fields
            if not step.get('action'):
                errors.append("Missing 'action' field")
                confidence -= 20
            
            # API steps don't need element_locator, only UI steps do
            is_api_step = step.get('method') or step.get('endpoint')
            if not step.get('element_locator') and step.get('action') not in ['wait', 'scroll', 'execute_script', 'submit'] and not is_api_step:
                errors.append("Missing 'element_locator' field for action that requires it")
                confidence -= 20
            
            # Validate action
            action = step.get('action', '').lower()
            if action and action not in self.validation_rules['valid_actions']:
                errors.append(f"Invalid action '{action}'. Valid actions: {', '.join(self.validation_rules['valid_actions'])}")
                confidence -= 15
            
            # Validate selector
            selector = step.get('element_locator', '')
            if selector:
                selector_validation = self._validate_selector(selector, step.get('css_selector'))
                errors.extend(selector_validation['errors'])
                warnings.extend(selector_validation['warnings'])
                suggestions.extend(selector_validation['suggestions'])
                confidence -= selector_validation['confidence_penalty']
            
            # Validate value
            value = step.get('value', '')
            if value:
                value_validation = self._validate_value(value, action)
                errors.extend(value_validation['errors'])
                warnings.extend(value_validation['warnings'])
                suggestions.extend(value_validation['suggestions'])
                confidence -= value_validation['confidence_penalty']
            
            # Validate by_strategy
            by_strategy = step.get('by_strategy', 'xpath').lower()
            if by_strategy not in self.validation_rules['valid_by_strategies']:
                errors.append(f"Invalid by_strategy '{by_strategy}'")
                confidence -= 10
            
            # Validate API-specific fields if present
            if step.get('method'):
                api_validation = self._validate_api_step(step)
                errors.extend(api_validation['errors'])
                warnings.extend(api_validation['warnings'])
                suggestions.extend(api_validation['suggestions'])
                confidence -= api_validation['confidence_penalty']
            
            # Ensure confidence is between 0-100
            confidence = max(0, min(100, confidence))
            
            is_valid = len(errors) == 0
            
            result = ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                confidence=confidence,
                suggestions=suggestions
            )
            
            self.logger.info(
                f"✓ Step validation: {'VALID' if is_valid else 'INVALID'} "
                f"(confidence: {confidence:.1f}%, errors: {len(errors)}, warnings: {len(warnings)})"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error validating step: {str(e)}")
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation error: {str(e)}"],
                confidence=0.0
            )
    
    def _validate_selector(self, xpath_selector: str, css_selector: Optional[str] = None) -> Dict[str, Any]:
        """Validate XPath and CSS selectors."""
        errors = []
        warnings = []
        suggestions = []
        confidence_penalty = 0
        
        # Validate XPath
        if xpath_selector:
            if len(xpath_selector) < self.validation_rules['min_selector_length']:
                errors.append(f"XPath selector too short (min: {self.validation_rules['min_selector_length']})")
                confidence_penalty += 10
            
            if len(xpath_selector) > self.validation_rules['max_selector_length']:
                errors.append(f"XPath selector too long (max: {self.validation_rules['max_selector_length']})")
                confidence_penalty += 10
            
            # Check for common XPath issues
            if xpath_selector.count("'") > 5:
                warnings.append("XPath has many quotes - may be fragile")
                confidence_penalty += 5
            
            if '//' not in xpath_selector and not xpath_selector.startswith('/'):
                warnings.append("XPath may not be absolute or relative")
                confidence_penalty += 5
            
            # Check for hardcoded values
            hardcoded = self._check_hardcoded_values(xpath_selector)
            if hardcoded:
                warnings.append(f"Possible hardcoded values detected: {', '.join(hardcoded)}")
                confidence_penalty += 10
                suggestions.append("Use environment variables or dynamic values instead of hardcoded IDs")
        
        # Validate CSS selector
        if css_selector:
            if len(css_selector) < self.validation_rules['min_selector_length']:
                warnings.append(f"CSS selector very short (min recommended: {self.validation_rules['min_selector_length']})")
                confidence_penalty += 3
            
            if len(css_selector) > self.validation_rules['max_selector_length']:
                errors.append(f"CSS selector too long (max: {self.validation_rules['max_selector_length']})")
                confidence_penalty += 10
        
        return {
            'errors': errors,
            'warnings': warnings,
            'suggestions': suggestions,
            'confidence_penalty': confidence_penalty
        }
    
    def _validate_value(self, value: str, action: str) -> Dict[str, Any]:
        """Validate step value based on action."""
        errors = []
        warnings = []
        suggestions = []
        confidence_penalty = 0
        
        # Check for environment variable usage
        if action in ['type', 'select'] and value:
            if not value.startswith('%') and not value.startswith('{'):
                # Check if it looks like it should be a variable
                if any(keyword in value.lower() for keyword in ['password', 'email', 'user', 'login']):
                    warnings.append(f"Value '{value}' looks like it should be a variable")
                    suggestions.append("Use %variable_name% or {variable_name} format")
                    confidence_penalty += 10
            
            # Check for hardcoded IDs
            hardcoded = self._check_hardcoded_values(value)
            if hardcoded:
                warnings.append(f"Possible hardcoded values in value: {', '.join(hardcoded)}")
                confidence_penalty += 15
                suggestions.append("Use %random_option% for dropdowns or dynamic values")
        
        # Validate wait time
        if action == 'wait':
            try:
                wait_time = float(value)
                if wait_time < 0:
                    errors.append("Wait time cannot be negative")
                    confidence_penalty += 10
                elif wait_time > 60:
                    warnings.append(f"Wait time {wait_time}s is very long")
                    confidence_penalty += 5
            except ValueError:
                errors.append(f"Invalid wait time: {value}")
                confidence_penalty += 10
        
        return {
            'errors': errors,
            'warnings': warnings,
            'suggestions': suggestions,
            'confidence_penalty': confidence_penalty
        }
    
    def _validate_api_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Validate API-specific test step."""
        errors = []
        warnings = []
        suggestions = []
        confidence_penalty = 0
        
        # Validate HTTP method
        valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        method = step.get('method', '').upper()
        if method and method not in valid_methods:
            errors.append(f"Invalid HTTP method '{method}'")
            confidence_penalty += 15
        
        # Validate endpoint
        endpoint = step.get('endpoint', '')
        if not endpoint:
            errors.append("Missing 'endpoint' field for API step")
            confidence_penalty += 20
        elif not endpoint.startswith('/') and not endpoint.startswith('http'):
            warnings.append("Endpoint should start with '/' or 'http'")
            confidence_penalty += 5
        
        # Validate request body for POST/PUT
        if method in ['POST', 'PUT']:
            if not step.get('request_body'):
                warnings.append(f"{method} request without body")
                confidence_penalty += 5
        
        # Validate response validation
        if not step.get('expected_status'):
            warnings.append("No expected status code specified")
            confidence_penalty += 5
        
        return {
            'errors': errors,
            'warnings': warnings,
            'suggestions': suggestions,
            'confidence_penalty': confidence_penalty
        }
    
    def _check_hardcoded_values(self, text: str) -> List[str]:
        """Check for hardcoded values in text."""
        found = []
        for pattern in self.validation_rules['hardcoded_patterns']:
            matches = re.findall(pattern, text)
            if matches:
                found.extend(matches)
        return found
    
    def validate_test_case(self, test_case_id: int) -> Tuple[bool, List[ValidationResult]]:
        """
        Validate all steps in a test case.
        
        Args:
            test_case_id: ID of test case to validate
            
        Returns:
            Tuple of (all_valid, list of ValidationResults)
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, action, element_path, value, by_strategy, css_selector, method, endpoint
                        FROM test_steps
                        WHERE test_case_id = %s
                        ORDER BY step_order ASC
                    """, (test_case_id,))
                    
                    steps = cursor.fetchall()
            
            results = []
            all_valid = True
            
            for step_row in steps:
                step = {
                    'id': step_row[0],
                    'action': step_row[1],
                    'element_locator': step_row[2],
                    'value': step_row[3],
                    'by_strategy': step_row[4],
                    'css_selector': step_row[5],
                    'method': step_row[6],
                    'endpoint': step_row[7]
                }
                
                result = self.validate_step(step)
                result.step_id = step_row[0]
                results.append(result)
                
                if not result.is_valid:
                    all_valid = False
            
            self.logger.info(
                f"Test case {test_case_id} validation: "
                f"{sum(1 for r in results if r.is_valid)}/{len(results)} steps valid"
            )
            
            return all_valid, results
            
        except Exception as e:
            self.logger.error(f"Error validating test case {test_case_id}: {str(e)}")
            return False, []
    
    def save_validation_result(self, test_case_id: int, step_id: int, result: ValidationResult) -> bool:
        """Save validation result to database."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO validation_results 
                        (test_case_id, step_id, is_valid, errors, warnings, suggestions, confidence)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (test_case_id, step_id) 
                        DO UPDATE SET 
                            is_valid = EXCLUDED.is_valid,
                            errors = EXCLUDED.errors,
                            warnings = EXCLUDED.warnings,
                            suggestions = EXCLUDED.suggestions,
                            confidence = EXCLUDED.confidence,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        test_case_id,
                        step_id,
                        result.is_valid,
                        result.errors,
                        result.warnings,
                        result.suggestions,
                        result.confidence
                    ))
                    conn.commit()
            
            return True
        except Exception as e:
            self.logger.error(f"Error saving validation result: {str(e)}")
            return False
