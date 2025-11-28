"""
SuiteService: Manages test suites and suite execution
Handles suite creation, test management, and execution orchestration
"""

import logging
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class Suite:
    """Test suite data model"""
    id: int
    client_id: str
    project_id: Optional[str]
    name: str
    description: Optional[str]
    parent_suite_id: Optional[int]
    suite_type: str  # 'static', 'dynamic', 'smart'
    default_environment_id: Optional[int]
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    test_count: int = 0


@dataclass
class SuiteTestCase:
    """Suite test case mapping"""
    id: int
    suite_id: int
    test_case_id: int
    execution_order: int
    environment_override_id: Optional[int]


class SuiteService:
    """Service for managing test suites"""

    def __init__(self, db_connection):
        """Initialize with database connection"""
        self.db = db_connection
        self.logger = logger

    def create_suite(self, client_id: str, name: str, suite_type: str = 'static',
                    project_id: Optional[str] = None, description: Optional[str] = None,
                    parent_suite_id: Optional[int] = None, 
                    default_environment_id: Optional[int] = None,
                    created_by: Optional[int] = None) -> int:
        """
        Create a new test suite
        
        Args:
            client_id: Client UUID
            name: Suite name
            suite_type: 'static', 'dynamic', or 'smart'
            project_id: Optional project UUID
            description: Suite description
            parent_suite_id: Parent suite for hierarchical organization
            default_environment_id: Default environment for suite
            created_by: User ID who created the suite
            
        Returns:
            Suite ID
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO test_suites 
                    (client_id, project_id, name, description, parent_suite_id, 
                     suite_type, default_environment_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (client_id, project_id, name, description, parent_suite_id,
                      suite_type, default_environment_id, created_by))
                
                suite_id = cursor.fetchone()[0]
                self.db.commit()
                
                self.logger.info(f"Created suite '{name}' (ID: {suite_id}) for client {client_id}")
                return suite_id
                
        except psycopg2.IntegrityError as e:
            self.db.rollback()
            self.logger.error(f"Integrity error creating suite: {e}")
            raise ValueError(f"Suite '{name}' already exists in this project")
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error creating suite: {e}")
            raise

    def get_suite(self, suite_id: int) -> Optional[Suite]:
        """Get suite details with test count"""
        try:
            with self.db.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        s.*,
                        COUNT(stc.id) as test_count
                    FROM test_suites s
                    LEFT JOIN suite_test_cases stc ON s.id = stc.suite_id
                    WHERE s.id = %s
                    GROUP BY s.id
                """, (suite_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return Suite(
                    id=row['id'],
                    client_id=row['client_id'],
                    project_id=row['project_id'],
                    name=row['name'],
                    description=row['description'],
                    parent_suite_id=row['parent_suite_id'],
                    suite_type=row['suite_type'],
                    default_environment_id=row['default_environment_id'],
                    created_by=row['created_by'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    test_count=row['test_count'] or 0
                )
                
        except Exception as e:
            self.logger.error(f"Error getting suite {suite_id}: {e}")
            raise

    def list_suites(self, client_id: str, project_id: Optional[str] = None,
                   parent_suite_id: Optional[int] = None) -> List[Suite]:
        """
        List suites with optional filtering
        
        Args:
            client_id: Client UUID (required)
            project_id: Filter by project
            parent_suite_id: Filter by parent suite
            
        Returns:
            List of Suite objects
        """
        try:
            with self.db.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT 
                        s.*,
                        COUNT(stc.id) as test_count
                    FROM test_suites s
                    LEFT JOIN suite_test_cases stc ON s.id = stc.suite_id
                    WHERE s.client_id = %s
                """
                params = [client_id]
                
                if project_id:
                    query += " AND s.project_id = %s"
                    params.append(project_id)
                
                if parent_suite_id is not None:
                    query += " AND s.parent_suite_id = %s"
                    params.append(parent_suite_id)
                
                query += " GROUP BY s.id ORDER BY s.name"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [Suite(
                    id=row['id'],
                    client_id=row['client_id'],
                    project_id=row['project_id'],
                    name=row['name'],
                    description=row['description'],
                    parent_suite_id=row['parent_suite_id'],
                    suite_type=row['suite_type'],
                    default_environment_id=row['default_environment_id'],
                    created_by=row['created_by'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    test_count=row['test_count'] or 0
                ) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error listing suites: {e}")
            raise

    def update_suite(self, suite_id: int, **kwargs) -> bool:
        """
        Update suite properties
        
        Args:
            suite_id: Suite ID
            **kwargs: Fields to update (name, description, default_environment_id, etc.)
            
        Returns:
            True if updated
        """
        allowed_fields = {
            'name', 'description', 'default_environment_id', 
            'parent_suite_id', 'suite_type'
        }
        
        update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        try:
            set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
            values = list(update_fields.values()) + [suite_id]
            
            with self.db.cursor() as cursor:
                cursor.execute(f"""
                    UPDATE test_suites
                    SET {set_clause}
                    WHERE id = %s
                """, values)
                
                self.db.commit()
                self.logger.info(f"Updated suite {suite_id}")
                return True
                
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error updating suite {suite_id}: {e}")
            raise

    def delete_suite(self, suite_id: int) -> bool:
        """Delete a suite and all associated test mappings"""
        try:
            with self.db.cursor() as cursor:
                cursor.execute("DELETE FROM test_suites WHERE id = %s", (suite_id,))
                self.db.commit()
                
                self.logger.info(f"Deleted suite {suite_id}")
                return True
                
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error deleting suite {suite_id}: {e}")
            raise

    def add_test_to_suite(self, suite_id: int, test_case_id: int,
                         execution_order: int = 0,
                         environment_override_id: Optional[int] = None) -> int:
        """
        Add a test case to a suite
        
        Args:
            suite_id: Suite ID
            test_case_id: Test case ID
            execution_order: Order of execution
            environment_override_id: Optional environment override
            
        Returns:
            Suite test case ID
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO suite_test_cases 
                    (suite_id, test_case_id, execution_order, environment_override_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (suite_id, test_case_id, execution_order, environment_override_id))
                
                stc_id = cursor.fetchone()[0]
                self.db.commit()
                
                self.logger.info(f"Added test {test_case_id} to suite {suite_id}")
                return stc_id
                
        except psycopg2.IntegrityError:
            self.db.rollback()
            self.logger.warning(f"Test {test_case_id} already in suite {suite_id}")
            raise ValueError("Test already in suite")
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error adding test to suite: {e}")
            raise

    def remove_test_from_suite(self, suite_id: int, test_case_id: int) -> bool:
        """Remove a test case from a suite"""
        try:
            with self.db.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM suite_test_cases
                    WHERE suite_id = %s AND test_case_id = %s
                """, (suite_id, test_case_id))
                
                self.db.commit()
                self.logger.info(f"Removed test {test_case_id} from suite {suite_id}")
                return True
                
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error removing test from suite: {e}")
            raise

    def get_suite_tests(self, suite_id: int) -> List[Dict]:
        """Get all tests in a suite with execution order"""
        try:
            with self.db.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        stc.id,
                        stc.test_case_id,
                        stc.execution_order,
                        stc.environment_override_id,
                        tc.name as test_name,
                        tc.test_type,
                        tc.description
                    FROM suite_test_cases stc
                    JOIN test_cases tc ON stc.test_case_id = tc.id
                    WHERE stc.suite_id = %s
                    ORDER BY stc.execution_order, tc.name
                """, (suite_id,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            self.logger.error(f"Error getting suite tests: {e}")
            raise

    def update_test_execution_order(self, suite_id: int, test_case_id: int,
                                   execution_order: int) -> bool:
        """Update execution order of a test in suite"""
        try:
            with self.db.cursor() as cursor:
                cursor.execute("""
                    UPDATE suite_test_cases
                    SET execution_order = %s
                    WHERE suite_id = %s AND test_case_id = %s
                """, (execution_order, suite_id, test_case_id))
                
                self.db.commit()
                return True
                
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error updating execution order: {e}")
            raise

    def get_suite_hierarchy(self, client_id: str, project_id: Optional[str] = None) -> List[Dict]:
        """
        Get hierarchical suite structure
        
        Returns:
            List of suites with nested children
        """
        try:
            with self.db.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    WITH RECURSIVE suite_tree AS (
                        SELECT 
                            s.*,
                            COUNT(stc.id) as test_count,
                            0 as depth
                        FROM test_suites s
                        LEFT JOIN suite_test_cases stc ON s.id = stc.suite_id
                        WHERE s.client_id = %s AND s.parent_suite_id IS NULL
                """
                params = [client_id]
                
                if project_id:
                    query += " AND s.project_id = %s"
                    params.append(project_id)
                
                query += """
                        GROUP BY s.id
                        
                        UNION ALL
                        
                        SELECT 
                            s.*,
                            COUNT(stc.id) as test_count,
                            st.depth + 1
                        FROM test_suites s
                        LEFT JOIN suite_test_cases stc ON s.id = stc.suite_id
                        JOIN suite_tree st ON s.parent_suite_id = st.id
                        GROUP BY s.id, st.depth
                    )
                    SELECT * FROM suite_tree
                    ORDER BY depth, name
                """
                
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            self.logger.error(f"Error getting suite hierarchy: {e}")
            raise

    def get_suite_statistics(self, suite_id: int) -> Dict:
        """Get statistics for a suite"""
        try:
            with self.db.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get test count and types
                cursor.execute("""
                    SELECT 
                        COUNT(stc.id) as total_tests,
                        COUNT(CASE WHEN tc.test_type = 'ui' THEN 1 END) as ui_tests,
                        COUNT(CASE WHEN tc.test_type = 'api' THEN 1 END) as api_tests
                    FROM suite_test_cases stc
                    JOIN test_cases tc ON stc.test_case_id = tc.id
                    WHERE stc.suite_id = %s
                """, (suite_id,))
                
                stats = dict(cursor.fetchone() or {})
                
                # Get recent execution stats
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                        AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds
                    FROM test_runs
                    WHERE suite_id = %s AND started_at > NOW() - INTERVAL '30 days'
                """, (suite_id,))
                
                execution_stats = dict(cursor.fetchone() or {})
                stats.update(execution_stats)
                
                return stats
                
        except Exception as e:
            self.logger.error(f"Error getting suite statistics: {e}")
            raise
