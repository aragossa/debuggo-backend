#!/usr/bin/env python3
"""
Script to regenerate test steps for test case 1281 using the improved schema extraction
"""
import psycopg2

# Delete existing steps
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="eYuUm57C!",
    database="postgres"
)

cursor = conn.cursor()

print("Deleting existing test steps for test case 1281...")
cursor.execute("DELETE FROM test_steps WHERE test_case_id = 1281")
deleted_count = cursor.rowcount
conn.commit()

print(f"✅ Deleted {deleted_count} existing steps")
print("\nNow you can:")
print("1. Go to the UI")
print("2. Select test case 1281 (Successful Authentication)")
print("3. Click 'Generate with AI' button")
print("4. The new steps will use the improved schema extraction with correct field names")

cursor.close()
conn.close()
