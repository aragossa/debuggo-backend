from contextlib import contextmanager
from typing import Optional, Dict
from Utils.System import System
from Utils.BrowserAutomation.NameGenerator import NameGenerator
import re

class EnvHelper:
    def __init__(self, environment_vars: Dict = None):
        self._base_url: Optional[str] = None
        self._login: Optional[str] = None
        self._password: Optional[str] = None
        self._generated_names: Dict[str, str] = {}  # Cache for generated names
        
        # If environment variables are provided, use them directly
        if environment_vars:
            if 'base_url' in environment_vars and environment_vars['base_url']:
                self._base_url = environment_vars['base_url']
            if 'login' in environment_vars and environment_vars['login']:
                self._login = environment_vars['login']
            if 'password' in environment_vars and environment_vars['password']:
                self._password = environment_vars['password']

    def get_base_url(self) -> Optional[str]:
        """
        Get the base URL from environment variables.
        
        Returns:
            Optional[str]: The base URL or None if not set
        """
        return self._base_url
        
    @property
    def base_url(self) -> Optional[str]:
        """
        Get the base URL.
        
        Returns:
            Optional[str]: The base URL or None if not set
        """
        return self._base_url
    
    @base_url.setter
    def base_url(self, value: str):
        """Set base_url value."""
        self._base_url = value

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
        # If we already have the variable in memory, return it
        if name == 'base_url' and self._base_url:
            return self._base_url
        elif name == 'login' and self._login:
            return self._login
        elif name == 'password' and self._password:
            return self._password
            
        # Otherwise, try to fetch from the database
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
    def login(self) -> str:
        """Get cached login or fetch from database."""
        if self._login is None:
            raise ValueError("Login not provided in environment variables")
        return self._login
    
    @login.setter
    def login(self, value: str):
        """Set login value."""
        self._login = value

    @property
    def password(self) -> str:
        """Get cached password or fetch from database."""
        if self._password is None:
            raise ValueError("Password not provided in environment variables")
        return self._password
    
    @password.setter
    def password(self, value: str):
        """Set password value."""
        self._password = value

    def clear_cache(self) -> None:
        """Clear all cached values."""
        self._base_url = None
        self._login = None
        self._password = None
        
    def process_variables(self, text: str) -> str:
        """
        Process environment variables in a text string.
        
        Replaces %variable_name% with the actual value from environment variables.
        Supports dynamic name generation for unique names.
        
        Supported variables:
        - %base_url%, %login%, %password% - Standard environment variables
        - %unique_name% - Generates a unique random name (e.g., "a7b3c9d2")
        - %unique_name:prefix% - Generates unique name with prefix (e.g., "Client_a7b3c9d2")
        - %unique_name:prefix:suffix% - Generates unique name with prefix and suffix (e.g., "Client_a7b3c9d2_Test")
        - %timestamp_name% - Generates timestamp-based name (e.g., "20250129_143052")
        - %timestamp_name:prefix% - Generates timestamp name with prefix (e.g., "Client_20250129_143052")
        
        Args:
            text (str): The text containing environment variable placeholders
            
        Returns:
            str: The text with environment variables replaced with their values
        """
        if not text:
            return text
        
        # Find all %variable% patterns in the text
        pattern = r'%([^%]+)%'
        matches = re.findall(pattern, text)
        
        # Replace each variable with its value
        result = text
        for var_match in matches:
            var_name = var_match.strip()
            placeholder = f'%{var_match}%'
            
            try:
                # Handle standard environment variables
                if var_name == 'base_url':
                    value = self.base_url
                elif var_name == 'login':
                    value = self.login
                elif var_name == 'password':
                    value = self.password
                    
                # Handle dynamic name generation
                elif var_name.startswith('unique_name'):
                    # Check if we already generated this exact variable in this test run
                    if placeholder in self._generated_names:
                        value = self._generated_names[placeholder]
                    else:
                        # Parse the variable for prefix and suffix
                        parts = var_name.split(':')
                        prefix = parts[1] if len(parts) > 1 else ""
                        suffix = parts[2] if len(parts) > 2 else ""
                        
                        # Generate unique name
                        value = NameGenerator.generate_unique_name(prefix=prefix, suffix=suffix)
                        
                        # Cache it for consistency within this test run
                        self._generated_names[placeholder] = value
                        
                elif var_name.startswith('timestamp_name'):
                    # Check if we already generated this exact variable in this test run
                    if placeholder in self._generated_names:
                        value = self._generated_names[placeholder]
                    else:
                        # Parse the variable for prefix
                        parts = var_name.split(':')
                        prefix = parts[1] if len(parts) > 1 else ""
                        
                        # Generate timestamp name
                        value = NameGenerator.generate_timestamp_name(prefix=prefix)
                        
                        # Cache it for consistency within this test run
                        self._generated_names[placeholder] = value
                        
                elif var_name.startswith('uuid_name'):
                    # Check if we already generated this exact variable in this test run
                    if placeholder in self._generated_names:
                        value = self._generated_names[placeholder]
                    else:
                        # Parse the variable for prefix
                        parts = var_name.split(':')
                        prefix = parts[1] if len(parts) > 1 else ""
                        short = parts[2].lower() != 'false' if len(parts) > 2 else True
                        
                        # Generate UUID name
                        value = NameGenerator.generate_uuid_name(prefix=prefix, short=short)
                        
                        # Cache it for consistency within this test run
                        self._generated_names[placeholder] = value
                else:
                    # For unknown variables, leave the placeholder
                    continue
                    
                # Replace the placeholder with the actual value
                result = result.replace(placeholder, value)
                
            except ValueError:
                # If the variable doesn't exist, leave the placeholder
                continue
                
        return result