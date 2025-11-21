"""
ToolRegistry: Manages available tools for AI agents to use.

Tools are functions that agents can call to:
- Analyze page elements
- Execute test steps
- Search for similar tests
- Validate selectors
- Extract API responses
- Get error resolutions

This enables agents to take actions beyond just generating text.
"""

import json
import logging
import time
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass
from auroqa.Utils.System import System

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Definition of an available tool."""
    name: str
    description: str
    params: Dict[str, str]  # param_name -> param_type
    returns: str
    func: Callable


class ToolRegistry:
    """Registry of available tools for AI agents."""

    def __init__(self):
        self.system = System()
        self.logger = logging.getLogger(__name__)
        self.tools: Dict[str, ToolDefinition] = {}
        self.execution_history: List[Dict] = []
        self._initialize_default_tools()

    def register_tool(self, name: str, func: Callable, description: str,
                     params: Dict[str, str], returns: str) -> None:
        """
        Register a new tool.

        Args:
            name: Tool name
            func: Callable function
            description: Tool description
            params: Parameter definitions
            returns: Return type description
        """
        tool_def = ToolDefinition(
            name=name,
            description=description,
            params=params,
            returns=returns,
            func=func
        )

        self.tools[name] = tool_def
        self.logger.info(f"✓ Registered tool: {name}")

    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool

        Returns:
            Tool result
        """
        if tool_name not in self.tools:
            error_msg = f"Tool '{tool_name}' not found"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'available_tools': list(self.tools.keys())
            }

        try:
            # Validate parameters
            if not self._validate_tool_params(tool_name, params):
                return {
                    'success': False,
                    'error': f"Invalid parameters for tool '{tool_name}'",
                    'expected_params': list(self.tools[tool_name].params.keys())
                }

            # Execute tool
            start_time = time.time()
            tool_def = self.tools[tool_name]
            result = tool_def.func(**params)
            execution_time = time.time() - start_time

            # Record execution
            execution_record = {
                'tool_name': tool_name,
                'params': params,
                'result': result,
                'execution_time_ms': execution_time * 1000,
                'success': True,
                'timestamp': time.time()
            }
            self.execution_history.append(execution_record)

            self.logger.info(
                f"✓ Executed tool '{tool_name}' in {execution_time*1000:.1f}ms"
            )

            return {
                'success': True,
                'result': result,
                'execution_time_ms': execution_time * 1000
            }

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error executing tool '{tool_name}': {error_msg}")

            execution_record = {
                'tool_name': tool_name,
                'params': params,
                'error': error_msg,
                'success': False,
                'timestamp': time.time()
            }
            self.execution_history.append(execution_record)

            return {
                'success': False,
                'error': error_msg
            }

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools.

        Returns:
            List of tool definitions
        """
        tools_list = []
        for name, tool_def in self.tools.items():
            tools_list.append({
                'name': name,
                'description': tool_def.description,
                'params': tool_def.params,
                'returns': tool_def.returns
            })

        return tools_list

    def validate_tool_params(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """
        Validate parameters for a tool.

        Args:
            tool_name: Name of the tool
            params: Parameters to validate

        Returns:
            True if valid, False otherwise
        """
        return self._validate_tool_params(tool_name, params)

    def get_tool_definition(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get definition of a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool definition or None
        """
        if tool_name not in self.tools:
            return None

        tool_def = self.tools[tool_name]
        return {
            'name': tool_def.name,
            'description': tool_def.description,
            'params': tool_def.params,
            'returns': tool_def.returns
        }

    def get_execution_history(self, limit: int = 100) -> List[Dict]:
        """
        Get tool execution history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of execution records
        """
        return self.execution_history[-limit:]

    def clear_execution_history(self) -> None:
        """Clear execution history."""
        self.execution_history = []
        self.logger.info("✓ Cleared execution history")

    # Default tools

    def _initialize_default_tools(self) -> None:
        """Initialize default tools."""
        self.register_tool(
            name='analyze_page_elements',
            func=self._tool_analyze_page_elements,
            description='Analyze page HTML and extract interactive elements',
            params={
                'page_html': 'str',
                'element_type': 'str (optional)'
            },
            returns='List of elements with properties'
        )

        self.register_tool(
            name='search_similar_tests',
            func=self._tool_search_similar_tests,
            description='Find similar past tests using vector similarity',
            params={
                'test_description': 'str',
                'top_k': 'int'
            },
            returns='List of similar tests'
        )

        self.register_tool(
            name='validate_selector',
            func=self._tool_validate_selector,
            description='Check if XPath/CSS selector is valid',
            params={
                'selector': 'str',
                'selector_type': 'str (xpath or css)'
            },
            returns='Validation result'
        )

        self.register_tool(
            name='extract_api_response',
            func=self._tool_extract_api_response,
            description='Parse API response and extract data',
            params={
                'response': 'dict',
                'schema': 'dict (optional)'
            },
            returns='Extracted data'
        )

        self.register_tool(
            name='get_error_resolution',
            func=self._tool_get_error_resolution,
            description='Find how to resolve a specific error',
            params={
                'error_type': 'str',
                'error_message': 'str (optional)'
            },
            returns='Resolution suggestions'
        )

        self.logger.info("✓ Initialized default tools")

    # Tool implementations

    def _tool_analyze_page_elements(self, page_html: str,
                                   element_type: str = None) -> Dict[str, Any]:
        """Analyze page HTML and extract elements."""
        try:
            # Simple HTML parsing - in production would use BeautifulSoup
            elements = {
                'inputs': [],
                'buttons': [],
                'links': [],
                'forms': []
            }

            if 'input' in page_html.lower():
                elements['inputs'].append({
                    'type': 'input',
                    'count': page_html.lower().count('<input'),
                    'description': 'Input fields found'
                })

            if 'button' in page_html.lower():
                elements['buttons'].append({
                    'type': 'button',
                    'count': page_html.lower().count('<button'),
                    'description': 'Buttons found'
                })

            if 'a href' in page_html.lower():
                elements['links'].append({
                    'type': 'link',
                    'count': page_html.lower().count('<a href'),
                    'description': 'Links found'
                })

            return {
                'success': True,
                'elements': elements,
                'total_elements': sum(
                    len(v) for v in elements.values() if isinstance(v, list)
                )
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _tool_search_similar_tests(self, test_description: str,
                                   top_k: int = 5) -> Dict[str, Any]:
        """Search for similar tests."""
        try:
            # In production, would use vector similarity search
            return {
                'success': True,
                'similar_tests': [],
                'search_query': test_description,
                'top_k': top_k,
                'note': 'Vector similarity search not yet implemented'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _tool_validate_selector(self, selector: str,
                               selector_type: str = 'xpath') -> Dict[str, Any]:
        """Validate XPath or CSS selector."""
        try:
            # Basic validation
            is_valid = True
            issues = []

            if selector_type == 'xpath':
                if not selector.startswith('//') and not selector.startswith('/'):
                    is_valid = False
                    issues.append("XPath should start with // or /")

                if "'" in selector and '"' in selector:
                    issues.append("Mixed quotes detected - may cause issues")

            elif selector_type == 'css':
                if selector.startswith('/'):
                    is_valid = False
                    issues.append("CSS selector should not start with /")

            return {
                'success': True,
                'is_valid': is_valid,
                'selector': selector,
                'selector_type': selector_type,
                'issues': issues
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _tool_extract_api_response(self, response: dict,
                                   schema: dict = None) -> Dict[str, Any]:
        """Extract data from API response."""
        try:
            extracted = {
                'status_code': response.get('status_code'),
                'headers': response.get('headers', {}),
                'body': response.get('body', {}),
                'data_fields': list(response.get('body', {}).keys())
            }

            return {
                'success': True,
                'extracted': extracted,
                'field_count': len(extracted['data_fields'])
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _tool_get_error_resolution(self, error_type: str,
                                   error_message: str = None) -> Dict[str, Any]:
        """Get resolution suggestions for an error."""
        try:
            # Common error resolutions
            resolutions = {
                'element_not_found': [
                    'Check if element selector is correct',
                    'Wait for element to load',
                    'Check if element is visible'
                ],
                'timeout': [
                    'Increase wait timeout',
                    'Check if page is loading correctly',
                    'Verify network connectivity'
                ],
                'invalid_selector': [
                    'Validate XPath/CSS syntax',
                    'Use browser DevTools to test selector',
                    'Check for special characters'
                ],
                'assertion_failed': [
                    'Verify expected value',
                    'Check actual vs expected',
                    'Review test data'
                ]
            }

            suggestions = resolutions.get(error_type, [
                'Check error message for details',
                'Review recent changes',
                'Try alternative approach'
            ])

            return {
                'success': True,
                'error_type': error_type,
                'suggestions': suggestions,
                'suggestion_count': len(suggestions)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    # Helper methods

    def _validate_tool_params(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """Validate parameters for a tool."""
        if tool_name not in self.tools:
            return False

        tool_def = self.tools[tool_name]

        # Check required parameters
        for param_name in tool_def.params.keys():
            if param_name not in params and '(optional)' not in tool_def.params[param_name]:
                return False

        return True
