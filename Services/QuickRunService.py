"""
Quick Run Service

Provides functionality for manual/quick test execution using execution_suite_plans.
This service deprecates the direct use of test_executions table for new runs.

Features:
- Create quick run execution plans
- Execute individual test cases
- Execute multiple test cases
- Log results to execution_suite_plan_runs
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection

logger = logging.getLogger(__name__)


class QuickRunService:
    """Service for managing quick/manual test executions"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logger.info("QuickRunService initialized")
    
    def create_quick_run_plan(
        self,
        client_id: str,
        project_id: str,
        name: str,
        created_by: str,
        description: Optional[str] = None,
        auto_delete: bool = False
    ) -> Optional[int]:
        """
        Create a quick run execution plan for manual test execution.
        
        Args:
            client_id: Client UUID
            project_id: Project UUID
            name: Plan name (e.g., "Quick Run - Test Case #123")
            created_by: User UUID who created the plan
            description: Optional description
            auto_delete: If True, plan will be marked for deletion after run
            
        Returns:
            Plan ID if successful, None otherwise
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plans (
                        client_id, project_id, name, description,
                        plan_type, schedule_type, status,
                        is_quick_run, auto_delete_after_run, created_by
                    ) VALUES (
                        %s, %s, %s, %s,
                        'sequential', 'manual', 'active',
                        TRUE, %s, %s
                    ) RETURNING id
                    """,
                    (client_id, project_id, name, 
                     description or 'Quick run - manual execution',
                     auto_delete, created_by)
                )
                plan_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Created quick run plan {plan_id}")
                return plan_id
        except Exception as e:
            logger.error(f"Error creating quick run plan: {e}")
            conn.rollback()
            return None
        finally:
            return_db_connection(conn)
    
    def add_test_case_to_plan(
        self,
        plan_id: int,
        test_case_id: int,
        suite_id: Optional[int] = None,
        execution_order: int = 1
    ) -> Optional[int]:
        """
        Add a test case to an execution plan.
        
        Args:
            plan_id: Execution plan ID
            test_case_id: Test case ID to add
            suite_id: Optional suite ID if test case belongs to a suite
            execution_order: Order of execution
            
        Returns:
            ID of the created record, None if failed
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_test_cases (
                        execution_suite_plan_id, test_case_id, suite_id,
                        execution_order, status
                    ) VALUES (%s, %s, %s, %s, 'pending')
                    RETURNING id
                    """,
                    (plan_id, test_case_id, suite_id, execution_order)
                )
                record_id = cursor.fetchone()[0]
                conn.commit()
                return record_id
        except Exception as e:
            logger.error(f"Error adding test case to plan: {e}")
            conn.rollback()
            return None
        finally:
            return_db_connection(conn)
    
    def add_test_cases_to_plan(
        self,
        plan_id: int,
        test_cases: List[Dict[str, Any]]
    ) -> bool:
        """
        Add multiple test cases to an execution plan.
        
        Args:
            plan_id: Execution plan ID
            test_cases: List of dicts with test_case_id, suite_id (optional)
            
        Returns:
            True if successful, False otherwise
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                for idx, tc in enumerate(test_cases, 1):
                    cursor.execute(
                        """
                        INSERT INTO execution_suite_plan_test_cases (
                            execution_suite_plan_id, test_case_id, suite_id,
                            execution_order, status
                        ) VALUES (%s, %s, %s, %s, 'pending')
                        """,
                        (plan_id, tc['test_case_id'], 
                         tc.get('suite_id'), idx)
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding test cases to plan: {e}")
            conn.rollback()
            return False
        finally:
            return_db_connection(conn)
    
    def create_plan_run(
        self,
        plan_id: int,
        triggered_by: str = 'manual'
    ) -> Optional[int]:
        """
        Create an execution run for a plan.
        
        Args:
            plan_id: Execution plan ID
            triggered_by: Who/what triggered the run
            
        Returns:
            Run ID if successful, None otherwise
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_runs (
                        execution_suite_plan_id, started_at, status, triggered_by
                    ) VALUES (%s, %s, 'running', %s)
                    RETURNING id
                    """,
                    (plan_id, datetime.now(), triggered_by)
                )
                run_id = cursor.fetchone()[0]
                
                # Update plan status
                cursor.execute(
                    """
                    UPDATE execution_suite_plans 
                    SET status = 'active', last_executed_at = %s
                    WHERE id = %s
                    """,
                    (datetime.now(), plan_id)
                )
                conn.commit()
                return run_id
        except Exception as e:
            logger.error(f"Error creating plan run: {e}")
            conn.rollback()
            return None
        finally:
            return_db_connection(conn)
    
    def log_test_run_result(
        self,
        run_id: int,
        test_case_id: int,
        status: str,
        suite_id: Optional[int] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        log_path: Optional[str] = None,
        retry_count: int = 0
    ) -> Optional[int]:
        """
        Log a test run result.
        
        Args:
            run_id: Execution plan run ID
            test_case_id: Test case ID
            status: Result status (passed, failed, skipped, error)
            suite_id: Optional suite ID
            started_at: When test started
            completed_at: When test completed
            duration_seconds: Test duration
            error_message: Error message if failed
            screenshot_path: Path to screenshot if captured
            log_path: Path to log file
            retry_count: Number of retries
            
        Returns:
            Test run ID if successful, None otherwise
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO execution_suite_plan_test_runs (
                        execution_suite_plan_run_id, test_case_id, suite_id,
                        status, started_at, completed_at, duration_seconds,
                        error_message, screenshot_path, log_path, retry_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (run_id, test_case_id, suite_id, status,
                     started_at or datetime.now(),
                     completed_at or datetime.now(),
                     duration_seconds,
                     error_message, screenshot_path, log_path, retry_count)
                )
                test_run_id = cursor.fetchone()[0]
                conn.commit()
                return test_run_id
        except Exception as e:
            logger.error(f"Error logging test run result: {e}")
            conn.rollback()
            return None
        finally:
            return_db_connection(conn)
    
    def complete_plan_run(
        self,
        run_id: int,
        status: str = 'completed'
    ) -> bool:
        """
        Complete a plan run and update statistics.
        
        Args:
            run_id: Execution plan run ID
            status: Final status (completed, failed, cancelled)
            
        Returns:
            True if successful, False otherwise
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Get test run statistics
                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'passed' THEN 1 END) as passed,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                        COUNT(CASE WHEN status = 'skipped' THEN 1 END) as skipped
                    FROM execution_suite_plan_test_runs
                    WHERE execution_suite_plan_run_id = %s
                    """,
                    (run_id,)
                )
                stats = cursor.fetchone()
                total, passed, failed, skipped = stats
                
                # Calculate duration
                cursor.execute(
                    """
                    SELECT 
                        EXTRACT(EPOCH FROM (MAX(completed_at) - MIN(started_at)))
                    FROM execution_suite_plan_test_runs
                    WHERE execution_suite_plan_run_id = %s
                    """,
                    (run_id,)
                )
                duration = cursor.fetchone()[0] or 0
                
                # Update run
                cursor.execute(
                    """
                    UPDATE execution_suite_plan_runs
                    SET 
                        completed_at = %s,
                        status = %s,
                        total_tests = %s,
                        passed_tests = %s,
                        failed_tests = %s,
                        skipped_tests = %s,
                        duration_seconds = %s
                    WHERE id = %s
                    """,
                    (datetime.now(), status, total, passed, failed, skipped, duration, run_id)
                )
                
                # Get plan_id and update plan status
                cursor.execute(
                    "SELECT execution_suite_plan_id FROM execution_suite_plan_runs WHERE id = %s",
                    (run_id,)
                )
                plan_id = cursor.fetchone()[0]
                
                cursor.execute(
                    """
                    UPDATE execution_suite_plans
                    SET status = 'completed', updated_at = %s
                    WHERE id = %s
                    """,
                    (datetime.now(), plan_id)
                )
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error completing plan run: {e}")
            conn.rollback()
            return False
        finally:
            return_db_connection(conn)
    
    def quick_run_test_case(
        self,
        client_id: str,
        project_id: str,
        test_case_id: int,
        created_by: str,
        suite_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a quick run plan for a single test case and prepare for execution.
        
        Args:
            client_id: Client UUID
            project_id: Project UUID
            test_case_id: Test case ID to run
            created_by: User UUID
            suite_id: Optional suite ID
            
        Returns:
            Dict with plan_id, run_id, and test_case_record_id
        """
        # Create quick run plan
        plan_id = self.create_quick_run_plan(
            client_id=client_id,
            project_id=project_id,
            name=f"Quick Run - Test #{test_case_id}",
            created_by=created_by,
            auto_delete=True
        )
        
        if not plan_id:
            return {'error': 'Failed to create quick run plan'}
        
        # Add test case to plan
        tc_record_id = self.add_test_case_to_plan(
            plan_id=plan_id,
            test_case_id=test_case_id,
            suite_id=suite_id
        )
        
        if not tc_record_id:
            return {'error': 'Failed to add test case to plan'}
        
        # Create run
        run_id = self.create_plan_run(plan_id, triggered_by='manual')
        
        if not run_id:
            return {'error': 'Failed to create plan run'}
        
        return {
            'plan_id': plan_id,
            'run_id': run_id,
            'test_case_record_id': tc_record_id,
            'status': 'ready'
        }
    
    def get_quick_run_history(
        self,
        client_id: str,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get quick run history.
        
        Args:
            client_id: Client UUID
            project_id: Optional project UUID filter
            limit: Maximum number of results
            
        Returns:
            List of quick run records
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                query = """
                    SELECT 
                        esp.id as plan_id,
                        esp.name,
                        esp.status,
                        esp.created_at,
                        esp.last_executed_at,
                        espr.id as run_id,
                        espr.status as run_status,
                        espr.total_tests,
                        espr.passed_tests,
                        espr.failed_tests,
                        espr.duration_seconds
                    FROM execution_suite_plans esp
                    LEFT JOIN execution_suite_plan_runs espr 
                        ON esp.id = espr.execution_suite_plan_id
                    WHERE esp.client_id = %s
                      AND esp.is_quick_run = TRUE
                """
                params = [client_id]
                
                if project_id:
                    query += " AND esp.project_id = %s"
                    params.append(project_id)
                
                query += " ORDER BY esp.created_at DESC LIMIT %s"
                params.append(limit)
                
                cursor.execute(query, params)
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'plan_id': row[0],
                        'name': row[1],
                        'status': row[2],
                        'created_at': row[3],
                        'last_executed_at': row[4],
                        'run_id': row[5],
                        'run_status': row[6],
                        'total_tests': row[7],
                        'passed_tests': row[8],
                        'failed_tests': row[9],
                        'duration_seconds': row[10]
                    })
                
                return results
        except Exception as e:
            logger.error(f"Error getting quick run history: {e}")
            return []
        finally:
            return_db_connection(conn)
    
    def get_run_details(self, run_id: int) -> Dict[str, Any]:
        """
        Get detailed results for a specific run.
        
        Args:
            run_id: Execution plan run ID
            
        Returns:
            Dict with run details and test results
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Get run info
                cursor.execute(
                    """
                    SELECT 
                        espr.id, espr.execution_suite_plan_id, espr.started_at,
                        espr.completed_at, espr.status, espr.total_tests,
                        espr.passed_tests, espr.failed_tests, espr.skipped_tests,
                        espr.duration_seconds, espr.triggered_by,
                        esp.name as plan_name
                    FROM execution_suite_plan_runs espr
                    JOIN execution_suite_plans esp ON espr.execution_suite_plan_id = esp.id
                    WHERE espr.id = %s
                    """,
                    (run_id,)
                )
                run = cursor.fetchone()
                
                if not run:
                    return {'error': 'Run not found'}
                
                # Get test results
                cursor.execute(
                    """
                    SELECT 
                        id, test_case_id, suite_id, status,
                        started_at, completed_at, duration_seconds,
                        error_message, screenshot_path, log_path, retry_count
                    FROM execution_suite_plan_test_runs
                    WHERE execution_suite_plan_run_id = %s
                    ORDER BY id
                    """,
                    (run_id,)
                )
                
                test_results = []
                for row in cursor.fetchall():
                    test_results.append({
                        'id': row[0],
                        'test_case_id': row[1],
                        'suite_id': row[2],
                        'status': row[3],
                        'started_at': row[4],
                        'completed_at': row[5],
                        'duration_seconds': row[6],
                        'error_message': row[7],
                        'screenshot_path': row[8],
                        'log_path': row[9],
                        'retry_count': row[10]
                    })
                
                return {
                    'run_id': run[0],
                    'plan_id': run[1],
                    'plan_name': run[11],
                    'started_at': run[2],
                    'completed_at': run[3],
                    'status': run[4],
                    'total_tests': run[5],
                    'passed_tests': run[6],
                    'failed_tests': run[7],
                    'skipped_tests': run[8],
                    'duration_seconds': run[9],
                    'triggered_by': run[10],
                    'test_results': test_results
                }
        except Exception as e:
            logger.error(f"Error getting run details: {e}")
            return {'error': str(e)}
        finally:
            return_db_connection(conn)
