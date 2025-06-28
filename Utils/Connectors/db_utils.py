"""
Database utility functions for connecting to PostgreSQL.
"""
import psycopg2
from psycopg2 import pool
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize database connection pool
db_pool = None

def init_db_pool():
    """Initialize the database connection pool."""
    global db_pool
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres")
        )
        print("Database pool initialized")
    except Exception as e:
        print(f"Error initializing database pool: {e}")
        db_pool = None

def get_db_connection():
    """Get a connection from the pool."""
    if db_pool is None:
        raise Exception("Database pool not initialized")
    return db_pool.getconn()

def return_db_connection(conn):
    """Return a connection to the pool."""
    if db_pool is not None and conn is not None:
        db_pool.putconn(conn)
        
def close_db_pool():
    """Close all connections in the pool."""
    global db_pool
    if db_pool is not None:
        db_pool.closeall()
        print("Database pool closed")
        db_pool = None
