"""
VariableManager: Handles variable scoping, resolution, and substitution

Supports variable scopes:
- Global: Available to all tests
- Client: Available to all tests in a client
- Project: Available to tests in a project
- Environment: Environment-specific overrides (highest precedence)

Features:
- Scope-based variable resolution with precedence
- Variable substitution in test steps
- Variable extraction from API responses
- Variable substitution logging
"""

import logging
import re
import json
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class VariableManager:
    """Manages variable scoping, resolution, and substitution."""
    
    # Scope precedence (higher number = higher precedence)
    SCOPE_PRECEDENCE = {
        'global': 1,
        'client': 2,
        'project': 3,
        'environment': 4
    }
    
    # Variable pattern for substitution
    VARIABLE_PATTERNS = [
        (r'%(\w+)%', 'percent'),  # %variable_name%
        (r'\{\{(\w+)\}\}', 'braces'),  # {{variable_name}}
    ]
    
    def __init__(self):
        """Initialize VariableManager."""
        self.logger = logging.getLogger(__name__)
        self.system = System()
        self._variable_cache = {}  # Cache for resolved variables
        
    def get_variable(
        self,
        name: str,
        client_id: Optional[str] = None,
        project_id: Optional[str] = None,
        environment_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Get variable value with scope resolution.
        
        Resolves variables in order of precedence:
        1. Environment-specific (highest)
        2. Project-specific
        3. Client-specific
        4. Global (lowest)
        
        Args:
            name: Variable name
            client_id: Client ID for scope resolution
            project_id: Project ID for scope resolution
            environment_id: Environment ID for scope resolution
            
        Returns:
            Variable value or None if not found
        """
        try:
            # Create cache key
            cache_key = f"{name}_{client_id}_{project_id}_{environment_id}"
            if cache_key in self._variable_cache:
                return self._variable_cache[cache_key]
            
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Use the database function for scope resolution
                    cursor.execute(
                        """
                        SELECT value FROM get_variable_by_scope(
                            %s, %s, %s, %s
                        )
                        """,
                        (name, client_id, project_id, environment_id)
                    )
                    result = cursor.fetchone()
                    value = result[0] if result else None
                    
                    # Cache the result
                    if value:
                        self._variable_cache[cache_key] = value
                    
                    return value
            finally:
                return_db_connection(conn)
                
        except Exception as e:
            self.logger.error(f"Error getting variable '{name}': {e}")
            return None
    
    def get_all_variables(
        self,
        client_id: Optional[str] = None,
        project_id: Optional[str] = None,
        environment_id: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Get all variables for a given scope.
        
        Args:
            client_id: Client ID for scope resolution
            project_id: Project ID for scope resolution
            environment_id: Environment ID for scope resolution
            
        Returns:
            Dictionary of variable names and values
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Build query based on scope
                    if environment_id:
                        cursor.execute(
                            """
                            SELECT DISTINCT name, value FROM v_variables_with_scope
                            WHERE environment_id = %s OR project_id = %s OR client_id = %s OR scope = 'global'
                            ORDER BY name, scope_precedence DESC
                            """,
                            (environment_id, project_id, client_id)
                        )
                    elif project_id:
                        cursor.execute(
                            """
                            SELECT DISTINCT name, value FROM v_variables_with_scope
                            WHERE project_id = %s OR client_id = %s OR scope = 'global'
                            ORDER BY name, scope_precedence DESC
                            """,
                            (project_id, client_id)
                        )
                    elif client_id:
                        cursor.execute(
                            """
                            SELECT DISTINCT name, value FROM v_variables_with_scope
                            WHERE client_id = %s OR scope = 'global'
                            ORDER BY name, scope_precedence DESC
                            """,
                            (client_id,)
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT DISTINCT name, value FROM v_variables_with_scope
                            WHERE scope = 'global'
                            ORDER BY name
                            """
                        )
                    
                    # Build result dictionary (later rows override earlier ones)
                    result = {}
                    for row in cursor.fetchall():
                        result[row[0]] = row[1]
                    
                    return result
            finally:
                return_db_connection(conn)
                
        except Exception as e:
            self.logger.error(f"Error getting all variables: {e}")
            return {}
    
    def substitute_variables(
        self,
        text: str,
        client_id: Optional[str] = None,
        project_id: Optional[str] = None,
        environment_id: Optional[int] = None,
        session_variables: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Substitute variables in text.
        
        Supports multiple formats:
        - %variable_name%
        - {{variable_name}}
        
        Resolution order:
        1. Session variables (extracted during execution)
        2. Scoped variables (environment > project > client > global)
        
        Args:
            text: Text containing variable placeholders
            client_id: Client ID for scope resolution
            project_id: Project ID for scope resolution
            environment_id: Environment ID for scope resolution
            session_variables: Variables extracted during test execution
            
        Returns:
            Text with variables substituted
        """
        if not isinstance(text, str):
            return text
        
        result = text
        session_variables = session_variables or {}
        
        # Get all available variables
        scoped_variables = self.get_all_variables(client_id, project_id, environment_id)
        
        # Merge session variables (higher precedence)
        all_variables = {**scoped_variables, **session_variables}
        
        # Substitute variables
        for pattern, pattern_type in self.VARIABLE_PATTERNS:
            matches = re.finditer(pattern, result)
            for match in matches:
                var_name = match.group(1)
                if var_name in all_variables:
                    var_value = str(all_variables[var_name])
                    result = result.replace(match.group(0), var_value)
                else:
                    self.logger.warning(f"Variable '{var_name}' not found in scope")
        
        return result
    
    def substitute_variables_in_dict(
        self,
        data: Dict,
        client_id: Optional[str] = None,
        project_id: Optional[str] = None,
        environment_id: Optional[int] = None,
        session_variables: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        Recursively substitute variables in a dictionary.
        
        Args:
            data: Dictionary containing variable placeholders
            client_id: Client ID for scope resolution
            project_id: Project ID for scope resolution
            environment_id: Environment ID for scope resolution
            session_variables: Variables extracted during test execution
            
        Returns:
            Dictionary with variables substituted
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.substitute_variables(
                    value, client_id, project_id, environment_id, session_variables
                )
            elif isinstance(value, dict):
                result[key] = self.substitute_variables_in_dict(
                    value, client_id, project_id, environment_id, session_variables
                )
            elif isinstance(value, list):
                result[key] = [
                    self.substitute_variables(item, client_id, project_id, environment_id, session_variables)
                    if isinstance(item, str)
                    else self.substitute_variables_in_dict(item, client_id, project_id, environment_id, session_variables)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        
        return result
    
    def log_substitution(
        self,
        test_run_id: int,
        test_step_id: int,
        variable_name: str,
        variable_scope: str,
        original_value: str,
        substituted_value: str
    ) -> None:
        """
        Log variable substitution for audit trail.
        
        Args:
            test_run_id: Test run ID
            test_step_id: Test step ID
            variable_name: Variable name
            variable_scope: Variable scope (global, client, project, environment)
            original_value: Original value before substitution
            substituted_value: Value after substitution
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT log_variable_substitution(%s, %s, %s, %s, %s, %s)
                        """,
                        (test_run_id, test_step_id, variable_name, variable_scope,
                         original_value, substituted_value)
                    )
                    conn.commit()
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error logging variable substitution: {e}")
    
    def log_extraction(
        self,
        test_run_id: int,
        test_step_id: int,
        variable_name: str,
        extracted_value: str,
        extraction_path: str
    ) -> None:
        """
        Log variable extraction for audit trail.
        
        Args:
            test_run_id: Test run ID
            test_step_id: Test step ID
            variable_name: Variable name
            extracted_value: Extracted value
            extraction_path: Path used for extraction (e.g., JSONPath)
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT log_variable_extraction(%s, %s, %s, %s, %s)
                        """,
                        (test_run_id, test_step_id, variable_name, extracted_value, extraction_path)
                    )
                    conn.commit()
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error logging variable extraction: {e}")
    
    def create_variable(
        self,
        name: str,
        value: str,
        scope: str = 'global',
        client_id: Optional[str] = None,
        project_id: Optional[str] = None,
        environment_id: Optional[int] = None,
        is_secret: bool = False,
        description: Optional[str] = None
    ) -> Optional[int]:
        """
        Create a new variable.
        
        Args:
            name: Variable name
            value: Variable value
            scope: Variable scope (global, client, project, environment)
            client_id: Client ID (required for client scope)
            project_id: Project ID (required for project scope)
            environment_id: Environment ID (required for environment scope)
            is_secret: Whether the variable is secret
            description: Variable description
            
        Returns:
            Variable ID or None if creation failed
        """
        try:
            # Validate scope
            if scope not in self.SCOPE_PRECEDENCE:
                self.logger.error(f"Invalid scope: {scope}")
                return None
            
            # Validate scope requirements
            if scope == 'client' and not client_id:
                self.logger.error("client_id required for client scope")
                return None
            if scope == 'project' and not project_id:
                self.logger.error("project_id required for project scope")
                return None
            if scope == 'environment' and not environment_id:
                self.logger.error("environment_id required for environment scope")
                return None
            
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO test_variables (
                            name, value, scope, client_id, project_id, environment_id,
                            is_secret, description, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                        RETURNING id
                        """,
                        (name, value, scope, client_id, project_id, environment_id,
                         is_secret, description)
                    )
                    result = cursor.fetchone()
                    var_id = result[0] if result else None
                    conn.commit()
                    
                    # Clear cache
                    self._variable_cache.clear()
                    
                    return var_id
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error creating variable: {e}")
            return None
    
    def update_variable(
        self,
        variable_id: int,
        value: Optional[str] = None,
        description: Optional[str] = None,
        is_secret: Optional[bool] = None
    ) -> bool:
        """
        Update an existing variable.
        
        Args:
            variable_id: Variable ID
            value: New value (optional)
            description: New description (optional)
            is_secret: New is_secret value (optional)
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            updates = []
            params = []
            
            if value is not None:
                updates.append("value = %s")
                params.append(value)
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            if is_secret is not None:
                updates.append("is_secret = %s")
                params.append(is_secret)
            
            if not updates:
                return False
            
            params.append(variable_id)
            
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    query = f"UPDATE test_variables SET {', '.join(updates)} WHERE id = %s"
                    cursor.execute(query, params)
                    conn.commit()
                    
                    # Clear cache
                    self._variable_cache.clear()
                    
                    return cursor.rowcount > 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error updating variable: {e}")
            return False
    
    def delete_variable(self, variable_id: int) -> bool:
        """
        Delete a variable.
        
        Args:
            variable_id: Variable ID
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM test_variables WHERE id = %s", (variable_id,))
                    conn.commit()
                    
                    # Clear cache
                    self._variable_cache.clear()
                    
                    return cursor.rowcount > 0
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error deleting variable: {e}")
            return False
    
    def clear_cache(self) -> None:
        """Clear variable cache."""
        self._variable_cache.clear()
        self.logger.debug("Variable cache cleared")
