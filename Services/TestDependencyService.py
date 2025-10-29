import logging
import psycopg2
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from Utils.System import System
from Services.ApiTestExecutor import ApiTestExecutor


class TestDependencyService:
    """Service to handle test case dependencies and preconditions"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system = System()
    
    @contextmanager
    def get_db_connection(self):
        """Context manager for database connections."""
        connection = None
        try:
            connection = System.get_db_connection()
            yield connection
        finally:
            if connection:
                System._pool.putconn(connection)
    
    def get_test_dependencies(self, test_case_id: int, dependency_type: str = 'precondition') -> List[Dict[str, Any]]:
        """
        Get all dependencies for a test case, ordered by execution_order.
        
        Args:
            test_case_id: The test case to get dependencies for
            dependency_type: 'precondition' or 'teardown'
            
        Returns:
            List of dependency dictionaries with test case info
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            td.id,
                            td.prerequisite_test_case_id,
                            td.dependency_type,
                            td.execution_order,
                            tc.name as prerequisite_name,
                            tc.description as prerequisite_description,
                            tc.test_type as prerequisite_type,
                            tc.client_id,
                            tc.project_id
                        FROM test_dependencies td
                        JOIN test_cases tc ON td.prerequisite_test_case_id = tc.id
                        WHERE td.dependent_test_case_id = %s 
                        AND td.dependency_type = %s
                        ORDER BY td.execution_order ASC
                    """, (test_case_id, dependency_type))
                    
                    results = cursor.fetchall()
                    dependencies = []
                    
                    for row in results:
                        dependencies.append({
                            'dependency_id': row[0],
                            'prerequisite_test_case_id': row[1],
                            'dependency_type': row[2],
                            'execution_order': row[3],
                            'prerequisite_name': row[4],
                            'prerequisite_description': row[5],
                            'prerequisite_type': row[6],
                            'client_id': row[7],
                            'project_id': row[8]
                        })
                    
                    return dependencies
                    
        except Exception as e:
            self.logger.error(f"Error fetching test dependencies for test case {test_case_id}: {str(e)}")
            return []
    
    def add_test_dependency(self, dependent_test_case_id: int, prerequisite_test_case_id: int, 
                           dependency_type: str = 'precondition', execution_order: int = 1) -> bool:
        """
        Add a new test dependency.
        
        Args:
            dependent_test_case_id: The test case that depends on the prerequisite
            prerequisite_test_case_id: The test case that must be executed first
            dependency_type: 'precondition' or 'teardown'
            execution_order: Order of execution when multiple dependencies exist
            
        Returns:
            True if dependency was added successfully, False otherwise
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO test_dependencies 
                        (dependent_test_case_id, prerequisite_test_case_id, dependency_type, execution_order)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (dependent_test_case_id, prerequisite_test_case_id, dependency_type)
                        DO UPDATE SET execution_order = EXCLUDED.execution_order
                    """, (dependent_test_case_id, prerequisite_test_case_id, dependency_type, execution_order))
                    
                    conn.commit()
                    self.logger.info(f"Added {dependency_type} dependency: test {dependent_test_case_id} depends on test {prerequisite_test_case_id}")
                    return True
                    
        except Exception as e:
            self.logger.error(f"Error adding test dependency: {str(e)}")
            return False
    
    def remove_test_dependency(self, dependent_test_case_id: int, prerequisite_test_case_id: int, 
                              dependency_type: str = 'precondition') -> bool:
        """
        Remove a test dependency.
        
        Args:
            dependent_test_case_id: The dependent test case
            prerequisite_test_case_id: The prerequisite test case
            dependency_type: 'precondition' or 'teardown'
            
        Returns:
            True if dependency was removed successfully, False otherwise
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM test_dependencies 
                        WHERE dependent_test_case_id = %s 
                        AND prerequisite_test_case_id = %s 
                        AND dependency_type = %s
                    """, (dependent_test_case_id, prerequisite_test_case_id, dependency_type))
                    
                    conn.commit()
                    self.logger.info(f"Removed {dependency_type} dependency: test {dependent_test_case_id} no longer depends on test {prerequisite_test_case_id}")
                    return True
                    
        except Exception as e:
            self.logger.error(f"Error removing test dependency: {str(e)}")
            return False
    
    def delete_test_dependency(self, dependency_id: int) -> bool:
        """
        Delete a test dependency by its ID.
        
        Args:
            dependency_id: The ID of the dependency to delete
            
        Returns:
            True if dependency was deleted successfully, False otherwise
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM test_dependencies 
                        WHERE id = %s
                    """, (dependency_id,))
                    
                    rows_affected = cursor.rowcount
                    conn.commit()
                    
                    if rows_affected > 0:
                        self.logger.info(f"Deleted test dependency with ID: {dependency_id}")
                        return True
                    else:
                        self.logger.warning(f"No dependency found with ID: {dependency_id}")
                        return False
                    
        except Exception as e:
            self.logger.error(f"Error deleting test dependency with ID {dependency_id}: {str(e)}")
            return False
    
    def execute_preconditions(self, test_case_id: int, environment_vars: Optional[Dict] = None, 
                             user_id: Optional[int] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Execute all preconditions for a test case before running the main test.
        
        Args:
            test_case_id: The test case to execute preconditions for
            environment_vars: Environment variables to pass to precondition tests
            user_id: User ID for test execution tracking
            
        Returns:
            Tuple of (success, results_list)
            - success: True if all preconditions passed, False if any failed
            - results_list: List of execution results for each precondition
        """
        preconditions = self.get_test_dependencies(test_case_id, 'precondition')
        
        if not preconditions:
            self.logger.info(f"No preconditions found for test case {test_case_id}")
            return True, []
        
        self.logger.info(f"Executing {len(preconditions)} preconditions for test case {test_case_id}")
        
        results = []
        all_passed = True
        
        for precondition in preconditions:
            prerequisite_id = precondition['prerequisite_test_case_id']
            prerequisite_type = precondition['prerequisite_type']
            prerequisite_name = precondition['prerequisite_name']
            
            self.logger.info(f"Executing precondition: {prerequisite_name} (ID: {prerequisite_id}, Type: {prerequisite_type})")
            
            try:
                if prerequisite_type == 'api':
                    # Execute API test precondition
                    result = self._execute_api_precondition(prerequisite_id, environment_vars)
                elif prerequisite_type == 'ui':
                    # Execute UI test precondition
                    result = self._execute_ui_precondition(prerequisite_id, environment_vars, user_id)
                else:
                    self.logger.warning(f"Unknown test type '{prerequisite_type}' for precondition {prerequisite_id}")
                    result = {
                        'success': False,
                        'error': f"Unknown test type: {prerequisite_type}",
                        'test_case_id': prerequisite_id,
                        'test_name': prerequisite_name,
                        'test_type': prerequisite_type
                    }
                
                results.append(result)
                
                if not result.get('success', False):
                    all_passed = False
                    self.logger.error(f"Precondition failed: {prerequisite_name} (ID: {prerequisite_id})")
                    # Stop executing remaining preconditions on first failure
                    break
                else:
                    self.logger.info(f"Precondition passed: {prerequisite_name} (ID: {prerequisite_id})")
                    
            except Exception as e:
                self.logger.error(f"Exception during precondition execution for {prerequisite_id}: {str(e)}")
                result = {
                    'success': False,
                    'error': str(e),
                    'test_case_id': prerequisite_id,
                    'test_name': prerequisite_name,
                    'test_type': prerequisite_type
                }
                results.append(result)
                all_passed = False
                break
        
        return all_passed, results
    
    def _execute_api_precondition(self, test_case_id: int, environment_vars: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute an API test case as a precondition."""
        try:
            api_executor = ApiTestExecutor(test_case_id, environment_vars)
            result = api_executor.execute_test_case()
            success = result.get('success', False)
            
            return {
                'success': success,
                'test_case_id': test_case_id,
                'test_type': 'api',
                'result': result,
                'error': None if success else result.get('error', 'API test failed')
            }
            
        except Exception as e:
            return {
                'success': False,
                'test_case_id': test_case_id,
                'test_type': 'api',
                'error': str(e)
            }
    
    def _execute_ui_precondition(self, test_case_id: int, environment_vars: Optional[Dict] = None, 
                                user_id: Optional[int] = None) -> Dict[str, Any]:
        """Execute a UI test case as a precondition."""
        try:
            # Import TestRunner locally to avoid circular import
            from Utils.BrowserAutomation.TestRunner import TestRunner
            
            test_runner = TestRunner(user_id=user_id, test_case_id=test_case_id)
            
            # Run the UI test case
            result = test_runner.run_test_case(test_case_id, environment_vars)
            
            success = result.get('status') == 'passed'
            
            return {
                'success': success,
                'test_case_id': test_case_id,
                'test_type': 'ui',
                'result': result,
                'error': None if success else result.get('stderr', 'UI test failed')
            }
            
        except Exception as e:
            return {
                'success': False,
                'test_case_id': test_case_id,
                'test_type': 'ui',
                'error': str(e)
            }
    
    def execute_teardown(self, test_case_id: int, environment_vars: Optional[Dict] = None, 
                        user_id: Optional[int] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Execute all teardown actions for a test case after the main test completes.
        
        Args:
            test_case_id: The test case to execute teardown for
            environment_vars: Environment variables to pass to teardown tests
            user_id: User ID for test execution tracking
            
        Returns:
            Tuple of (success, results_list)
            - success: True if all teardowns passed, False if any failed
            - results_list: List of execution results for each teardown
        """
        teardowns = self.get_test_dependencies(test_case_id, 'teardown')
        
        if not teardowns:
            self.logger.info(f"No teardown actions found for test case {test_case_id}")
            return True, []
        
        self.logger.info(f"Executing {len(teardowns)} teardown actions for test case {test_case_id}")
        
        results = []
        all_passed = True
        
        # Execute teardowns even if some fail (cleanup should continue)
        for teardown in teardowns:
            prerequisite_id = teardown['prerequisite_test_case_id']
            prerequisite_type = teardown['prerequisite_type']
            prerequisite_name = teardown['prerequisite_name']
            
            self.logger.info(f"Executing teardown: {prerequisite_name} (ID: {prerequisite_id}, Type: {prerequisite_type})")
            
            try:
                if prerequisite_type == 'api':
                    result = self._execute_api_precondition(prerequisite_id, environment_vars)
                elif prerequisite_type == 'ui':
                    result = self._execute_ui_precondition(prerequisite_id, environment_vars, user_id)
                else:
                    result = {
                        'success': False,
                        'error': f"Unknown test type: {prerequisite_type}",
                        'test_case_id': prerequisite_id,
                        'test_name': prerequisite_name,
                        'test_type': prerequisite_type
                    }
                
                results.append(result)
                
                if not result.get('success', False):
                    all_passed = False
                    self.logger.warning(f"Teardown failed (continuing): {prerequisite_name} (ID: {prerequisite_id})")
                else:
                    self.logger.info(f"Teardown passed: {prerequisite_name} (ID: {prerequisite_id})")
                    
            except Exception as e:
                self.logger.error(f"Exception during teardown execution for {prerequisite_id}: {str(e)}")
                result = {
                    'success': False,
                    'error': str(e),
                    'test_case_id': prerequisite_id,
                    'test_name': prerequisite_name,
                    'test_type': prerequisite_type
                }
                results.append(result)
                all_passed = False
        
        return all_passed, results
    
    def has_dependencies(self, test_case_id: int) -> bool:
        """
        Check if a test case has any dependencies (preconditions or teardowns).
        
        Args:
            test_case_id: The test case to check
            
        Returns:
            True if the test case has dependencies, False otherwise
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) FROM test_dependencies 
                        WHERE dependent_test_case_id = %s
                    """, (test_case_id,))
                    
                    count = cursor.fetchone()[0]
                    return count > 0
                    
        except Exception as e:
            self.logger.error(f"Error checking dependencies for test case {test_case_id}: {str(e)}")
            return False
    
    def get_dependency_chain(self, test_case_id: int, dependency_type: str = 'precondition', 
                           visited: Optional[set] = None) -> List[int]:
        """
        Get the full dependency chain for a test case, detecting circular dependencies.
        
        Args:
            test_case_id: The test case to get the chain for
            dependency_type: 'precondition' or 'teardown'
            visited: Set of already visited test case IDs (for circular dependency detection)
            
        Returns:
            List of test case IDs in execution order
        """
        if visited is None:
            visited = set()
        
        if test_case_id in visited:
            self.logger.error(f"Circular dependency detected for test case {test_case_id}")
            return []
        
        visited.add(test_case_id)
        chain = []
        
        dependencies = self.get_test_dependencies(test_case_id, dependency_type)
        
        for dep in dependencies:
            prerequisite_id = dep['prerequisite_test_case_id']
            # Recursively get dependencies of prerequisites
            sub_chain = self.get_dependency_chain(prerequisite_id, dependency_type, visited.copy())
            chain.extend(sub_chain)
            if prerequisite_id not in chain:
                chain.append(prerequisite_id)
        
        visited.remove(test_case_id)
        return chain
