"""
Migration to add start_time and end_time columns to test_cases table
for tracking test steps generation timing.
"""

from datetime import datetime
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", "postgres"),
            database=os.environ.get("DB_NAME", "postgres")
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def migrate():
    """Execute the migration."""
    logger.info("Starting migration to add test steps generation timing columns")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'test_cases' 
            AND column_name IN ('steps_generation_start_time', 'steps_generation_end_time');
        """)
        
        existing_columns = [col[0] for col in cursor.fetchall()]
        
        # Add steps_generation_start_time column if it doesn't exist
        if 'steps_generation_start_time' not in existing_columns:
            logger.info("Adding steps_generation_start_time column to test_cases table")
            cursor.execute("""
                ALTER TABLE test_cases 
                ADD COLUMN steps_generation_start_time TIMESTAMP WITH TIME ZONE;
            """)
        
        # Add steps_generation_end_time column if it doesn't exist
        if 'steps_generation_end_time' not in existing_columns:
            logger.info("Adding steps_generation_end_time column to test_cases table")
            cursor.execute("""
                ALTER TABLE test_cases 
                ADD COLUMN steps_generation_end_time TIMESTAMP WITH TIME ZONE;
            """)
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    migrate()
