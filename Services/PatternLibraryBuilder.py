"""
PatternLibraryBuilder Service

Extracts patterns from successful test cases and builds a pattern library.
Automatically categorizes, tags, and generates embeddings for patterns.

Used to populate the vector database with high-quality patterns for few-shot learning.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta

from auroqa.Services.VectorStore import VectorStore
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator
from auroqa.Utils.System import System

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPattern:
    """Represents a pattern extracted from a test"""
    pattern_type: str
    pattern_data: Dict[str, Any]
    tags: List[str]
    confidence: float  # 0-1, how confident we are in this pattern
    source_test_id: int
    source_step_number: int


class PatternLibraryBuilder:
    """
    Builds and maintains the pattern library.
    
    Responsibilities:
    - Extract patterns from successful test cases
    - Categorize and tag patterns
    - Generate embeddings
    - Store patterns in vector database
    - Update pattern statistics
    - Identify high-quality patterns
    """
    
    def __init__(self):
        """Initialize pattern library builder"""
        self.vector_store = VectorStore()
        self.embedding_generator = EmbeddingGenerator()
        self.system = System()
        logger.info("PatternLibraryBuilder initialized")
    
    def build_library_from_successful_tests(
        self,
        client_id: Optional[str] = None,
        min_success_rate: float = 0.9,
        limit: int = 100
    ) -> Dict[str, int]:
        """
        Build pattern library from successful test cases.
        
        Args:
            client_id: Optional client ID filter
            min_success_rate: Minimum success rate for test cases to consider
            limit: Maximum number of test cases to process
        
        Returns:
            Dictionary with counts: {'selectors': 10, 'api_flows': 5, ...}
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Get successful test cases
                query = """
                    SELECT id, name, description, test_type
                    FROM test_cases
                    WHERE success_rate >= %s
                """
                params = [min_success_rate]
                
                if client_id:
                    query += " AND client_id = %s"
                    params.append(client_id)
                
                query += " ORDER BY success_rate DESC LIMIT %s"
                params.append(limit)
                
                cur.execute(query, params)
                test_cases = cur.fetchall()
                
                logger.info(
                    f"Found {len(test_cases)} successful test cases "
                    f"(min_success: {min_success_rate})"
                )
                
                # Extract patterns from each test case
                counts = {
                    'selectors': 0,
                    'api_flows': 0,
                    'error_resolutions': 0,
                    'ui_components': 0
                }
                
                for test_case in test_cases:
                    test_id, name, description, test_type = test_case
                    
                    # Extract patterns based on test type
                    if test_type == 'ui':
                        ui_counts = self._extract_ui_patterns(test_id, name, client_id, conn)
                        for key in ui_counts:
                            counts[key] += ui_counts[key]
                    
                    elif test_type == 'api':
                        api_counts = self._extract_api_patterns(test_id, name, client_id, conn)
                        for key in api_counts:
                            counts[key] += api_counts[key]
                
                logger.info(f"Pattern library built: {counts}")
                return counts
        
        except Exception as e:
            logger.error(f"Failed to build pattern library: {str(e)}")
            return {}
        finally:
            self.system.return_connection(conn)
    
    def _extract_ui_patterns(
        self,
        test_case_id: int,
        test_name: str,
        client_id: Optional[str],
        conn
    ) -> Dict[str, int]:
        """
        Extract patterns from a UI test case.
        
        Args:
            test_case_id: ID of the test case
            test_name: Name of the test case
            client_id: Client ID for multi-tenancy
            conn: Database connection
        
        Returns:
            Dictionary with pattern counts
        """
        counts = {
            'selectors': 0,
            'ui_components': 0,
            'error_resolutions': 0
        }
        
        try:
            with conn.cursor() as cur:
                # Get all steps from the test case
                cur.execute("""
                    SELECT id, step_order, action, element_path, css_selector, value, description
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order
                """, (test_case_id,))
                
                steps = cur.fetchall()
                
                for step in steps:
                    step_id, step_order, action, element_path, css_selector, value, description = step
                    
                    # Extract selector pattern
                    if element_path:
                        selector_pattern = self._create_selector_pattern(
                            element_path, css_selector, action, description
                        )
                        
                        if self._store_pattern(
                            selector_pattern, test_case_id, step_order, client_id
                        ):
                            counts['selectors'] += 1
                    
                    # Extract UI component pattern
                    if action and description:
                        component_pattern = self._create_ui_component_pattern(
                            action, description, value
                        )
                        
                        if self._store_pattern(
                            component_pattern, test_case_id, step_order, client_id
                        ):
                            counts['ui_components'] += 1
        
        except Exception as e:
            logger.error(f"Failed to extract UI patterns from test {test_case_id}: {str(e)}")
        
        return counts
    
    def _extract_api_patterns(
        self,
        test_case_id: int,
        test_name: str,
        client_id: Optional[str],
        conn
    ) -> Dict[str, int]:
        """
        Extract patterns from an API test case.
        
        Args:
            test_case_id: ID of the test case
            test_name: Name of the test case
            client_id: Client ID for multi-tenancy
            conn: Database connection
        
        Returns:
            Dictionary with pattern counts
        """
        counts = {
            'api_flows': 0,
            'error_resolutions': 0
        }
        
        try:
            with conn.cursor() as cur:
                # Get all steps from the test case
                cur.execute("""
                    SELECT id, step_order, description
                    FROM test_steps
                    WHERE test_case_id = %s AND action = 'api_request'
                    ORDER BY step_order
                """, (test_case_id,))
                
                steps = cur.fetchall()
                
                for step in steps:
                    step_id, step_order, description = step
                    
                    try:
                        # Parse description as JSON (API step format)
                        step_data = json.loads(description) if isinstance(description, str) else description
                        
                        # Extract API flow pattern
                        api_pattern = self._create_api_flow_pattern(step_data, test_name)
                        
                        if self._store_pattern(
                            api_pattern, test_case_id, step_order, client_id
                        ):
                            counts['api_flows'] += 1
                    
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse API step {step_id} as JSON")
                        continue
        
        except Exception as e:
            logger.error(f"Failed to extract API patterns from test {test_case_id}: {str(e)}")
        
        return counts
    
    def _create_selector_pattern(
        self,
        xpath: str,
        css: Optional[str],
        action: str,
        description: str
    ) -> ExtractedPattern:
        """
        Create a selector pattern from a test step.
        
        Args:
            xpath: XPath selector
            css: CSS selector (optional)
            action: Action type (click, type, etc.)
            description: Step description
        
        Returns:
            ExtractedPattern object
        """
        pattern_data = {
            'xpath': xpath,
            'css': css,
            'action': action,
            'description': description,
            'specificity': self._calculate_selector_specificity(xpath)
        }
        
        tags = ['selector', action]
        if 'button' in description.lower():
            tags.append('button')
        elif 'input' in description.lower():
            tags.append('input')
        elif 'dropdown' in description.lower():
            tags.append('dropdown')
        
        return ExtractedPattern(
            pattern_type='selector',
            pattern_data=pattern_data,
            tags=tags,
            confidence=0.85,  # Selectors from successful tests are fairly reliable
            source_test_id=0,  # Will be set by caller
            source_step_number=0
        )
    
    def _create_ui_component_pattern(
        self,
        action: str,
        description: str,
        value: Optional[str]
    ) -> ExtractedPattern:
        """
        Create a UI component interaction pattern.
        
        Args:
            action: Action type (click, type, select, etc.)
            description: Step description
            value: Optional value used in the action
        
        Returns:
            ExtractedPattern object
        """
        pattern_data = {
            'action': action,
            'description': description,
            'value_type': type(value).__name__ if value else None,
            'has_value': value is not None
        }
        
        tags = ['ui_component', action]
        if 'form' in description.lower():
            tags.append('form')
        elif 'modal' in description.lower():
            tags.append('modal')
        elif 'table' in description.lower():
            tags.append('table')
        
        return ExtractedPattern(
            pattern_type='ui_component',
            pattern_data=pattern_data,
            tags=tags,
            confidence=0.8,
            source_test_id=0,
            source_step_number=0
        )
    
    def _create_api_flow_pattern(
        self,
        step_data: Dict[str, Any],
        test_name: str
    ) -> ExtractedPattern:
        """
        Create an API flow pattern from a test step.
        
        Args:
            step_data: API step data (method, endpoint, etc.)
            test_name: Name of the test case
        
        Returns:
            ExtractedPattern object
        """
        pattern_data = {
            'method': step_data.get('method', 'GET'),
            'endpoint': step_data.get('endpoint', ''),
            'has_body': 'body' in step_data and step_data['body'],
            'has_headers': 'headers' in step_data and step_data['headers'],
            'expected_status': step_data.get('expected_status', 200),
            'description': step_data.get('description', '')
        }
        
        tags = ['api_flow', step_data.get('method', 'GET').lower()]
        
        # Tag by endpoint pattern
        endpoint = step_data.get('endpoint', '')
        if '/users' in endpoint:
            tags.append('users')
        elif '/products' in endpoint:
            tags.append('products')
        elif '/auth' in endpoint:
            tags.append('auth')
        
        return ExtractedPattern(
            pattern_type='api_flow',
            pattern_data=pattern_data,
            tags=tags,
            confidence=0.9,  # API flows from successful tests are very reliable
            source_test_id=0,
            source_step_number=0
        )
    
    def _store_pattern(
        self,
        pattern: ExtractedPattern,
        test_case_id: int,
        step_number: int,
        client_id: Optional[str]
    ) -> bool:
        """
        Store an extracted pattern in the vector database.
        
        Args:
            pattern: ExtractedPattern to store
            test_case_id: Source test case ID
            step_number: Source step number
            client_id: Client ID for multi-tenancy
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate embedding
            embedding_result = self.embedding_generator.embed_text(
                json.dumps(pattern.pattern_data),
                pattern.pattern_type
            )
            
            # Store in vector database
            pattern_id = self.vector_store.store_pattern(
                pattern_type=pattern.pattern_type,
                pattern_data=pattern.pattern_data,
                embedding=embedding_result.embedding,
                tags=pattern.tags,
                created_by=None,  # System-generated
                client_id=client_id
            )
            
            # Record usage
            self.vector_store.record_pattern_usage(
                pattern_id=pattern_id,
                test_case_id=test_case_id,
                step_number=step_number,
                success=True,
                error_message=None
            )
            
            logger.debug(
                f"Stored {pattern.pattern_type} pattern {pattern_id} "
                f"from test {test_case_id} step {step_number}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to store pattern: {str(e)}")
            return False
    
    def _calculate_selector_specificity(self, selector: str) -> int:
        """
        Calculate specificity score of a selector.
        
        Higher specificity = more specific selector = more reliable.
        
        Args:
            selector: XPath or CSS selector
        
        Returns:
            Specificity score (0-100)
        """
        specificity = 0
        
        # ID selectors are most specific
        if '#' in selector or '[@id=' in selector:
            specificity += 30
        
        # Class selectors
        if '.' in selector or '[@class=' in selector:
            specificity += 20
        
        # Attribute selectors
        if '[@' in selector:
            specificity += 10
        
        # Tag selectors
        if '::' in selector or '//' in selector:
            specificity += 5
        
        # Avoid position-based selectors (less reliable)
        if '[1]' in selector or '[last()]' in selector:
            specificity -= 15
        
        # Avoid contains() (less reliable)
        if 'contains(' in selector:
            specificity -= 10
        
        return max(0, min(100, specificity))
    
    def get_library_stats(self, client_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about the pattern library.
        
        Args:
            client_id: Optional client ID filter
        
        Returns:
            Dictionary with library statistics
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                query = "SELECT pattern_type, COUNT(*) FROM patterns WHERE 1=1"
                params = []
                
                if client_id:
                    query += " AND client_id = %s"
                    params.append(client_id)
                
                query += " GROUP BY pattern_type"
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                stats = {
                    'total_patterns': 0,
                    'by_type': {},
                    'high_confidence': 0,
                    'total_usage': 0
                }
                
                for pattern_type, count in rows:
                    stats['by_type'][pattern_type] = count
                    stats['total_patterns'] += count
                
                # Get high confidence patterns
                query = "SELECT COUNT(*) FROM patterns WHERE success_rate >= 0.8"
                params = []
                if client_id:
                    query += " AND client_id = %s"
                    params.append(client_id)
                
                cur.execute(query, params)
                stats['high_confidence'] = cur.fetchone()[0]
                
                # Get total usage
                query = "SELECT COUNT(*) FROM pattern_usage"
                cur.execute(query)
                stats['total_usage'] = cur.fetchone()[0]
                
                logger.info(f"Library stats: {stats}")
                return stats
        
        except Exception as e:
            logger.error(f"Failed to get library stats: {str(e)}")
            return {}
        finally:
            self.system.return_connection(conn)
