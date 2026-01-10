"""
Fetch Test Steps Module
Retrieves test case data and steps from the database
"""

from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


def get_test_data_from_db_helper(conn, test_case_id: int, client_id: str):
    """
    Fetch test case data and steps from the database
    
    Args:
        conn: Database connection
        test_case_id: ID of the test case
        client_id: Client ID for authorization
    
    Returns:
        Dictionary containing test case data and steps
    """
    try:
        cursor = conn.cursor()
        
        # Fetch test case details
        cursor.execute('''
            SELECT id, name, description, type, parent_id, test_case_id, client_id, project_id, updated_at, steps_generation_start_time, steps_generation_end_time, test_type
            FROM test_cases
            WHERE id = %s AND client_id = %s
        ''', (test_case_id, client_id))
        
        test_case = cursor.fetchone()
        
        if not test_case:
            return {
                "status": "error",
                "message": "Test case not found",
                "data": None
            }
        
        # Convert to dictionary
        test_case_dict = {
            "id": test_case[0],
            "name": test_case[1],
            "description": test_case[2],
            "type": test_case[3],
            "parent_id": test_case[4],
            "test_case_id": test_case[5],
            "client_id": test_case[6],
            "project_id": test_case[7],
            "updated_at": test_case[8].isoformat() if test_case[8] else None,
            "steps_generation_start_time": test_case[9].isoformat() if test_case[9] else None,
            "steps_generation_end_time": test_case[10].isoformat() if test_case[10] else None,
            "test_type": test_case[11] if len(test_case) > 11 else 'ui'  # Default to 'ui' if not present
        }
        
        # Fetch test steps if this is a test case (not a folder)
        steps = []
        if test_case_dict["type"] in ["test_case", "test"]:
            cursor.execute('''
                SELECT id, step_order, action, element_path, value, description, css_selector, expected_result, path_type
                FROM test_steps
                WHERE test_case_id = %s
                ORDER BY step_order ASC
            ''', (test_case_id,))
            
            step_rows = cursor.fetchall()
            for step in step_rows:
                steps.append({
                    "id": step[0],
                    "step_order": step[1],
                    "action": step[2],
                    "element_path": step[3],
                    "value": step[4],
                    "description": step[5],
                    "css_selector": step[6],
                    "expected_result": step[7],
                    "path_type": step[8]
                })

        # Fetch associated test suites
        test_suites = []
        cursor.execute('''
            SELECT s.id, s.name
            FROM test_suites s
            JOIN suite_test_cases stc ON s.id = stc.suite_id
            WHERE stc.test_case_id = %s
        ''', (test_case_id,))
        
        suite_rows = cursor.fetchall()
        for suite in suite_rows:
            test_suites.append({
                "id": suite[0],
                "name": suite[1]
            })
        
        return {
            "status": "success",
            "data": {
                "test_case": test_case_dict,
                "steps": steps,
                "test_suites": test_suites
            }
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }
    finally:
        cursor.close()


def get_test_steps_by_case_id(conn, test_case_id: int):
    """
    Fetch test steps for a specific test case
    
    Args:
        conn: Database connection
        test_case_id: ID of the test case
    
    Returns:
        List of test steps
    """
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, step_order, action, element_path, value, description, css_selector, expected_result, path_type
            FROM test_steps
            WHERE test_case_id = %s
            ORDER BY step_order ASC
        ''', (test_case_id,))
        
        steps = []
        for step in cursor.fetchall():
            steps.append({
                "id": step[0],
                "step_order": step[1],
                "action": step[2],
                "element_path": step[3],
                "value": step[4],
                "description": step[5],
                "css_selector": step[6],
                "expected_result": step[7],
                "path_type": step[8]
            })
        
        return steps
    
    except Exception as e:
        print(f"Error fetching test steps: {e}")
        return []
    finally:
        cursor.close()


def get_test_case_tree(conn, client_id: str, project_id: int = None):
    """
    Fetch complete test case tree for a client
    
    Args:
        conn: Database connection
        client_id: Client ID
        project_id: Optional project ID filter
    
    Returns:
        Hierarchical test case tree
    """
    try:
        cursor = conn.cursor()
        
        # Build the query
        if project_id:
            cursor.execute('''
                SELECT id, name, parent_id, type, test_case_id, project_id
                FROM test_cases
                WHERE client_id = %s AND project_id = %s
                ORDER BY parent_id NULLS FIRST, id
            ''', (client_id, project_id))
        else:
            cursor.execute('''
                SELECT id, name, parent_id, type, test_case_id, project_id
                FROM test_cases
                WHERE client_id = %s
                ORDER BY parent_id NULLS FIRST, id
            ''', (client_id,))
        
        # Fetch all rows
        rows = cursor.fetchall()
        
        # Convert to dictionaries
        nodes = []
        for row in rows:
            nodes.append({
                "id": row[0],
                "name": row[1],
                "parent_id": row[2],
                "type": row[3],
                "test_case_id": row[4],
                "project_id": row[5],
                "children": []
            })
        
        # Build tree structure
        tree = []
        node_map = {node["id"]: node for node in nodes}
        
        for node in nodes:
            if node["parent_id"] is None:
                tree.append(node)
            else:
                parent = node_map.get(node["parent_id"])
                if parent:
                    parent["children"].append(node)
        
        return tree
    
    except Exception as e:
        print(f"Error fetching test case tree: {e}")
        return []
    finally:
        cursor.close()
