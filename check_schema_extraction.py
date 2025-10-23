#!/usr/bin/env python3
"""
Script to check what the schema extraction produces for the /api/auth endpoint
"""
import sys
import json
from Services.ApiSchemaService import ApiSchemaService

# Get schema from database
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="eYuUm57C!",
    database="postgres"
)

cursor = conn.cursor()
cursor.execute("SELECT content FROM api_schemas WHERE id = 15")
schema_content = cursor.fetchone()[0]
cursor.close()
conn.close()

# Create service and extract schema summary
service = ApiSchemaService()
summary = service._extract_schema_summary(schema_content)

# Print the summary
print("=" * 80)
print("SCHEMA EXTRACTION FOR /api/auth ENDPOINT")
print("=" * 80)
print(summary)
print("=" * 80)

# Also check the specific /api/auth endpoint
schema = json.loads(schema_content)
if 'paths' in schema and '/api/auth' in schema['paths']:
    auth_endpoint = schema['paths']['/api/auth']
    print("\n" + "=" * 80)
    print("RAW SCHEMA FOR /api/auth")
    print("=" * 80)
    print(json.dumps(auth_endpoint, indent=2))
