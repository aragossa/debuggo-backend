"""
ExecutionPlanService: Manages execution plans with scheduling, parallel execution, and auto-retry

Features:
- Create and manage execution plans
- Schedule execution (manual, once, recurring, cron)
- Parallel suite execution
- Automatic retry with configurable delays
- Execution history and statistics
- Notifications and webhooks
"""

import logging
import json
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class ExecutionPlanService:
    """Service for managing execution plans"""
    
    def __init__(self, conn=None):
        """Initialize ExecutionPlanService"""
        self.logger = logging.getLogger(__name__)
        self.system = System()
        self.conn = conn
        self._should_close_conn = conn is None
    
    def _get_connection(self):
        """Get database connection"""
        if self.conn is None:
            self.conn = get_db_connection()
            self._should_close_conn = True
        return self.conn
    
    def _close_connection(self):
        """Close database connection if we opened it"""
        if self._should_close_conn and self.conn:
            return_db_connection(self.conn)
            self.conn = None
    
    def create_execution_plan(
        self,
        client_id: str,
        project_id: str,
        name: str,
        description: Optional[str] = None,
        plan_type: str = 'sequential',
        schedule_type: str = 'manual',
        max_parallel_suites: int = 1,
        max_retries: int = 0,
        retry_delay_seconds: int = 5,
        timeout_seconds: int = 3600,
        created_by: str = None,
        environment_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Create a new execution plan
        
        Args:
            client_id: Client ID
            project_id: Project ID
            name: Plan name
            description: Plan description
            plan_type: Type of plan (sequential, parallel, hybrid)
            schedule_type: Schedule type (manual, once, recurring, cron)
            max_parallel_suites: Maximum parallel suites
            max_retries: Maximum retry attempts
            retry_delay_seconds: Delay between retries
            timeout_seconds: Execution timeout
            created_by: User ID who created the plan
            environment_id: Environment ID for test execution
            
        Returns:
            Plan ID or None if creation failed
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plans (
                        client_id, project_id, name, description, plan_type,
                        schedule_type, max_parallel_suites, max_retries,
                        retry_delay_seconds, timeout_seconds, created_by, environment_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (client_id, project_id, name, description, plan_type,
                     schedule_type, max_parallel_suites, max_retries,
                     retry_delay_seconds, timeout_seconds, created_by, environment_id)
                )
                result = cursor.fetchone()
                plan_id = result[0] if result else None
                conn.commit()
                
                if plan_id:
                    self.logger.info(f"Created execution plan {plan_id}: {name}")
                
                return plan_id
        except Exception as e:
            self.logger.error(f"Error creating execution plan: {e}")
            return None
        finally:
            self._close_connection()
    
    def get_execution_plan(self, plan_id: int) -> Optional[Dict]:
        """Get execution plan details"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, client_id, project_id, name, description, plan_type,
                           schedule_type, scheduled_at, cron_expression, recurrence_pattern,
                           max_parallel_suites, max_retries, retry_delay_seconds,
                           timeout_seconds, status, created_by, created_at, updated_at,
                           last_executed_at, next_execution_at, environment_id
                    FROM execution_suite_plans
                    WHERE id = %s AND is_active = TRUE
                    """,
                    (plan_id,)
                )
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'id': result[0],
                    'client_id': result[1],
                    'project_id': result[2],
                    'name': result[3],
                    'description': result[4],
                    'plan_type': result[5],
                    'schedule_type': result[6],
                    'scheduled_at': result[7],
                    'cron_expression': result[8],
                    'recurrence_pattern': result[9],
                    'max_parallel_suites': result[10],
                    'max_retries': result[11],
                    'retry_delay_seconds': result[12],
                    'timeout_seconds': result[13],
                    'status': result[14],
                    'created_by': result[15],
                    'created_at': result[16],
                    'updated_at': result[17],
                    'last_executed_at': result[18],
                    'next_execution_at': result[19],
                    'environment_id': result[20]
                }
        except Exception as e:
            self.logger.error(f"Error getting execution plan: {e}")
            return None
        finally:
            self._close_connection()
    
    def list_execution_plans(
        self,
        client_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple:
        """List execution plans"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Build WHERE clause
                where_clauses = ["is_active = TRUE", "client_id = %s"]
                params = [client_id]
                
                if project_id:
                    where_clauses.append("project_id = %s")
                    params.append(project_id)
                if status:
                    where_clauses.append("status = %s")
                    params.append(status)
                
                where_clause = " AND ".join(where_clauses)
                
                # Get total count
                cursor.execute(f"SELECT COUNT(*) FROM execution_suite_plans WHERE {where_clause}", params)
                total = cursor.fetchone()[0]
                
                # Get paginated results
                params.extend([limit, offset])
                cursor.execute(
                    f"""
                    SELECT id, client_id, project_id, name, description, plan_type,
                           schedule_type, max_parallel_suites, max_retries, 
                           retry_delay_seconds, timeout_seconds, status, 
                           created_at, updated_at, last_executed_at, next_execution_at,
                           environment_id
                    FROM execution_suite_plans
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params
                )
                
                plans = []
                for row in cursor.fetchall():
                    plans.append({
                        'id': row[0],
                        'client_id': row[1],
                        'project_id': row[2],
                        'name': row[3],
                        'description': row[4],
                        'plan_type': row[5],
                        'schedule_type': row[6],
                        'max_parallel_suites': row[7],
                        'max_retries': row[8],
                        'retry_delay_seconds': row[9],
                        'timeout_seconds': row[10],
                        'status': row[11],
                        'created_at': row[12],
                        'updated_at': row[13],
                        'last_executed_at': row[14],
                        'next_execution_at': row[15],
                        'environment_id': row[16]
                    })
                
                return plans, total
        except Exception as e:
            self.logger.error(f"Error listing execution plans: {e}")
            return [], 0
        finally:
            self._close_connection()
    
    def add_suite_to_plan(
        self,
        plan_id: int,
        suite_id: int,
        execution_order: int,
        environment_id: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> Optional[int]:
        """Add test suite to execution plan"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_suites (
                        execution_suite_plan_id, test_suite_id, execution_order,
                        environment_id, timeout_seconds, max_retries
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (plan_id, suite_id, execution_order, environment_id, timeout_seconds, max_retries)
                )
                result = cursor.fetchone()
                suite_plan_id = result[0] if result else None
                conn.commit()
                
                if suite_plan_id:
                    self.logger.info(f"Added suite {suite_id} to plan {plan_id}")
                
                return suite_plan_id
        except Exception as e:
            self.logger.error(f"Error adding suite to plan: {e}")
            return None
        finally:
            self._close_connection()
    
    def get_plan_suites(self, plan_id: int) -> List[Dict]:
        """Get all suites in an execution plan"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, test_suite_id, execution_order, environment_id,
                           timeout_seconds, max_retries, status
                    FROM execution_suite_plan_suites
                    WHERE execution_suite_plan_id = %s
                    ORDER BY execution_order ASC
                    """,
                    (plan_id,)
                )
                
                suites = []
                for row in cursor.fetchall():
                    suites.append({
                        'id': row[0],
                        'suite_id': row[1],
                        'execution_order': row[2],
                        'environment_id': row[3],
                        'timeout_seconds': row[4],
                        'max_retries': row[5],
                        'status': row[6]
                    })
                
                return suites
        except Exception as e:
            self.logger.error(f"Error getting plan suites: {e}")
            return []
        finally:
            self._close_connection()
    
    def create_plan_run(
        self,
        plan_id: int,
        triggered_by: str = 'manual',
        triggered_by_user_id: Optional[str] = None
    ) -> Optional[int]:
        """Create a new execution plan run"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_runs (
                        execution_suite_plan_id, started_at, status, triggered_by, triggered_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (plan_id, datetime.now(), 'running', triggered_by, triggered_by_user_id)
                )
                result = cursor.fetchone()
                run_id = result[0] if result else None
                conn.commit()
                
                if run_id:
                    self.logger.info(f"Created execution plan run {run_id} for plan {plan_id}")
                
                return run_id
        except Exception as e:
            self.logger.error(f"Error creating plan run: {e}")
            return None
        finally:
            self._close_connection()
    
    def update_plan_run(
        self,
        run_id: int,
        status: str,
        completed_at: Optional[datetime] = None,
        total_suites: Optional[int] = None,
        passed_suites: Optional[int] = None,
        failed_suites: Optional[int] = None,
        skipped_suites: Optional[int] = None,
        total_tests: Optional[int] = None,
        passed_tests: Optional[int] = None,
        failed_tests: Optional[int] = None,
        skipped_tests: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update execution plan run"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE execution_suite_plan_runs
                    SET status = %s, completed_at = %s, total_suites = %s,
                        passed_suites = %s, failed_suites = %s, skipped_suites = %s,
                        total_tests = %s, passed_tests = %s, failed_tests = %s,
                        skipped_tests = %s, duration_seconds = %s, error_message = %s
                    WHERE id = %s
                    """,
                    (status, completed_at, total_suites, passed_suites, failed_suites,
                     skipped_suites, total_tests, passed_tests, failed_tests,
                     skipped_tests, duration_seconds, error_message, run_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error updating plan run: {e}")
            return False
        finally:
            self._close_connection()
    
    def create_suite_run(
        self,
        plan_run_id: int,
        plan_suite_id: int,
        suite_id: int
    ) -> Optional[int]:
        """Create a new suite run within a plan run"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_suite_runs (
                        execution_suite_plan_run_id, execution_suite_plan_suite_id, test_suite_id,
                        started_at, status
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (plan_run_id, plan_suite_id, suite_id, datetime.now(), 'running')
                )
                result = cursor.fetchone()
                suite_run_id = result[0] if result else None
                conn.commit()
                
                return suite_run_id
        except Exception as e:
            self.logger.error(f"Error creating suite run: {e}")
            return None
        finally:
            self._close_connection()
    
    def update_suite_run(
        self,
        suite_run_id: int,
        status: str,
        completed_at: Optional[datetime] = None,
        total_tests: Optional[int] = None,
        passed_tests: Optional[int] = None,
        failed_tests: Optional[int] = None,
        skipped_tests: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        retry_count: Optional[int] = None
    ) -> bool:
        """Update suite run"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE execution_suite_plan_suite_runs
                    SET status = %s, completed_at = %s, total_tests = %s,
                        passed_tests = %s, failed_tests = %s, skipped_tests = %s,
                        duration_seconds = %s, error_message = %s, retry_count = %s
                    WHERE id = %s
                    """,
                    (status, completed_at, total_tests, passed_tests, failed_tests,
                     skipped_tests, duration_seconds, error_message, retry_count, suite_run_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error updating suite run: {e}")
            return False
        finally:
            self._close_connection()
    
    def log_retry_attempt(
        self,
        suite_run_id: int,
        retry_number: int,
        status: str,
        passed_tests: Optional[int] = None,
        failed_tests: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[int]:
        """Log a retry attempt"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_retry_history (
                        execution_suite_plan_suite_run_id, retry_number, attempted_at,
                        completed_at, status, passed_tests, failed_tests, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (suite_run_id, retry_number, datetime.now(), datetime.now(),
                     status, passed_tests, failed_tests, error_message)
                )
                result = cursor.fetchone()
                retry_id = result[0] if result else None
                conn.commit()
                
                return retry_id
        except Exception as e:
            self.logger.error(f"Error logging retry attempt: {e}")
            return None
        finally:
            self._close_connection()
    
    def get_plan_statistics(self, plan_id: int) -> Optional[Dict]:
        """Get execution plan statistics"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, name, status, total_suites, total_runs,
                           passed_runs, failed_runs, last_executed_at, next_execution_at
                    FROM v_execution_suite_plan_stats
                    WHERE id = %s
                    """,
                    (plan_id,)
                )
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'id': result[0],
                    'name': result[1],
                    'status': result[2],
                    'total_suites': result[3],
                    'total_runs': result[4],
                    'passed_runs': result[5],
                    'failed_runs': result[6],
                    'last_executed_at': result[7],
                    'next_execution_at': result[8]
                }
        except Exception as e:
            self.logger.error(f"Error getting plan statistics: {e}")
            return None
        finally:
            self._close_connection()
    
    def get_recent_runs(self, limit: int = 50) -> List[Dict]:
        """Get recent execution plan runs"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, plan_name, status, started_at, completed_at,
                           duration_seconds, total_suites, passed_suites, failed_suites,
                           total_tests, passed_tests, failed_tests, triggered_by
                    FROM v_recent_execution_suite_plan_runs
                    LIMIT %s
                    """,
                    (limit,)
                )
                
                runs = []
                for row in cursor.fetchall():
                    runs.append({
                        'id': row[0],
                        'plan_name': row[1],
                        'status': row[2],
                        'started_at': row[3],
                        'completed_at': row[4],
                        'duration_seconds': row[5],
                        'total_suites': row[6],
                        'passed_suites': row[7],
                        'failed_suites': row[8],
                        'total_tests': row[9],
                        'passed_tests': row[10],
                        'failed_tests': row[11],
                        'triggered_by': row[12]
                    })
                
                return runs
        except Exception as e:
            self.logger.error(f"Error getting recent runs: {e}")
            return []
        finally:
            self._close_connection()
    
    def update_plan_status(self, plan_id: int, status: str) -> bool:
        """Update execution plan status"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE execution_suite_plans
                    SET status = %s
                    WHERE id = %s
                    """,
                    (status, plan_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error updating plan status: {e}")
            return False
        finally:
            self._close_connection()
