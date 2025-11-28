"""
RequirementsService: Manages requirements and test-to-requirement traceability

Features:
- Requirement CRUD operations
- Test-to-requirement mapping
- Coverage calculation
- Traceability matrix
- Impact analysis
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class RequirementsService:
    """Manages requirements and traceability"""
    
    def __init__(self):
        """Initialize RequirementsService"""
        self.logger = logging.getLogger(__name__)
        self.system = System()
    
    # ========================================================================
    # Requirement CRUD
    # ========================================================================
    
    def create_requirement(
        self,
        client_id: str,
        project_id: str,
        requirement_id: str,
        title: str,
        description: Optional[str] = None,
        requirement_type: str = 'functional',
        priority: str = 'medium',
        status: str = 'draft',
        created_by: Optional[int] = None
    ) -> Optional[int]:
        """Create a new requirement"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO requirements 
                            (client_id, project_id, requirement_id, title, description,
                             requirement_type, priority, status, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (client_id, project_id, requirement_id, title, description,
                         requirement_type, priority, status, created_by)
                    )
                    result = cursor.fetchone()
                    conn.commit()
                    return result[0] if result else None
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error creating requirement: {e}")
            return None
    
    def get_requirement(self, requirement_db_id: int) -> Optional[Dict]:
        """Get requirement by database ID"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, client_id, project_id, requirement_id, title, description,
                               requirement_type, priority, status, created_by, created_at, updated_at
                        FROM requirements
                        WHERE id = %s
                        """,
                        (requirement_db_id,)
                    )
                    result = cursor.fetchone()
                    if not result:
                        return None
                    
                    return {
                        'id': result[0],
                        'client_id': str(result[1]),
                        'project_id': str(result[2]) if result[2] else None,
                        'requirement_id': result[3],
                        'title': result[4],
                        'description': result[5],
                        'requirement_type': result[6],
                        'priority': result[7],
                        'status': result[8],
                        'created_by': result[9],
                        'created_at': result[10],
                        'updated_at': result[11]
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting requirement: {e}")
            return None
    
    def list_requirements(
        self,
        client_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        requirement_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple:
        """List requirements with filters"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Build WHERE clause
                    conditions = ["client_id = %s"]
                    params = [client_id]
                    
                    if project_id:
                        conditions.append("project_id = %s")
                        params.append(project_id)
                    if status:
                        conditions.append("status = %s")
                        params.append(status)
                    if priority:
                        conditions.append("priority = %s")
                        params.append(priority)
                    if requirement_type:
                        conditions.append("requirement_type = %s")
                        params.append(requirement_type)
                    
                    where_clause = " AND ".join(conditions)
                    
                    # Get total count
                    cursor.execute(
                        f"SELECT COUNT(*) FROM requirements WHERE {where_clause}",
                        params
                    )
                    total = cursor.fetchone()[0]
                    
                    # Get paginated results
                    params.extend([limit, offset])
                    cursor.execute(
                        f"""
                        SELECT id, client_id, project_id, requirement_id, title, description,
                               requirement_type, priority, status, created_at, updated_at
                        FROM requirements
                        WHERE {where_clause}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        params
                    )
                    
                    requirements = []
                    for row in cursor.fetchall():
                        requirements.append({
                            'id': row[0],
                            'client_id': str(row[1]),
                            'project_id': str(row[2]) if row[2] else None,
                            'requirement_id': row[3],
                            'title': row[4],
                            'description': row[5],
                            'requirement_type': row[6],
                            'priority': row[7],
                            'status': row[8],
                            'created_at': row[9],
                            'updated_at': row[10]
                        })
                    
                    return requirements, total
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error listing requirements: {e}")
            return [], 0
    
    def update_requirement(
        self,
        requirement_db_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        requirement_type: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None
    ) -> bool:
        """Update a requirement"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    updates = []
                    params = []
                    
                    if title is not None:
                        updates.append("title = %s")
                        params.append(title)
                    if description is not None:
                        updates.append("description = %s")
                        params.append(description)
                    if requirement_type is not None:
                        updates.append("requirement_type = %s")
                        params.append(requirement_type)
                    if priority is not None:
                        updates.append("priority = %s")
                        params.append(priority)
                    if status is not None:
                        updates.append("status = %s")
                        params.append(status)
                    
                    if not updates:
                        return True
                    
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(requirement_db_id)
                    
                    cursor.execute(
                        f"""
                        UPDATE requirements
                        SET {", ".join(updates)}
                        WHERE id = %s
                        """,
                        params
                    )
                    conn.commit()
                    return cursor.rowcount > 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error updating requirement: {e}")
            return False
    
    def delete_requirement(self, requirement_db_id: int) -> bool:
        """Delete a requirement"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM requirements WHERE id = %s",
                        (requirement_db_id,)
                    )
                    conn.commit()
                    return cursor.rowcount > 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error deleting requirement: {e}")
            return False
    
    # ========================================================================
    # Test-Requirement Mapping
    # ========================================================================
    
    def map_test_to_requirement(
        self,
        test_case_id: int,
        requirement_db_id: int,
        coverage_type: str = 'full'
    ) -> Optional[int]:
        """Map a test case to a requirement"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO test_requirement_mapping 
                            (test_case_id, requirement_id, coverage_type)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (test_case_id, requirement_id) 
                        DO UPDATE SET coverage_type = EXCLUDED.coverage_type
                        RETURNING id
                        """,
                        (test_case_id, requirement_db_id, coverage_type)
                    )
                    result = cursor.fetchone()
                    conn.commit()
                    return result[0] if result else None
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error mapping test to requirement: {e}")
            return None
    
    def unmap_test_from_requirement(
        self,
        test_case_id: int,
        requirement_db_id: int
    ) -> bool:
        """Remove a test-requirement mapping"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM test_requirement_mapping
                        WHERE test_case_id = %s AND requirement_id = %s
                        """,
                        (test_case_id, requirement_db_id)
                    )
                    conn.commit()
                    return cursor.rowcount > 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error unmapping test from requirement: {e}")
            return False
    
    def get_tests_for_requirement(self, requirement_db_id: int) -> List[Dict]:
        """Get all tests mapped to a requirement"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT tc.id, tc.name, tc.description, tc.type, trm.coverage_type
                        FROM test_cases tc
                        JOIN test_requirement_mapping trm ON tc.id = trm.test_case_id
                        WHERE trm.requirement_id = %s
                        ORDER BY tc.name
                        """,
                        (requirement_db_id,)
                    )
                    
                    tests = []
                    for row in cursor.fetchall():
                        tests.append({
                            'test_case_id': row[0],
                            'name': row[1],
                            'description': row[2],
                            'type': row[3],
                            'coverage_type': row[4]
                        })
                    return tests
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting tests for requirement: {e}")
            return []
    
    def get_requirements_for_test(self, test_case_id: int) -> List[Dict]:
        """Get all requirements linked to a test"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT r.id, r.requirement_id, r.title, r.priority, r.status, trm.coverage_type
                        FROM requirements r
                        JOIN test_requirement_mapping trm ON r.id = trm.requirement_id
                        WHERE trm.test_case_id = %s
                        ORDER BY r.requirement_id
                        """,
                        (test_case_id,)
                    )
                    
                    requirements = []
                    for row in cursor.fetchall():
                        requirements.append({
                            'id': row[0],
                            'requirement_id': row[1],
                            'title': row[2],
                            'priority': row[3],
                            'status': row[4],
                            'coverage_type': row[5]
                        })
                    return requirements
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting requirements for test: {e}")
            return []
    
    # ========================================================================
    # Coverage Analysis
    # ========================================================================
    
    def get_coverage_summary(
        self,
        client_id: str,
        project_id: Optional[str] = None
    ) -> Dict:
        """Get requirements coverage summary"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Build filter
                    conditions = ["r.client_id = %s"]
                    params = [client_id]
                    if project_id:
                        conditions.append("r.project_id = %s")
                        params.append(project_id)
                    where_clause = " AND ".join(conditions)
                    
                    # Total requirements
                    cursor.execute(
                        f"SELECT COUNT(*) FROM requirements r WHERE {where_clause}",
                        params
                    )
                    total_requirements = cursor.fetchone()[0]
                    
                    # Requirements with tests
                    cursor.execute(
                        f"""
                        SELECT COUNT(DISTINCT r.id)
                        FROM requirements r
                        JOIN test_requirement_mapping trm ON r.id = trm.requirement_id
                        WHERE {where_clause}
                        """,
                        params
                    )
                    covered_requirements = cursor.fetchone()[0]
                    
                    # Requirements by status
                    cursor.execute(
                        f"""
                        SELECT status, COUNT(*) 
                        FROM requirements r
                        WHERE {where_clause}
                        GROUP BY status
                        """,
                        params
                    )
                    by_status = {row[0]: row[1] for row in cursor.fetchall()}
                    
                    # Requirements by priority
                    cursor.execute(
                        f"""
                        SELECT priority, COUNT(*) 
                        FROM requirements r
                        WHERE {where_clause}
                        GROUP BY priority
                        """,
                        params
                    )
                    by_priority = {row[0]: row[1] for row in cursor.fetchall()}
                    
                    # Coverage by type
                    cursor.execute(
                        f"""
                        SELECT trm.coverage_type, COUNT(DISTINCT r.id)
                        FROM requirements r
                        JOIN test_requirement_mapping trm ON r.id = trm.requirement_id
                        WHERE {where_clause}
                        GROUP BY trm.coverage_type
                        """,
                        params
                    )
                    by_coverage_type = {row[0]: row[1] for row in cursor.fetchall()}
                    
                    uncovered = total_requirements - covered_requirements
                    coverage_percentage = (covered_requirements / total_requirements * 100) if total_requirements > 0 else 0
                    
                    return {
                        'total_requirements': total_requirements,
                        'covered_requirements': covered_requirements,
                        'uncovered_requirements': uncovered,
                        'coverage_percentage': round(coverage_percentage, 1),
                        'by_status': by_status,
                        'by_priority': by_priority,
                        'by_coverage_type': by_coverage_type
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting coverage summary: {e}")
            return {
                'total_requirements': 0,
                'covered_requirements': 0,
                'uncovered_requirements': 0,
                'coverage_percentage': 0,
                'by_status': {},
                'by_priority': {},
                'by_coverage_type': {}
            }
    
    def get_traceability_matrix(
        self,
        client_id: str,
        project_id: Optional[str] = None
    ) -> List[Dict]:
        """Get traceability matrix (requirements with their linked tests)"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Build filter
                    conditions = ["r.client_id = %s"]
                    params = [client_id]
                    if project_id:
                        conditions.append("r.project_id = %s")
                        params.append(project_id)
                    where_clause = " AND ".join(conditions)
                    
                    cursor.execute(
                        f"""
                        SELECT r.id, r.requirement_id, r.title, r.priority, r.status,
                               COUNT(trm.test_case_id) as test_count,
                               STRING_AGG(DISTINCT tc.name, ', ') as test_names
                        FROM requirements r
                        LEFT JOIN test_requirement_mapping trm ON r.id = trm.requirement_id
                        LEFT JOIN test_cases tc ON trm.test_case_id = tc.id
                        WHERE {where_clause}
                        GROUP BY r.id, r.requirement_id, r.title, r.priority, r.status
                        ORDER BY r.requirement_id
                        """,
                        params
                    )
                    
                    matrix = []
                    for row in cursor.fetchall():
                        matrix.append({
                            'id': row[0],
                            'requirement_id': row[1],
                            'title': row[2],
                            'priority': row[3],
                            'status': row[4],
                            'test_count': row[5],
                            'test_names': row[6] or '',
                            'is_covered': row[5] > 0
                        })
                    return matrix
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting traceability matrix: {e}")
            return []
    
    def get_uncovered_requirements(
        self,
        client_id: str,
        project_id: Optional[str] = None
    ) -> List[Dict]:
        """Get requirements without any test coverage"""
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Build filter
                    conditions = ["r.client_id = %s"]
                    params = [client_id]
                    if project_id:
                        conditions.append("r.project_id = %s")
                        params.append(project_id)
                    where_clause = " AND ".join(conditions)
                    
                    cursor.execute(
                        f"""
                        SELECT r.id, r.requirement_id, r.title, r.priority, r.status
                        FROM requirements r
                        LEFT JOIN test_requirement_mapping trm ON r.id = trm.requirement_id
                        WHERE {where_clause} AND trm.id IS NULL
                        ORDER BY r.priority DESC, r.requirement_id
                        """,
                        params
                    )
                    
                    uncovered = []
                    for row in cursor.fetchall():
                        uncovered.append({
                            'id': row[0],
                            'requirement_id': row[1],
                            'title': row[2],
                            'priority': row[3],
                            'status': row[4]
                        })
                    return uncovered
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting uncovered requirements: {e}")
            return []


# Singleton instance
_requirements_service = None

def get_requirements_service() -> RequirementsService:
    """Get or create singleton RequirementsService instance"""
    global _requirements_service
    if _requirements_service is None:
        _requirements_service = RequirementsService()
    return _requirements_service
