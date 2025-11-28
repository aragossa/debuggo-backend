"""
ParallelExecutionEngine: Manages parallel execution of test suites

Features:
- Execute multiple suites in parallel
- Respect max_parallel_suites limit
- Handle suite dependencies
- Manage resource allocation
- Track execution progress
- Aggregate results
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from auroqa.Services.ExecutionPlanService import ExecutionPlanService
from auroqa.Services.SuiteService import SuiteService
from auroqa.Services.NotificationService import NotificationService
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class ParallelExecutionEngine:
    """Manages parallel execution of test suites"""
    
    def __init__(self):
        """Initialize ParallelExecutionEngine"""
        self.logger = logging.getLogger(__name__)
        self.system = System()
        self.plan_service = ExecutionPlanService()
        self.notification_service = NotificationService()
        self._lock = threading.Lock()
        self.execution_results = {}  # Track execution results
    
    def execute_plan(
        self,
        plan_id: int,
        run_id: int,
        max_parallel: int = 1
    ) -> Dict:
        """
        Execute a plan with parallel suite execution
        
        Args:
            plan_id: ID of the plan to execute
            run_id: ID of the execution run
            max_parallel: Maximum number of parallel suites
            
        Returns:
            Execution results dictionary
        """
        start_time = datetime.now()
        
        try:
            self.logger.info(f"Starting parallel execution for plan {plan_id}, run {run_id}")
            
            # Get plan and suites
            plan = self.plan_service.get_execution_plan(plan_id)
            if not plan:
                self.logger.error(f"Plan {plan_id} not found")
                self._update_run_failed(run_id, start_time, "Plan not found")
                return {'status': 'failed', 'error': 'Plan not found'}
            
            plan_name = plan.get('name', f'Plan #{plan_id}')
            
            # Send start notification
            try:
                self.notification_service.notify_execution_start(plan_id, run_id, plan_name)
            except Exception as e:
                self.logger.warning(f"Failed to send start notification: {e}")
            
            suites = self.plan_service.get_plan_suites(plan_id)
            if not suites:
                self.logger.warning(f"No suites found for plan {plan_id}")
                # Update run as passed with no suites
                self.plan_service.update_plan_run(
                    run_id=run_id,
                    status='passed',
                    completed_at=datetime.now(),
                    total_suites=0,
                    passed_suites=0,
                    failed_suites=0,
                    skipped_suites=0,
                    total_tests=0,
                    passed_tests=0,
                    failed_tests=0,
                    skipped_tests=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )
                return {'status': 'passed', 'suites': [], 'total': 0}
            
            # Add plan's environment_id to each suite as fallback
            plan_environment_id = plan.get('environment_id')
            if plan_environment_id:
                for suite in suites:
                    suite['plan_environment_id'] = plan_environment_id
            
            # Group suites by execution order
            suite_groups = self._group_suites_by_order(suites)
            
            # Execute suite groups
            results = self._execute_suite_groups(
                plan_id=plan_id,
                run_id=run_id,
                suite_groups=suite_groups,
                max_parallel=max_parallel
            )
            
            # Update plan run with final results
            final_status = 'passed' if results.get('failed_suites', 0) == 0 else 'failed'
            duration_seconds = (datetime.now() - start_time).total_seconds()
            
            self.plan_service.update_plan_run(
                run_id=run_id,
                status=final_status,
                completed_at=datetime.now(),
                total_suites=results.get('total_suites', 0),
                passed_suites=results.get('passed_suites', 0),
                failed_suites=results.get('failed_suites', 0),
                skipped_suites=results.get('skipped_suites', 0),
                total_tests=results.get('total_tests', 0),
                passed_tests=results.get('passed_tests', 0),
                failed_tests=results.get('failed_tests', 0),
                skipped_tests=results.get('skipped_tests', 0),
                duration_seconds=duration_seconds
            )
            
            # Update plan's last_executed_at
            self._update_plan_last_executed(plan_id)
            
            # Send completion notification
            try:
                self.notification_service.notify_execution_complete(
                    plan_id=plan_id,
                    run_id=run_id,
                    plan_name=plan_name,
                    status=final_status,
                    total_tests=results.get('total_tests', 0),
                    passed_tests=results.get('passed_tests', 0),
                    failed_tests=results.get('failed_tests', 0),
                    duration_seconds=duration_seconds
                )
            except Exception as e:
                self.logger.warning(f"Failed to send completion notification: {e}")
            
            self.logger.info(f"Plan {plan_id} execution completed: {results.get('passed_suites')}/{results.get('total_suites')} suites passed")
            return results
            
        except Exception as e:
            self.logger.error(f"Error executing plan {plan_id}: {e}")
            self._update_run_failed(run_id, start_time, str(e))
            return {'status': 'failed', 'error': str(e)}
    
    def _update_run_failed(self, run_id: int, start_time: datetime, error_message: str):
        """Update run as failed"""
        self.plan_service.update_plan_run(
            run_id=run_id,
            status='failed',
            completed_at=datetime.now(),
            duration_seconds=(datetime.now() - start_time).total_seconds(),
            error_message=error_message
        )
    
    def _update_plan_last_executed(self, plan_id: int):
        """Update plan's last_executed_at timestamp"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE execution_suite_plans SET last_executed_at = %s WHERE id = %s",
                        (datetime.now(), plan_id)
                    )
                    conn.commit()
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error updating plan last_executed_at: {e}")
    
    def _group_suites_by_order(self, suites: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Group suites by execution order
        
        Suites with the same execution_order can run in parallel
        Different orders run sequentially
        
        Args:
            suites: List of suite configurations
            
        Returns:
            Dictionary mapping execution_order to list of suites
        """
        groups = {}
        for suite in suites:
            order = suite.get('execution_order', 0)
            if order not in groups:
                groups[order] = []
            groups[order].append(suite)
        
        return groups
    
    def _execute_suite_groups(
        self,
        plan_id: int,
        run_id: int,
        suite_groups: Dict[int, List[Dict]],
        max_parallel: int
    ) -> Dict:
        """
        Execute suite groups sequentially, with parallel execution within groups
        
        Args:
            plan_id: Plan ID
            run_id: Run ID
            suite_groups: Grouped suites by execution order
            max_parallel: Maximum parallel suites
            
        Returns:
            Execution results
        """
        all_results = {
            'plan_id': plan_id,
            'run_id': run_id,
            'status': 'passed',
            'suite_results': [],
            'total_suites': 0,
            'passed_suites': 0,
            'failed_suites': 0,
            'skipped_suites': 0,
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'skipped_tests': 0,
            'started_at': datetime.now(),
            'completed_at': None
        }
        
        try:
            # Sort groups by execution order
            sorted_orders = sorted(suite_groups.keys())
            
            for order in sorted_orders:
                suites_in_group = suite_groups[order]
                
                # Execute suites in parallel within the group
                group_results = self._execute_suites_parallel(
                    plan_id=plan_id,
                    run_id=run_id,
                    suites=suites_in_group,
                    max_parallel=max_parallel
                )
                
                # Aggregate results
                all_results['suite_results'].extend(group_results)
                all_results['total_suites'] += len(group_results)
                
                for result in group_results:
                    if result['status'] == 'passed':
                        all_results['passed_suites'] += 1
                    elif result['status'] == 'failed':
                        all_results['failed_suites'] += 1
                    else:
                        all_results['skipped_suites'] += 1
                    
                    all_results['total_tests'] += result.get('total_tests', 0)
                    all_results['passed_tests'] += result.get('passed_tests', 0)
                    all_results['failed_tests'] += result.get('failed_tests', 0)
                    all_results['skipped_tests'] += result.get('skipped_tests', 0)
                
                # If any suite failed and we're not continuing on failure, stop
                if any(r['status'] == 'failed' for r in group_results):
                    self.logger.warning(f"Suite failure in group {order}, continuing with next group")
        
        except Exception as e:
            self.logger.error(f"Error executing suite groups: {e}")
            all_results['status'] = 'failed'
            all_results['error'] = str(e)
        
        finally:
            all_results['completed_at'] = datetime.now()
        
        return all_results
    
    def _execute_suites_parallel(
        self,
        plan_id: int,
        run_id: int,
        suites: List[Dict],
        max_parallel: int
    ) -> List[Dict]:
        """
        Execute multiple suites in parallel
        
        Args:
            plan_id: Plan ID
            run_id: Run ID
            suites: List of suites to execute
            max_parallel: Maximum parallel suites
            
        Returns:
            List of execution results
        """
        results = []
        
        # Limit parallel execution
        num_workers = min(len(suites), max_parallel)
        
        if num_workers <= 1:
            # Sequential execution
            for suite in suites:
                result = self._execute_single_suite(plan_id, run_id, suite)
                results.append(result)
        else:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_suite = {
                    executor.submit(self._execute_single_suite, plan_id, run_id, suite): suite
                    for suite in suites
                }
                
                for future in as_completed(future_to_suite):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        suite = future_to_suite[future]
                        self.logger.error(f"Error executing suite {suite['suite_id']}: {e}")
                        results.append({
                            'suite_id': suite['suite_id'],
                            'status': 'failed',
                            'error': str(e),
                            'total_tests': 0,
                            'passed_tests': 0,
                            'failed_tests': 0,
                            'skipped_tests': 0
                        })
        
        return results
    
    def _execute_single_suite(
        self,
        plan_id: int,
        run_id: int,
        suite: Dict
    ) -> Dict:
        """
        Execute a single suite
        
        Args:
            plan_id: Plan ID
            run_id: Run ID
            suite: Suite configuration
            
        Returns:
            Execution result
        """
        suite_id = suite.get('suite_id')
        start_time = datetime.now()
        
        try:
            self.logger.info(f"Executing suite {suite_id} in plan {plan_id}")
            
            # Create suite run in database
            suite_run_id = self.plan_service.create_suite_run(
                plan_run_id=run_id,
                plan_suite_id=suite.get('id'),
                suite_id=suite_id
            )
            
            if not suite_run_id:
                return {
                    'suite_id': suite_id,
                    'status': 'failed',
                    'error': 'Failed to create suite run',
                    'total_tests': 0,
                    'passed_tests': 0,
                    'failed_tests': 0,
                    'skipped_tests': 0
                }
            
            # Get test cases in suite
            conn = get_db_connection()
            try:
                suite_service = SuiteService(conn)
                test_cases = suite_service.get_suite_tests(suite_id)
            finally:
                return_db_connection(conn)
            
            if not test_cases:
                self.logger.warning(f"No test cases found in suite {suite_id}")
                result = {
                    'suite_id': suite_id,
                    'suite_run_id': suite_run_id,
                    'status': 'passed',
                    'total_tests': 0,
                    'passed_tests': 0,
                    'failed_tests': 0,
                    'skipped_tests': 0,
                    'duration_seconds': 0
                }
                self.plan_service.update_suite_run(
                    suite_run_id=suite_run_id,
                    status='passed',
                    total_tests=0,
                    passed_tests=0,
                    failed_tests=0,
                    skipped_tests=0,
                    duration_seconds=0
                )
                return result
            
            # Execute each test case
            total_tests = len(test_cases)
            passed_tests = 0
            failed_tests = 0
            skipped_tests = 0
            
            # Import TestRunner here to avoid circular imports
            from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
            
            for test_case in test_cases:
                test_case_id = test_case.get('test_case_id')
                # Priority: suite override > test case override > plan environment
                environment_id = (
                    suite.get('environment_id') or 
                    test_case.get('environment_override_id') or 
                    suite.get('plan_environment_id')
                )
                
                try:
                    self.logger.info(f"Running test case {test_case_id} in suite {suite_id} with environment {environment_id}")
                    
                    # Create TestRunner and execute test
                    runner = TestRunner(user_id="system", test_case_id=test_case_id)
                    
                    # Get environment variables if environment_id is set
                    environment_vars = None
                    if environment_id:
                        environment_vars = self._get_environment_vars(environment_id)
                    
                    # Run test case with quick_run_id for logging
                    test_result = runner.run_test_case(
                        test_case_id=test_case_id,
                        environment_vars=environment_vars,
                        quick_run_id=run_id,
                        suite_id=suite_id
                    )
                    
                    # Check result
                    if test_result and test_result.get('status') in ['completed', 'success', 'passed']:
                        passed_tests += 1
                    else:
                        failed_tests += 1
                        
                except Exception as test_error:
                    self.logger.error(f"Error running test case {test_case_id}: {test_error}")
                    failed_tests += 1
            
            # Calculate duration and status
            duration_seconds = (datetime.now() - start_time).total_seconds()
            status = 'passed' if failed_tests == 0 else 'failed'
            
            result = {
                'suite_id': suite_id,
                'suite_run_id': suite_run_id,
                'status': status,
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'skipped_tests': skipped_tests,
                'duration_seconds': duration_seconds
            }
            
            # Update suite run with results
            self.plan_service.update_suite_run(
                suite_run_id=suite_run_id,
                status=result['status'],
                total_tests=result['total_tests'],
                passed_tests=result['passed_tests'],
                failed_tests=result['failed_tests'],
                skipped_tests=result['skipped_tests'],
                duration_seconds=result['duration_seconds']
            )
            
            self.logger.info(f"Suite {suite_id} completed: {passed_tests}/{total_tests} passed")
            return result
        
        except Exception as e:
            self.logger.error(f"Error executing suite {suite_id}: {e}")
            duration_seconds = (datetime.now() - start_time).total_seconds()
            return {
                'suite_id': suite_id,
                'status': 'failed',
                'error': str(e),
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'skipped_tests': 0,
                'duration_seconds': duration_seconds
            }
    
    def _get_environment_vars(self, environment_id: int) -> Optional[Dict]:
        """Get environment variables for an environment"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT base_url, login, password, custom_variables
                        FROM environments
                        WHERE id = %s
                        """,
                        (environment_id,)
                    )
                    result = cursor.fetchone()
                    if result:
                        return {
                            'base_url': result[0],
                            'login': result[1],
                            'password': result[2],
                            'custom_variables': result[3] or {}
                        }
                    return None
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting environment vars: {e}")
            return None
    
    def get_execution_status(self, run_id: int) -> Optional[Dict]:
        """
        Get execution status for a run
        
        Args:
            run_id: Run ID
            
        Returns:
            Execution status or None
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, status, started_at, completed_at,
                               total_suites, passed_suites, failed_suites,
                               total_tests, passed_tests, failed_tests
                        FROM execution_suite_plan_runs
                        WHERE id = %s
                        """,
                        (run_id,)
                    )
                    result = cursor.fetchone()
                    if not result:
                        return None
                    
                    return {
                        'id': result[0],
                        'status': result[1],
                        'started_at': result[2],
                        'completed_at': result[3],
                        'total_suites': result[4],
                        'passed_suites': result[5],
                        'failed_suites': result[6],
                        'total_tests': result[7],
                        'passed_tests': result[8],
                        'failed_tests': result[9]
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting execution status: {e}")
            return None
    
    def cancel_execution(self, run_id: int) -> bool:
        """
        Cancel an ongoing execution
        
        Args:
            run_id: Run ID
            
        Returns:
            True if cancelled, False otherwise
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE execution_suite_plan_runs
                        SET status = 'stopped'
                        WHERE id = %s AND status = 'running'
                        """,
                        (run_id,)
                    )
                    conn.commit()
                    return cursor.rowcount > 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error cancelling execution: {e}")
            return False
    
    def get_execution_progress(self, run_id: int) -> Optional[Dict]:
        """
        Get detailed execution progress
        
        Args:
            run_id: Run ID
            
        Returns:
            Progress information or None
        """
        try:
            status = self.get_execution_status(run_id)
            if not status:
                return None
            
            progress = {
                'run_id': run_id,
                'status': status['status'],
                'total_suites': status['total_suites'],
                'completed_suites': status['passed_suites'] + status['failed_suites'],
                'passed_suites': status['passed_suites'],
                'failed_suites': status['failed_suites'],
                'total_tests': status['total_tests'],
                'completed_tests': status['passed_tests'] + status['failed_tests'],
                'passed_tests': status['passed_tests'],
                'failed_tests': status['failed_tests'],
                'progress_percentage': 0
            }
            
            # Calculate progress percentage
            if status['total_suites'] > 0:
                progress['progress_percentage'] = int(
                    (progress['completed_suites'] / status['total_suites']) * 100
                )
            
            return progress
        except Exception as e:
            self.logger.error(f"Error getting execution progress: {e}")
            return None


# Global execution engine instance
_engine_instance = None


def get_execution_engine() -> ParallelExecutionEngine:
    """Get or create global execution engine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ParallelExecutionEngine()
    return _engine_instance
