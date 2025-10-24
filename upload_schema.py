#!/usr/bin/env python3
"""Upload API schema to database"""
import json
import psycopg2

# Read the schema file
with open('/Users/aragossa/dzrprj/auroqa/auroqa/tests/lucy-swagger.json', 'r') as f:
    schema_content = f.read()

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    user='postgres',
    password='eYuUm57C!',
    database='postgres'
)

try:
    with conn.cursor() as cursor:
        # Insert schema
        cursor.execute("""
            INSERT INTO api_schemas (
                project_id, client_id, name, description, 
                schema_type, content, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            'fecf1566-d1c8-4967-b0f7-405fb6aaa1e8',  # project_id
            'fc4f046c-8b48-43b6-84ca-ac93097078e4',  # client_id
            'Lucy API Schema',
            'Main API schema for Lucy project',
            'swagger',
            schema_content,
            13  # user_id
        ))
        
        schema_id = cursor.fetchone()[0]
        conn.commit()
        print(f"✅ Successfully uploaded schema with ID: {schema_id}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
finally:
    conn.close()
