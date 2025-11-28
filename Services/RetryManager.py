"""
RetryManager: Manages automatic retry logic for failed test suites

Features:
- Configurable retry attempts
- Exponential backoff support
- Retry delay management
- Retry history tracking
- Success/failure thresholds
- Retry statistics
"""

import logging
import time
from typing import Dict, Optional, List, Callable
from datetime import datetime, timedelta
from auroqa.Services.ExecutionPlanService import ExecutionPlanService
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class RetryManager:
    """Manages automatic retry logic for test suites"""
    
    def __init__(self):
        """Initialize RetryManager"""
        self.logger = logging.getLogger(__name__)
        self.system = System()
        self.plan_service = ExecutionPlanService()
    
    def should_retry(
        self,
        suite_run_id: int,
        current_retry_count: int,
        max_retries: int,
        failure_threshold: int = 1
    ) -> bool:
        """
        Determine if a suite should be retried
        
        Args:
            suite_run_id: ID of the suite run
            current_retry_count: Current number of retries
            max_retries: Maximum allowed retries
            failure_threshold: Number of failures before retry
            
        Returns:
            True if should retry, False otherwise
        """
        try:
            # Check if max retries exceeded
            if current_retry_count >= max_retries:
                self.logger.info(f"Max retries ({max_retries}) reached for suite run {suite_run_id}")
                return False
            
            # Check failure threshold
            if failure_threshold > 1:
                failed_tests = self._get_failed_test_count(suite_run_id)
                if failed_tests < failure_threshold:
                    self.logger.info(f"Failure count ({failed_tests}) below threshold ({failure_threshold})")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error determining retry eligibility: {e}")
            return False
    
    def calculate_retry_delay(
        self,
        retry_count: int,
        base_delay: int = 5,
        backoff_multiplier: float = 2.0,
        max_delay: int = 300
    ) -> int:
        """
        Calculate delay before next retry with exponential backoff
        
        Args:
            retry_count: Current retry attempt number (0-indexed)
            base_delay: Base delay in seconds
            backoff_multiplier: Multiplier for exponential backoff
            max_delay: Maximum delay in seconds
            
        Returns:
            Delay in seconds
        """
        try:
            # Calculate exponential backoff: base_delay * (multiplier ^ retry_count)
            delay = int(base_delay * (backoff_multiplier ** retry_count))
            
            # Cap at max_delay
            delay = min(delay, max_delay)
            
            self.logger.info(f"Calculated retry delay: {delay}s for retry {retry_count}")
            return delay
        except Exception as e:
            self.logger.error(f"Error calculating retry delay: {e}")
            return base_delay
    
    def wait_before_retry(self, delay_seconds: int) -> bool:
        """
        Wait before retrying
        
        Args:
            delay_seconds: Delay in seconds
            
        Returns:
            True if wait completed successfully
        """
        try:
            if delay_seconds > 0:
                self.logger.info(f"Waiting {delay_seconds}s before retry...")
                time.sleep(delay_seconds)
            return True
        except Exception as e:
            self.logger.error(f"Error waiting for retry: {e}")
            return False
    
    def execute_with_retry(
        self,
        suite_run_id: int,
        execute_func: Callable,
        max_retries: int = 3,
        base_delay: int = 5,
        backoff_multiplier: float = 2.0
    ) -> Dict:
        """
        Execute a function with automatic retry logic
        
        Args:
            suite_run_id: ID of the suite run
            execute_func: Function to execute
            max_retries: Maximum retry attempts
            base_delay: Base delay between retries
            backoff_multiplier: Exponential backoff multiplier
            
        Returns:
            Execution result with retry information
        """
        retry_count = 0
        last_error = None
        retry_history = []
        
        try:
            while retry_count <= max_retries:
                try:
                    self.logger.info(f"Executing suite run {suite_run_id} (attempt {retry_count + 1}/{max_retries + 1})")
                    
                    # Execute the function
                    result = execute_func()
                    
                    if result.get('status') == 'passed':
                        self.logger.info(f"Suite run {suite_run_id} passed on attempt {retry_count + 1}")
                        return {
                            'status': 'passed',
                            'retry_count': retry_count,
                            'result': result,
                            'retry_history': retry_history
                        }
                    
                    # If failed, check if we should retry
                    if retry_count < max_retries and self.should_retry(
                        suite_run_id, retry_count, max_retries
                    ):
                        # Log retry attempt
                        retry_info = {
                            'retry_number': retry_count + 1,
                            'status': 'failed',
                            'timestamp': datetime.now(),
                            'error': result.get('error', 'Unknown error')
                        }
                        retry_history.append(retry_info)
                        
                        # Log to database
                        self.plan_service.log_retry_attempt(
                            suite_run_id=suite_run_id,
                            retry_number=retry_count + 1,
                            status='failed',
                            passed_tests=result.get('passed_tests', 0),
                            failed_tests=result.get('failed_tests', 0),
                            error_message=result.get('error', 'Unknown error')
                        )
                        
                        # Calculate delay and wait
                        delay = self.calculate_retry_delay(
                            retry_count,
                            base_delay,
                            backoff_multiplier
                        )
                        self.wait_before_retry(delay)
                        
                        retry_count += 1
                    else:
                        # No more retries
                        self.logger.warning(f"Suite run {suite_run_id} failed, no more retries")
                        return {
                            'status': 'failed',
                            'retry_count': retry_count,
                            'result': result,
                            'retry_history': retry_history
                        }
                
                except Exception as e:
                    last_error = str(e)
                    self.logger.error(f"Error executing suite run {suite_run_id}: {e}")
                    
                    if retry_count < max_retries:
                        retry_info = {
                            'retry_number': retry_count + 1,
                            'status': 'error',
                            'timestamp': datetime.now(),
                            'error': last_error
                        }
                        retry_history.append(retry_info)
                        
                        delay = self.calculate_retry_delay(
                            retry_count,
                            base_delay,
                            backoff_multiplier
                        )
                        self.wait_before_retry(delay)
                        retry_count += 1
                    else:
                        return {
                            'status': 'error',
                            'retry_count': retry_count,
                            'error': last_error,
                            'retry_history': retry_history
                        }
        
        except Exception as e:
            self.logger.error(f"Unexpected error in execute_with_retry: {e}")
            return {
                'status': 'error',
                'retry_count': retry_count,
                'error': str(e),
                'retry_history': retry_history
            }
    
    def get_retry_statistics(self, suite_run_id: int) -> Optional[Dict]:
        """
        Get retry statistics for a suite run
        
        Args:
            suite_run_id: ID of the suite run
            
        Returns:
            Retry statistics or None
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Get retry history
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total_retries,
                               SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as successful_retries,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_retries,
                               MAX(attempted_at) as last_retry_at
                        FROM execution_suite_plan_retry_history
                        WHERE execution_suite_plan_suite_run_id = %s
                        """,
                        (suite_run_id,)
                    )
                    
                    result = cursor.fetchone()
                    if not result:
                        return None
                    
                    return {
                        'suite_run_id': suite_run_id,
                        'total_retries': result[0] or 0,
                        'successful_retries': result[1] or 0,
                        'failed_retries': result[2] or 0,
                        'last_retry_at': result[3]
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting retry statistics: {e}")
            return None
    
    def get_retry_history(
        self,
        suite_run_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get retry history for a suite run
        
        Args:
            suite_run_id: ID of the suite run
            limit: Number of records to retrieve
            offset: Number of records to skip
            
        Returns:
            List of retry history records
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, retry_number, attempted_at, completed_at, status,
                               passed_tests, failed_tests, error_message
                        FROM execution_suite_plan_retry_history
                        WHERE execution_suite_plan_suite_run_id = %s
                        ORDER BY attempted_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (suite_run_id, limit, offset)
                    )
                    
                    history = []
                    for row in cursor.fetchall():
                        history.append({
                            'id': row[0],
                            'retry_number': row[1],
                            'attempted_at': row[2],
                            'completed_at': row[3],
                            'status': row[4],
                            'passed_tests': row[5],
                            'failed_tests': row[6],
                            'error_message': row[7]
                        })
                    
                    return history
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting retry history: {e}")
            return []
    
    def _get_failed_test_count(self, suite_run_id: int) -> int:
        """
        Get count of failed tests in a suite run
        
        Args:
            suite_run_id: ID of the suite run
            
        Returns:
            Number of failed tests
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT failed_tests
                        FROM execution_suite_plan_suite_runs
                        WHERE id = %s
                        """,
                        (suite_run_id,)
                    )
                    
                    result = cursor.fetchone()
                    return result[0] if result else 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting failed test count: {e}")
            return 0
    
    def should_retry_based_on_threshold(
        self,
        suite_run_id: int,
        failure_percentage_threshold: float = 10.0
    ) -> bool:
        """
        Determine if suite should be retried based on failure percentage
        
        Args:
            suite_run_id: ID of the suite run
            failure_percentage_threshold: Failure percentage threshold (0-100)
            
        Returns:
            True if should retry based on threshold
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT total_tests, failed_tests
                        FROM execution_suite_plan_suite_runs
                        WHERE id = %s
                        """,
                        (suite_run_id,)
                    )
                    
                    result = cursor.fetchone()
                    if not result or result[0] == 0:
                        return False
                    
                    total_tests, failed_tests = result
                    failure_percentage = (failed_tests / total_tests) * 100
                    
                    should_retry = failure_percentage <= failure_percentage_threshold
                    self.logger.info(
                        f"Suite run {suite_run_id}: {failure_percentage:.1f}% failure rate, "
                        f"threshold: {failure_percentage_threshold}%, retry: {should_retry}"
                    )
                    
                    return should_retry
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error checking retry threshold: {e}")
            return False


# Global retry manager instance
_retry_manager_instance = None


def get_retry_manager() -> RetryManager:
    """Get or create global retry manager instance"""
    global _retry_manager_instance
    if _retry_manager_instance is None:
        _retry_manager_instance = RetryManager()
    return _retry_manager_instance
