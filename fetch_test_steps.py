from Utils.Connectors.db_utils import get_db_connection, return_db_connection


def get_test_data_from_db(test_case_id: int, client_id: str):
    conn = get_db_connection()
    
    try:
        result = get_test_data_from_db_helper(conn, test_case_id, client_id)
        return result
    finally:
        return_db_connection(conn)


def get_test_data_from_db_helper(conn, test_case_id: int, client_id: str):
    cursor = conn.cursor()

    cursor.execute('''
         SELECT name, description, updated_at, steps_generation_start_time, steps_generation_end_time
         FROM test_cases
         WHERE id = %s AND client_id = %s
     ''', (test_case_id, client_id))

    # Fetch test case details
    test_case_row = cursor.fetchone()
    if not test_case_row:
        return None

    # Query to get the test steps for the given test_case_id
    cursor.execute('''
        SELECT id, step_order, description, expected_result, action, value, element_path
        FROM test_steps
        WHERE test_case_id = %s
        ORDER BY step_order ASC
    ''', (test_case_id,))

    # Fetch all the rows for test steps
    steps_rows = cursor.fetchall()

    # Convert rows to list of dictionaries for test steps
    test_steps = [
        {
            "id": row[0],
            "name": f"Test Step {row[1]}",
            "description": row[2],
            "expected_result": row[3],
            "action": row[4],
            "value": row[5],
            "element_path": row[6]
        }
        for row in steps_rows
    ]

    # Query to get the test runs for the given test_case_id
    cursor.execute('''
        SELECT id, run_date, result, exception, duration, stdout, stderr, additional_info
        FROM test_runs
        WHERE test_case_id = %s
        ORDER BY run_date DESC
    ''', (test_case_id,))

    # Fetch all the rows for test runs
    runs_rows = cursor.fetchall()

    # Convert rows to list of dictionaries for test runs
    test_runs = []
    for row in runs_rows:
        test_run = {
            "id": row[0],
            "run_date": row[1].isoformat(),
            "result": row[2],
            "exception": row[3],
            "duration": row[4],
            "stdout": row[5],
            "stderr": row[6],
            "additional_info": row[7],
        }
        test_runs.append(test_run)

    # Return test case data including generation timing
    return {
        "test_name": test_case_row[0],
        "test_description": test_case_row[1],
        "updated_at": test_case_row[2].isoformat() if test_case_row[2] else None,
        "steps_generation_start_time": test_case_row[3].isoformat() if test_case_row[3] else None,
        "steps_generation_end_time": test_case_row[4].isoformat() if test_case_row[4] else None,
        "test_steps": test_steps,
        "test_runs": test_runs
    }
