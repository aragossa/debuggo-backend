import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from typing import Optional
import logging


class System:
    _instance = None
    _pool: Optional[SimpleConnectionPool] = None
    logger = logging.getLogger(__name__)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(System, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Load environment variables from .env file
        env_path = Path(__file__).parent.parent / '.env'
        load_dotenv(dotenv_path=env_path)

        # Database configuration
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = os.getenv('DB_PORT', '5432')
        self.db_name = os.getenv('DB_NAME', 'postgres')
        self.db_user = os.getenv('DB_USER', 'postgres')
        self.db_password = os.getenv('DB_PASSWORD', 'postgres')

        # Kafka configuration
        self.kafka_host = os.getenv('KAFKA_HOST', 'localhost')
        self.kafka_port = os.getenv('KAFKA_PORT', '9092')

        # Connection pool configuration
        self.min_connections = int(os.getenv('DB_MIN_CONNECTIONS', '1'))
        self.max_connections = int(os.getenv('DB_MAX_CONNECTIONS', '10'))

        # AI model configuration
        self.ai_model = os.getenv('AI_MODEL', 'gemini').lower()
        self.gemini_api_key = os.getenv('GEMINI_API')
        self.claude_api_key = os.getenv('CLAUDE_API')

        self._initialized = True

        # Initialize the connection pool
        self._initialize_connection_pool()

    def _initialize_connection_pool(self) -> None:
        """Initialize the database connection pool."""
        try:
            if System._pool is None:
                System._pool = SimpleConnectionPool(
                    minconn=self.min_connections,
                    maxconn=self.max_connections,
                    host=self.db_host,
                    port=self.db_port,
                    database=self.db_name,
                    user=self.db_user,
                    password=self.db_password
                )
                self.logger.info("Database connection pool initialized successfully")
        except psycopg2.Error as e:
            self.logger.error(f"Failed to initialize database connection pool: {str(e)}")
            raise

    @classmethod
    def get_db_connection(cls):
        """
        Get a connection from the pool.

        Returns:
            psycopg2.extensions.connection: A database connection from the pool
        """
        if cls._pool is None:
            cls()._initialize_connection_pool()

        try:
            connection = cls._pool.getconn()
            return connection
        except psycopg2.Error as e:
            cls.logger.error(f"Failed to get database connection: {str(e)}")
            raise

    @classmethod
    def return_connection(cls, connection):
        """
        Return a connection to the pool.

        Args:
            connection: The connection to return to the pool
        """
        if cls._pool is not None:
            cls._pool.putconn(connection)

    @classmethod
    def close_all_connections(cls):
        """Close all connections in the pool."""
        if cls._pool is not None:
            cls._pool.closeall()
            cls._pool = None
            cls.logger.info("All database connections closed")

    @property
    def db_connection_string(self) -> str:
        """Get the database connection string."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    def validate_api_keys(self) -> bool:
        """Validate that required API keys are present."""
        if self.ai_model == 'gemini' and not self.gemini_api_key:
            self.logger.warning("GEMINI_API key is not set in .env file")
            return False
        if self.ai_model == 'claude' and not self.claude_api_key:
            self.logger.warning("CLAUDE_API key is not set in .env file")
            return False
        return True