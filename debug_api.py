import psycopg2
import traceback
import sys
import json
from datetime import datetime

# Helper function to convert datetime objects to ISO format strings
def convert_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

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
                "created_at": updated_test_case[5],
                "updated_at": updated_test_case[6]
            }
            
            # Test JSON serialization
            try:
                json_response = json.dumps(response, default=convert_datetime, indent=2)
                print(f"JSON Response (with custom serializer): {json_response}")
            except Exception as json_err:
                print(f"JSON serialization error: {str(json_err)}")
                traceback.print_exc()
            
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
