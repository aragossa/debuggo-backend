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
_active_connections = weakref.WeakSet()
_connection_lock = threading.Lock()

def init_db_pool():
    """Initialize the database connection pool."""
    global db_pool
    try:
        # Pool size: 10-100 connections
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
    
    with _connection_lock:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                conn = db_pool.getconn()
                
                # Validate connection is not closed
                if conn.closed:
                    logger.warning(f"Retrieved closed connection on attempt {attempt + 1}, trying to get new one")
                    # CRITICAL: Return to pool before closing, otherwise pool thinks it's still in use
                    try:
                        db_pool.putconn(conn, close=True)
                    except:
                        try:
                            conn.close()
                        except:
                            pass
                    continue
                
                # Test connection with a simple query
                try:
                    with conn.cursor() as test_cur:
                        test_cur.execute("SELECT 1")
                        test_cur.fetchone()
                except Exception as e:
                    logger.warning(f"Connection failed test query on attempt {attempt + 1}: {e}")
                    # CRITICAL: Return to pool before closing
                    try:
                        db_pool.putconn(conn, close=True)
                    except:
                        try:
                            conn.close()
                        except:
                            pass
                    continue
                
                # Track this connection as active
                _active_connections.add(conn)
                logger.debug(f"Valid connection retrieved. Active: {len(db_pool._used)}, Tracked: {len(_active_connections)}")
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
        with _connection_lock:
            try:
                # Check if connection is in our tracked set
                if conn not in _active_connections:
                    logger.warning("Attempting to return untracked connection - forcing close instead")
                    try:
                        conn.close()
                    except:
                        pass
                    return
                
                # Remove from tracking
                try:
                    _active_connections.discard(conn)
                except:
                    pass
                
                # Only return valid connections to pool
                if not conn.closed:
                    try:
                        # Rollback any uncommitted transactions
                        conn.rollback()
                        # Verify connection is still valid before returning
                        with conn.cursor() as test_cur:
                            test_cur.execute("SELECT 1")
                            test_cur.fetchone()
                        
                        # Connection is valid, return to pool
                        db_pool.putconn(conn)
                        logger.debug(f"Connection returned to pool. Active: {len(db_pool._used)}, Tracked: {len(_active_connections)}")
                    except Exception as e:
                        logger.warning(f"Connection invalid during return, closing instead: {e}")
                        try:
                            conn.close()
                        except:
                            pass
                else:
                    logger.debug("Connection already closed, not returning to pool")
                    
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
                # Force close the connection if it can't be returned properly
                try:
                    conn.close()
                except:
                    pass

@contextmanager
def get_db_connection_context():
    """Context manager for database connections that guarantees cleanup."""
    conn = None
    try:
        conn = get_db_connection()
        logger.debug(f"Context manager got connection with closed={conn.closed}")
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
    
    with _connection_lock:
        return {
            "status": "active",
            "min_connections": db_pool.minconn,
            "max_connections": db_pool.maxconn,
            "active_connections": len(db_pool._used),
            "available_connections": len(db_pool._pool),
            "tracked_connections": len(_active_connections)
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
