"""
ExecutionFeedbackCollector Service

Collects and analyzes feedback from test execution failures.
Categorizes errors and generates suggestions for improvement.
"""

import logging
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from auroqa.Utils.Connectors.db_utils import get_db_connection_context


@dataclass
class FailureRecord:
    """Record of a test step failure"""
    test_case_id: int
    step_id: int
    step_order: int
    action: str
    element_locator: str
    error_type: str
    error_message: str
    error_details: Dict[str, Any]
    screenshot_path: Optional[str] = None
    html_snapshot: Optional[str] = None
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class ExecutionFeedbackCollector:
    """
    Collects feedback from test execution failures.
    Analyzes errors and generates suggestions for improvement.
    """
    
    # Error categories and their characteristics
    ERROR_CATEGORIES = {
        'selector_not_found': {
            'keywords': ['no such element', 'element not found', 'cannot find', 'not visible'],
            'suggestions': [
                'Selector may be incorrect or element not loaded',
                'Try using CSS selector fallback',
                'Add wait for element to load',
                'Check if element is inside iframe'
            ]
        },
        'element_not_clickable': {
            'keywords': ['not clickable', 'element not interactable', 'obscured'],
            'suggestions': [
                'Element may be hidden or covered by another element',
                'Try scrolling to element first',
                'Use JavaScript click instead',
                'Wait for element to be visible'
            ]
        },
        'stale_element': {
            'keywords': ['stale element', 'element is no longer attached'],
            'suggestions': [
                'Element was removed from DOM after finding',
                'Re-find element before interacting',
                'Add wait for element stability',
                'Avoid storing element references'
            ]
        },
        'timeout': {
            'keywords': ['timeout', 'timed out', 'timeout waiting'],
            'suggestions': [
                'Element took too long to appear',
                'Increase wait timeout',
                'Check if element exists on page',
                'Verify network connectivity'
            ]
        },
        'value_error': {
            'keywords': ['value', 'invalid', 'type error', 'format'],
            'suggestions': [
                'Value format may be incorrect',
                'Check data type compatibility',
                'Verify variable substitution',
                'Use proper formatting for value'
            ]
        },
        'navigation_error': {
            'keywords': ['navigation', 'url', 'redirect', 'page load'],
            'suggestions': [
                'Page navigation failed',
                'Check base URL configuration',
                'Verify network connectivity',
                'Check for redirects or authentication'
            ]
        },
        'assertion_error': {
            'keywords': ['assert', 'expected', 'actual', 'verification failed'],
            'suggestions': [
                'Verification condition not met',
                'Check expected vs actual values',
                'Verify element state or content',
                'Add more specific assertion'
            ]
        },
        'api_error': {
            'keywords': ['http', 'status', 'response', 'request failed', '4xx', '5xx'],
            'suggestions': [
                'API request failed',
                'Check endpoint and method',
                'Verify request body and headers',
                'Check API response status'
            ]
        },
        'unknown_error': {
            'keywords': [],
            'suggestions': [
                'Unknown error occurred',
                'Check logs for more details',
                'Try running step again',
                'Escalate to human review'
            ]
        }
    }
    
    def __init__(self):
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        """Setup logger for ExecutionFeedbackCollector."""
        logger = logging.getLogger('ExecutionFeedbackCollector')
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
    
    def collect_failure(
        self,
        test_case_id: int,
        step_id: int,
        step_order: int,
        action: str,
        element_locator: str,
        error: Exception,
        screenshot_path: Optional[str] = None,
        html_snapshot: Optional[str] = None
    ) -> FailureRecord:
        """
        Collect failure information from a test step execution.
        
        Args:
            test_case_id: ID of test case
            step_id: ID of test step
            step_order: Order of step in test
            action: Action that was attempted
            element_locator: Selector that was used
            error: Exception that occurred
            screenshot_path: Path to screenshot if available
            html_snapshot: HTML snapshot if available
            
        Returns:
            FailureRecord with collected information
        """
        error_message = str(error)
        error_type = type(error).__name__
        error_details = {
            'exception_type': error_type,
            'exception_message': error_message,
            'traceback': getattr(error, '__traceback__', None)
        }
        
        record = FailureRecord(
            test_case_id=test_case_id,
            step_id=step_id,
            step_order=step_order,
            action=action,
            element_locator=element_locator,
            error_type=error_type,
            error_message=error_message,
            error_details=error_details,
            screenshot_path=screenshot_path,
            html_snapshot=html_snapshot
        )
        
        self.logger.info(
            f"📝 Collected failure for test {test_case_id} step {step_order}: {error_type}"
        )
        
        return record
    
    def categorize_error(self, error_message: str) -> str:
        """
        Categorize error based on error message.
        
        Args:
            error_message: Error message to categorize
            
        Returns:
            Error category name
        """
        error_lower = error_message.lower()
        
        for category, config in self.ERROR_CATEGORIES.items():
            if category == 'unknown_error':
                continue
            
            for keyword in config['keywords']:
                if keyword in error_lower:
                    self.logger.debug(f"Categorized error as: {category}")
                    return category
        
        return 'unknown_error'
    
    def extract_suggestions(self, error_message: str) -> List[str]:
        """
        Extract suggestions for fixing an error.
        
        Args:
            error_message: Error message
            
        Returns:
            List of suggestions
        """
        category = self.categorize_error(error_message)
        suggestions = self.ERROR_CATEGORIES.get(category, {}).get('suggestions', [])
        
        self.logger.debug(f"Extracted {len(suggestions)} suggestions for {category}")
        
        return suggestions
    
    def generate_ai_feedback(self, failure_record: FailureRecord) -> str:
        """
        Generate AI feedback prompt based on failure record.
        
        Args:
            failure_record: FailureRecord to generate feedback for
            
        Returns:
            Feedback prompt for AI
        """
        category = self.categorize_error(failure_record.error_message)
        suggestions = self.extract_suggestions(failure_record.error_message)
        
        feedback = f"""
Test Step Execution Failed:

Step Order: {failure_record.step_order}
Action: {failure_record.action}
Selector: {failure_record.element_locator}
Error Type: {failure_record.error_type}
Error Message: {failure_record.error_message}
Error Category: {category}

Suggestions for fixing:
{chr(10).join(f'- {s}' for s in suggestions)}

Please regenerate this step with the following considerations:
1. Verify the selector is correct and element exists on page
2. Consider using CSS selector as fallback
3. Add appropriate wait conditions if needed
4. Ensure element is visible and clickable
5. Check for any dynamic content or iframes
"""
        
        return feedback.strip()
    
    def save_failure_record(self, record: FailureRecord) -> bool:
        """
        Save failure record to database.
        
        Args:
            record: FailureRecord to save
            
        Returns:
            True if saved successfully
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO execution_feedback
                        (test_case_id, step_id, step_order, action, element_locator, 
                         error_type, error_message, error_details, screenshot_path, 
                         html_snapshot, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        record.test_case_id,
                        record.step_id,
                        record.step_order,
                        record.action,
                        record.element_locator,
                        record.error_type,
                        record.error_message,
                        json.dumps(record.error_details),
                        record.screenshot_path,
                        record.html_snapshot,
                        record.timestamp
                    ))
                    conn.commit()
            
            self.logger.info(f"✅ Saved failure record for test {record.test_case_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving failure record: {str(e)}")
            return False
    
    def get_failure_history(self, test_case_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get failure history for a test case.
        
        Args:
            test_case_id: ID of test case
            limit: Maximum number of records to retrieve
            
        Returns:
            List of failure records
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, test_case_id, step_id, step_order, action, element_locator,
                               error_type, error_message, error_details, screenshot_path,
                               html_snapshot, created_at
                        FROM execution_feedback
                        WHERE test_case_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (test_case_id, limit))
                    
                    rows = cursor.fetchall()
            
            records = []
            for row in rows:
                record = {
                    'id': row[0],
                    'test_case_id': row[1],
                    'step_id': row[2],
                    'step_order': row[3],
                    'action': row[4],
                    'element_locator': row[5],
                    'error_type': row[6],
                    'error_message': row[7],
                    'error_details': json.loads(row[8]) if row[8] else {},
                    'screenshot_path': row[9],
                    'html_snapshot': row[10],
                    'created_at': row[11].isoformat() if row[11] else None
                }
                records.append(record)
            
            return records
            
        except Exception as e:
            self.logger.error(f"Error getting failure history: {str(e)}")
            return []
    
    def get_error_patterns(self, test_case_id: int) -> Dict[str, int]:
        """
        Get error patterns for a test case.
        
        Args:
            test_case_id: ID of test case
            
        Returns:
            Dictionary of error types and their counts
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT error_type, COUNT(*) as count
                        FROM execution_feedback
                        WHERE test_case_id = %s
                        GROUP BY error_type
                        ORDER BY count DESC
                    """, (test_case_id,))
                    
                    rows = cursor.fetchall()
            
            patterns = {row[0]: row[1] for row in rows}
            
            self.logger.info(f"Found {len(patterns)} error patterns for test {test_case_id}")
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"Error getting error patterns: {str(e)}")
            return {}
    
    def get_most_common_errors(self, client_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most common errors across all test cases for a client.
        
        Args:
            client_id: Client ID
            limit: Maximum number of errors to retrieve
            
        Returns:
            List of most common errors
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT error_type, error_message, COUNT(*) as count
                        FROM execution_feedback ef
                        JOIN test_cases tc ON ef.test_case_id = tc.id
                        WHERE tc.client_id = %s
                        GROUP BY error_type, error_message
                        ORDER BY count DESC
                        LIMIT %s
                    """, (client_id, limit))
                    
                    rows = cursor.fetchall()
            
            errors = []
            for row in rows:
                error = {
                    'error_type': row[0],
                    'error_message': row[1],
                    'count': row[2],
                    'category': self.categorize_error(row[1]),
                    'suggestions': self.extract_suggestions(row[1])
                }
                errors.append(error)
            
            return errors
            
        except Exception as e:
            self.logger.error(f"Error getting most common errors: {str(e)}")
            return []
