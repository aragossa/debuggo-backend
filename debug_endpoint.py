import psycopg2
import traceback
import sys
import json

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
    
    # Simulate the request data
    test_case_id = 725  # Replace with your test case ID
    target_group_id = 724  # Replace with your target group ID
    
    print(f"Testing move_test_case with test_case_id={test_case_id}, target_group_id={target_group_id}")
    
    # Test the move test case functionality
    try:
        with conn.cursor() as cur:
            # Check if the test case exists and belongs to the user's client
            cur.execute(
                """
                SELECT id, client_id 
                FROM test_cases 
                WHERE id = %s
                """,
                (test_case_id,)
            )
            test_case = cur.fetchone()
            
            if not test_case:
                print("Test case not found")
                sys.exit(1)
            
            print(f"Test case found: {test_case}")
            
            # Check if the target group exists and is a valid group
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
                print("Target group not found")
                sys.exit(1)
            
            print(f"Target group found: {target_group}")
            
            if target_group[1] != 'group' and target_group[1] != 'root':
                print("Target must be a group or root")
                sys.exit(1)
            
            # Update the test case's parent_id
            print("Executing SQL query to update parent_id...")
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
            
            if not updated_test_case:
                print("No rows were updated")
                sys.exit(1)
            
            print(f"Updated test case: {updated_test_case}")
            
            # Format the response
            response = {
                "id": updated_test_case[0],
                "name": updated_test_case[1],
                "parent_id": updated_test_case[2],
                "type": updated_test_case[3],
                "order": updated_test_case[4],
                "created_at": str(updated_test_case[5]) if updated_test_case[5] else None,
                "updated_at": str(updated_test_case[6]) if updated_test_case[6] else None
            }
            
            print(f"Response: {json.dumps(response, indent=2)}")
            
            # Commit the transaction
            conn.commit()
            print("Transaction committed successfully")
            
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        traceback.print_exc()
    
except Exception as e:
    print(f"Database connection error: {str(e)}")
    traceback.print_exc()
finally:
    if 'conn' in locals():
        conn.close()
        print("Database connection closed")
