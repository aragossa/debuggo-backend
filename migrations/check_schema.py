import psycopg2

def check_schema():
    """Check the current database schema."""
    # Database connection parameters
    db_params = {
        'dbname': 'postgres',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }
    
    # Connect to the database
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        print("=== Tables in database ===")
        for table in tables:
            print(f"- {table[0]}")
            
            # Get columns for each table
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{table[0]}'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            
            print("  Columns:")
            for col in columns:
                nullable = "NULL" if col[2] == "YES" else "NOT NULL"
                print(f"  - {col[0]} ({col[1]}, {nullable})")
            
            print()
        
    except Exception as e:
        print(f"Error checking schema: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    check_schema()
