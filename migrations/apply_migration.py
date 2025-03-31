import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def apply_migration(migration_file):
    """Apply a SQL migration file to the database."""
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
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print(f"Applying migration: {migration_file}")
        
        # Read the migration file
        with open(migration_file, 'r') as f:
            sql = f.read()
        
        # Execute the SQL commands
        cursor.execute(sql)
        
        print(f"Migration {migration_file} applied successfully!")
        
    except Exception as e:
        print(f"Error applying migration {migration_file}: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def main():
    """Apply all migration files in the migrations directory."""
    # Get the directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get all SQL files in the migrations directory
    migration_files = [
        os.path.join(current_dir, f) 
        for f in os.listdir(current_dir) 
        if f.endswith('.sql')
    ]
    
    # Sort the migration files to ensure they're applied in the correct order
    migration_files.sort()
    
    # Apply each migration
    for migration_file in migration_files:
        apply_migration(migration_file)
    
    print("All migrations applied successfully!")

if __name__ == "__main__":
    main()
