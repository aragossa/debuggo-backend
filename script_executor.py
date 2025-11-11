from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


def save_test_run_result(test_case_id, result, exception="", duration=None, stdout="", stderr="", additional_info=""):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO test_runs (test_case_id, result, exception, duration, stdout, stderr, additional_info)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (test_case_id, result, exception, duration, stdout, stderr, additional_info))

        conn.commit()
    finally:
        return_db_connection(conn)




def execute_test_case(test_case_id):
    import subprocess
    import time
    import io
    import sys

    start_time = time.time()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Retrieve the python_script and curl command from the test_cases table where id = test_case_id
    cursor.execute('''
        SELECT python_script, curl FROM test_cases WHERE id = %s
    ''', (test_case_id,))
    result = cursor.fetchone()

    if result is None:
        exception_message = f"No test case found with id {test_case_id}"
        save_test_run_result(test_case_id, "Failed", exception=exception_message)
        return_db_connection(conn)
        return {
            "result": "Failed",
            "exception": exception_message
        }

    curl_command = result
    return_db_connection(conn)

    stdout_content = ""
    stderr_content = ""

    if python_script:
        # Execute the python script
        try:
            # Redirect stdout and stderr to capture outputs
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = stdout_buffer = io.StringIO()
            sys.stderr = stderr_buffer = io.StringIO()

            exec(python_script, {})

            # Restore stdout and stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            stdout_content = stdout_buffer.getvalue()
            stderr_content = stderr_buffer.getvalue()

            duration = time.time() - start_time

            # Save the test run result
            save_test_run_result(
                test_case_id,
                "Passed",
                exception="",
                duration=duration,
                stdout=stdout_content,
                stderr=stderr_content
            )

            return {
                "result": "Passed",
                "exception": "",
                "stdout": stdout_content,
                "stderr": stderr_content
            }

        except Exception as e:
            # Restore stdout and stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            stdout_content = stdout_buffer.getvalue()
            stderr_content = stderr_buffer.getvalue()

            exception_message = str(e)
            duration = time.time() - start_time

            # Save the test run result
            save_test_run_result(
                test_case_id,
                "Failed",
                exception=exception_message,
                duration=duration,
                stdout=stdout_content,
                stderr=stderr_content
            )

            return {
                "result": "Failed",
                "exception": exception_message,
                "stdout": stdout_content,
                "stderr": stderr_content
            }

    elif curl_command:
        # Execute the curl command
        try:
            result = subprocess.run(
                curl_command,
                shell=True,
                capture_output=True,
                text=True
            )

            duration = time.time() - start_time

            stdout_content = result.stdout
            stderr_content = result.stderr

            if result.returncode == 0:
                # Test passed
                save_test_run_result(
                    test_case_id,
                    "Passed",
                    exception="",
                    duration=duration,
                    stdout=stdout_content,
                    stderr=stderr_content
                )

                return {
                    "result": "Passed",
                    "stdout": stdout_content,
                    "stderr": stderr_content
                }
            else:
                # Test failed
                save_test_run_result(
                    test_case_id,
                    "Failed",
                    exception="",
                    duration=duration,
                    stdout=stdout_content,
                    stderr=stderr_content
                )

                return {
                    "result": "Failed",
                    "stdout": stdout_content,
                    "stderr": stderr_content
                }

        except Exception as e:
            exception_message = str(e)
            duration = time.time() - start_time

            # Save the test run result
            save_test_run_result(
                test_case_id,
                "Failed",
                exception=exception_message,
                duration=duration
            )

            return {
                "result": "Failed",
                "exception": exception_message
            }
    else:
        exception_message = f"No python script or curl command found for test case id {test_case_id}"
        duration = time.time() - start_time

        # Save the test run result
        save_test_run_result(
            test_case_id,
            "Failed",
            exception=exception_message,
            duration=duration
        )

        return {
            "result": "Failed",
            "exception": exception_message
        }
