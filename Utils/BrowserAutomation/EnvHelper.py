from contextlib import contextmanager
from typing import Optional
from Utils.System import System

class EnvHelper:
    def __init__(self):
        self._base_url: Optional[str] = None
        self._login: Optional[str] = None
        self._password: Optional[str] = None

    @contextmanager
    def get_db_connection(self):
        """Context manager for database connections."""
        connection = None
        try:
            connection = System.get_db_connection()
            yield connection
        finally:
            if connection:
                System._pool.putconn(connection)

    def _get_variable(self, name: str) -> str:
        """Generic method to fetch any variable from the database."""
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT value FROM test_variables WHERE name = %s',
                    (name,)
                )
                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Variable '{name}' not found in database")
                return result[0]

    @property
    def base_url(self) -> str:
        """Get cached base_url or fetch from database."""
        if self._base_url is None:
            self._base_url = self._get_variable('base_url')
        return self._base_url

    @property
    def login(self) -> str:
        """Get cached login or fetch from database."""
        if self._login is None:
            self._login = self._get_variable('login')
        return self._login

    @property
    def password(self) -> str:
        """Get cached password or fetch from database."""
        if self._password is None:
            self._password = self._get_variable('password')
        return self._password

    def clear_cache(self) -> None:
        """Clear all cached values."""
        self._base_url = None
        self._login = None
        self._password = None