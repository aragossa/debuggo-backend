"""
Database utility functions for connecting to PostgreSQL.
"""
import psycopg2
from psycopg2 import pool
import os
from dotenv import load_dotenv
from contextlib import contextmanager
import logging
import threading
import weakref

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
# Don't override existing environment variables (preserve command-line overrides)
load_dotenv(override=False)

# Initialize database connection pool
db_pool = None
# Track active connections to prevent "unkeyed connection" errors
# We use a separate lock just for the set operations, which are fast and in-memory
_active_connections = weakref.WeakSet()
_tracking_lock = threading.Lock()

def init_db_pool():
    """Initialize the database connection pool."""
    global db_pool
    try:
        # Pool size: 10-100 connections
        # SimpleConnectionPool is thread-safe for getconn/putconn
        db_pool = psycopg2.pool.SimpleConnectionPool(
            10, 100,
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres")
        )
        logger.info(f"Database pool initialized with {db_pool.minconn}-{db_pool.maxconn} connections")
    except Exception as e:
        print(f"Error initializing database pool: {e}")
        db_pool = None

def get_db_connection():
    """Get a connection from the pool with validation."""
    if db_pool is None:
        raise Exception("Database pool not initialized")
    
    # No global lock here! SimpleConnectionPool.getconn() is thread-safe.
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            conn = db_pool.getconn()
            
            # Validate connection is not closed
            if conn.closed:
                logger.warning(f"Retrieved closed connection on attempt {attempt + 1}, trying to get new one")
                try:
                    # Return bad connection to pool with close=True to remove it
                    db_pool.putconn(conn, close=True)
                except Exception:
                    pass
                continue
            
            # Test connection with a simple query
            # This network I/O now happens in parallel for different threads!
            try:
                with conn.cursor() as test_cur:
                    test_cur.execute("SELECT 1")
                    test_cur.fetchone()
            except Exception as e:
                logger.warning(f"Connection failed test query on attempt {attempt + 1}: {e}")
                try:
                    db_pool.putconn(conn, close=True)
                except Exception:
                    pass
                continue
            
            # Track this connection as active
            with _tracking_lock:
                _active_connections.add(conn)
            
            # Logging connection stats (optional, can be noisy)
            # logger.debug(f"Valid connection retrieved.")
            return conn
            
        except Exception as e:
            logger.error(f"Error getting connection on attempt {attempt + 1}: {e}")
            if attempt == max_attempts - 1:
                raise Exception(f"Failed to get valid connection after {max_attempts} attempts")
            continue
    
    raise Exception("Unable to retrieve valid connection from pool")

def return_db_connection(conn):
    """Return a connection to the pool with proper validation."""
    if db_pool is not None and conn is not None:
        try:
            # Check if connection is in our tracked set
            is_tracked = False
            with _tracking_lock:
                if conn in _active_connections:
                    _active_connections.discard(conn)
                    is_tracked = True
            
            if not is_tracked:
                logger.warning("Attempting to return untracked connection - forcing close instead")
                try:
                    conn.close()
                except Exception:
                    pass
                return
            
            # Only return valid connections to pool
            if not conn.closed:
                try:
                    # Rollback any uncommitted transactions
                    conn.rollback()
                    
                    # Verify connection is still valid before returning
                    # This validation also happens in parallel now
                    with conn.cursor() as test_cur:
                        test_cur.execute("SELECT 1")
                        test_cur.fetchone()
                    
                    # Connection is valid, return to pool
                    db_pool.putconn(conn)
                except Exception as e:
                    logger.warning(f"Connection invalid during return, closing instead: {e}")
                    try:
                        # If validation fails, put back with close=True
                        db_pool.putconn(conn, close=True)
                    except Exception:
                        pass
            else:
                logger.debug("Connection already closed, not returning to pool")
                try:
                    # Ensure pool knows it's gone if it was from the pool
                    db_pool.putconn(conn, close=True)
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")
            # Force close if something went wrong
            try:
                conn.close()
            except Exception:
                pass

@contextmanager
def get_db_connection_context():
    """Context manager for database connections that guarantees cleanup."""
    conn = None
    try:
        conn = get_db_connection()
        yield conn
    except Exception as e:
        logger.error(f"Error in connection context: {e}")
        if conn and not conn.closed:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.warning(f"Error during rollback: {rollback_error}")
        raise e
    finally:
        if conn:
            return_db_connection(conn)

def get_pool_status():
    """Get current pool status for monitoring."""
    if db_pool is None:
        return {"status": "not_initialized"}
    
    # We can access pool internals, but be careful about thread safety of these attributes
    # _used and _pool are internal to SimpleConnectionPool, but reading len() is generally safe enough for stats
    try:
        active_count = len(db_pool._used)
        available_count = len(db_pool._pool)
    except Exception:
        active_count = -1
        available_count = -1

    with _tracking_lock:
        tracked_count = len(_active_connections)

    return {
        "status": "active",
        "min_connections": db_pool.minconn,
        "max_connections": db_pool.maxconn,
        "active_connections": active_count,
        "available_connections": available_count,
        "tracked_connections": tracked_count
    }
        
def close_db_pool():
    """Close all connections in the pool."""
    global db_pool
    if db_pool is not None:
        db_pool.closeall()
        logger.info("Database pool closed")
        db_pool = None

# Initialize pool on module import
try:
    init_db_pool()
except Exception as e:
    logger.warning(f"Failed to initialize pool on import: {e}")
