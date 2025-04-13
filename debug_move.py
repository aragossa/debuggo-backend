import psycopg2
import traceback
import sys

# Connect to the database
try:
    conn = psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="postgres",
        port=5432
    )
    conn.autocommit = False
    
    # Test the move test case functionality
    with conn.cursor() as cur:
        # Check if the test case exists
        test_case_id = 725  # Replace with your test case ID
        target_group_id = 724  # Replace with your target group ID
        
        cur.execute(
            """
            SELECT id, client_id, type, parent_id 
            FROM test_cases 
            WHERE id = %s
            """,
            (test_case_id,)
        )
        test_case = cur.fetchone()
        
        if not test_case:
            print(f"Test case {test_case_id} not found")
            sys.exit(1)
        
        print(f"Test case found: {test_case}")
        
        # Check if the target group exists
        cur.execute(
            """
            SELECT id, type, client_id 
            FROM test_cases 
            WHERE id = %s
            """,
            (target_group_id,)
        )
        target_group = cur.fetchone()
        
        if not target_group:
            print(f"Target group {target_group_id} not found")
            sys.exit(1)
        
        print(f"Target group found: {target_group}")
        
        # Try to update the test case's parent_id
        try:
            cur.execute(
                """
                UPDATE test_cases
                SET parent_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, name, parent_id, type, "order", created_at, updated_at
                """,
                (target_group_id, test_case_id)
            )
            updated_test_case = cur.fetchone()
            conn.commit()
            
            print(f"Successfully moved test case: {updated_test_case}")
        except Exception as e:
            conn.rollback()
            print(f"Failed to move test case: {str(e)}")
            traceback.print_exc()
    
except Exception as e:
    print(f"Database connection error: {str(e)}")
    traceback.print_exc()
finally:
    if 'conn' in locals():
        conn.close()
