import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection, get_db_connection_context
import psycopg2.extras


class TestExecutionService:
    """Service for managing test executions with status tracking and test runs association"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def create_execution(self, name: str, description: str, project_id: str, client_id: str, created_by: int) -> Dict[str, Any]:
        """Create a new test execution"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """
                INSERT INTO test_executions (name, description, project_id, client_id, created_by, status)
                VALUES (%s, %s, %s, %s, %s, 'New')
                RETURNING id, name, description, status, project_id, client_id, created_by, created_at, updated_at
            """
            
            cursor.execute(query, (name, description, project_id, client_id, created_by))
            result = cursor.fetchone()
            conn.commit()
            return dict(result)
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error creating execution: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def get_executions_by_project(self, project_id: str, client_id: str) -> List[Dict[str, Any]]:
        """Get all executions for a specific project with test runs count"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """SELECT te.*, u.full_name as created_by_name, p.name as project_name, COUNT(tr.id) as test_runs_count
                FROM test_executions te
                LEFT JOIN users u ON te.created_by = u.id
                LEFT JOIN projects p ON te.project_id = p.id
                LEFT JOIN test_runs tr ON tr.execution_id = te.id
                WHERE te.project_id = %s AND te.client_id = %s
                GROUP BY te.id, u.full_name, p.name
                ORDER BY te.created_at DESC"""
            
            cursor.execute(query, (project_id, client_id))
            results = cursor.fetchall()
            executions = [dict(row) for row in results]
            
            # Convert datetime objects to ISO strings
            for execution in executions:
                for key, value in execution.items():
                    if isinstance(value, datetime):
                        execution[key] = value.isoformat()
            
            self.logger.info(f"Retrieved {len(executions)} executions for project {project_id}")
            return executions
        except Exception as e:
            self.logger.error(f"Error getting executions for project {project_id}: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def get_project_executions(self, project_id: str, client_id: str) -> List[Dict[str, Any]]:
        """Get all executions for a specific project with test runs count"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """SELECT te.*, u.full_name as created_by_name, p.name as project_name, COUNT(tr.id) as test_runs_count
                FROM test_executions te
                LEFT JOIN users u ON te.created_by = u.id
                LEFT JOIN projects p ON te.project_id = p.id
                LEFT JOIN test_runs tr ON tr.execution_id = te.id
                WHERE te.project_id = %s AND te.client_id = %s
                GROUP BY te.id, u.full_name, p.name
                ORDER BY te.created_at DESC"""
            
            cursor.execute(query, (project_id, client_id))
            results = cursor.fetchall()
            executions = [dict(row) for row in results]
            
            # Convert datetime objects to ISO strings
            for execution in executions:
                for key, value in execution.items():
                    if isinstance(value, datetime):
                        execution[key] = value.isoformat()
            
            self.logger.info(f"Retrieved {len(executions)} executions for project {project_id}")
            return executions
        except Exception as e:
            self.logger.error(f"Error getting executions for project {project_id}: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def get_execution_by_id(self, execution_id: str, client_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific execution by ID"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """SELECT te.*, u.full_name as created_by_name, p.name as project_name
                FROM test_executions te
                LEFT JOIN users u ON te.created_by = u.id
                LEFT JOIN projects p ON te.project_id = p.id
                WHERE te.id = %s AND te.client_id = %s"""
            
            cursor.execute(query, (execution_id, client_id))
            result = cursor.fetchone()
            execution = dict(result) if result else None
            
            # Convert datetime objects to ISO strings
            if execution:
                for key, value in execution.items():
                    if isinstance(value, datetime):
                        execution[key] = value.isoformat()
            
            return execution
        except Exception as e:
            self.logger.error(f"Error getting execution {execution_id}: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def update_execution_status(self, execution_id: str, status: str, client_id: str) -> bool:
        """Update execution status and set appropriate timestamps"""
        conn = None
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
            
            # Set timestamp field based on status
            if status == 'In Progress':
                timestamp_field = 'started_at'
            elif status == 'Done':
                timestamp_field = 'completed_at'
            else:
                timestamp_field = None
            
            if timestamp_field:
                query = f"""UPDATE test_executions 
                    SET status = %s, {timestamp_field} = CURRENT_TIMESTAMP 
                    WHERE id = %s AND client_id = %s"""
            else:
                query = """UPDATE test_executions 
                    SET status = %s 
                    WHERE id = %s AND client_id = %s"""
            
            cursor.execute(query, (status, execution_id, client_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error updating execution {execution_id} status: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def delete_execution(self, execution_id: int, client_id: str) -> bool:
        """Delete an execution (only if no test runs are associated)"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Check if there are any test runs associated with this execution
            count_query = """SELECT COUNT(*) as count FROM test_runs WHERE execution_id = %s"""
            cursor.execute(count_query, (execution_id,))
            count_result = cursor.fetchone()
            
            if count_result and count_result['count'] > 0:
                raise Exception("Cannot delete execution with test runs")
            
            # Delete the execution
            delete_query = """DELETE FROM test_executions WHERE id = %s AND client_id = %s"""
            cursor.execute(delete_query, (execution_id, client_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting execution {execution_id}: {e}")
            raise

    def get_executions_for_dropdown(self, project_id: str, client_id: str) -> List[Dict[str, Any]]:
        """Get all executions for a project (for execution selection dropdown)"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """SELECT id, name, status, created_at
                FROM test_executions 
                WHERE project_id = %s AND client_id = %s
                ORDER BY created_at DESC
                LIMIT 10"""
            
            cursor.execute(query, (project_id, client_id))
            results = cursor.fetchall()
            executions = [dict(row) for row in results]
            
            # Convert datetime objects to ISO strings
            for execution in executions:
                for key, value in execution.items():
                    if isinstance(value, datetime):
                        execution[key] = value.isoformat()
            
            return executions
        except Exception as e:
            self.logger.error(f"Error getting in-progress executions for project {project_id}: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def get_in_progress_executions(self, project_id: str, client_id: str) -> List[Dict[str, Any]]:
        """Get all in-progress executions for a specific project"""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """SELECT te.*, u.full_name as created_by_name, p.name as project_name, COUNT(tr.id) as test_runs_count
                FROM test_executions te
                LEFT JOIN users u ON te.created_by = u.id
                LEFT JOIN projects p ON te.project_id = p.id
                LEFT JOIN test_runs tr ON tr.execution_id = te.id
                WHERE te.project_id = %s AND te.client_id = %s AND te.status = 'In Progress'
                GROUP BY te.id, u.full_name, p.name
                ORDER BY te.created_at DESC"""
            
            cursor.execute(query, (project_id, client_id))
            results = cursor.fetchall()
            executions = [dict(row) for row in results]
            
            # Convert datetime objects to ISO strings
            for execution in executions:
                for key, value in execution.items():
                    if isinstance(value, datetime):
                        execution[key] = value.isoformat()
            
            self.logger.info(f"Retrieved {len(executions)} in-progress executions for project {project_id}")
            return executions
        except Exception as e:
            self.logger.error(f"Error getting in-progress executions for project {project_id}: {e}")
            raise

    def get_execution_test_runs(self, execution_id: int, client_id: str) -> Dict[str, Any]:
        """Get all test runs for a specific execution grouped by test case"""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = """SELECT tr.id, tr.test_case_id, tr.run_date as created_at, tr.result as status, 
                       tr.exception, tr.duration, tr.stdout, tr.stderr, tr.additional_info, tr.execution_id,
                       tc.name as test_case_name, tc.type as test_case_type, tc.description as test_case_description
                FROM test_runs tr
                LEFT JOIN test_cases tc ON tr.test_case_id = tc.id
                WHERE tr.execution_id = %s AND tc.client_id = %s
                ORDER BY tc.name ASC, tr.run_date DESC"""
            
            cursor.execute(query, (execution_id, client_id))
            results = cursor.fetchall()
            
            # Group test runs by test case
            test_cases = {}
            for row in results:
                test_case_id = row['test_case_id']
                
                # Create test case entry if not exists
                if test_case_id not in test_cases:
                    test_cases[test_case_id] = {
                        'id': test_case_id,
                        'name': row['test_case_name'],
                        'type': row['test_case_type'],
                        'description': row['test_case_description'],
                        'test_runs': []
                    }
                
                # Add test run to test case
                test_run = dict(row)
                # Convert datetime objects to ISO strings
                for key, value in test_run.items():
                    if isinstance(value, datetime):
                        test_run[key] = value.isoformat()
                
                test_cases[test_case_id]['test_runs'].append(test_run)
            
            return {'test_cases': list(test_cases.values())}
        except Exception as e:
            self.logger.error(f"Error getting test runs for execution {execution_id}: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)

    def assign_test_run_to_execution(self, test_run_id: int, execution_id: int, client_id: str) -> bool:
        """Assign a test run to an execution"""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # First verify the test run belongs to the user's client through test_cases
            verify_query = """SELECT tr.id FROM test_runs tr
                JOIN test_cases tc ON tr.test_case_id = tc.id
                WHERE tr.id = %s AND tc.client_id = %s"""
            
            cursor.execute(verify_query, (test_run_id, client_id))
            if not cursor.fetchone():
                return False
            
            # Update the test run's execution_id
            query = """UPDATE test_runs 
                SET execution_id = %s 
                WHERE id = %s"""
            
            cursor.execute(query, (execution_id, test_run_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error assigning test run {test_run_id} to execution {execution_id}: {e}")
            raise
        finally:
            if conn:
                return_db_connection(conn)
