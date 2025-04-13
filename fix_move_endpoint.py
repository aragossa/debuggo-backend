import psycopg2
import traceback
import sys
import json
from datetime import datetime

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
    
    # Print the SQL query that will be executed
    test_case_id = 725
    target_group_id = 724
    
    sql_query = f"""
    UPDATE test_cases
    SET parent_id = {target_group_id}, updated_at = CURRENT_TIMESTAMP
    WHERE id = {test_case_id}
    RETURNING id, name, parent_id, type, "order", created_at, updated_at
    """
    
    print(f"SQL Query to be executed:\n{sql_query}")
    
    # Execute the query directly
    with conn.cursor() as cur:
        cur.execute(sql_query)
        result = cur.fetchone()
        conn.commit()
        
        if result:
            print("Query executed successfully")
            print(f"Result: {result}")
            
            # Format the result as it would be in the API response
            formatted_result = {
                "id": result[0],
                "name": result[1],
                "parent_id": result[2],
                "type": result[3],
                "order": result[4],
                "created_at": result[5].isoformat() if result[5] else None,
                "updated_at": result[6].isoformat() if result[6] else None
            }
            
            print(f"Formatted result: {json.dumps(formatted_result, indent=2)}")
        else:
            print("Query executed but no rows were returned")
    
except Exception as e:
    print(f"Error: {str(e)}")
    traceback.print_exc()
finally:
    if 'conn' in locals():
        conn.close()
        print("Database connection closed")
