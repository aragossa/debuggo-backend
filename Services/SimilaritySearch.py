"""
SimilaritySearch Service

Finds similar patterns, tests, and error resolutions using vector similarity.
Used for few-shot learning and pattern recommendations.

Leverages VectorStore for efficient similarity search.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from auroqa.Services.VectorStore import VectorStore, Pattern
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator
from auroqa.Utils.System import System

logger = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    """Result of a similarity search"""
    item_id: int
    item_type: str  # 'pattern', 'test_case', etc.
    similarity_score: float  # 0-1
    item_data: Dict[str, Any]
    reason: Optional[str] = None


class SimilaritySearch:
    """
    Similarity search for patterns and test cases.
    
    Responsibilities:
    - Find similar selectors
    - Find similar API flows
    - Find similar test cases
    - Find error resolutions
    - Calculate similarity scores
    """
    
    def __init__(self):
        """Initialize similarity search"""
        self.vector_store = VectorStore()
        self.embedding_generator = EmbeddingGenerator()
        self.system = System()
        logger.info("SimilaritySearch initialized")
    
    def find_similar_selectors(
        self,
        selector: str,
        context: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        min_similarity: float = 0.7,
        client_id: Optional[str] = None
    ) -> List[Pattern]:
        """
        Find selectors similar to the given selector.
        
        Args:
            selector: XPath or CSS selector
            context: Optional context about the element
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold (0-1)
            client_id: Optional client ID filter
        
        Returns:
            List of similar selector patterns
        """
        try:
            # Generate embedding for the selector
            embedding_result = self.embedding_generator.embed_selector(selector, context)
            
            # Search for similar patterns
            patterns = self.vector_store.search_similar_patterns(
                query_embedding=embedding_result.embedding,
                pattern_type='selector',
                top_k=top_k,
                min_success_rate=0.6,  # Lower threshold for selectors
                client_id=client_id
            )
            
            logger.info(f"Found {len(patterns)} similar selectors for: {selector}")
            return patterns
        
        except Exception as e:
            logger.error(f"Failed to find similar selectors: {str(e)}")
            return []
    
    def find_similar_api_flows(
        self,
        flow: Dict[str, Any],
        top_k: int = 5,
        min_similarity: float = 0.7,
        client_id: Optional[str] = None
    ) -> List[Pattern]:
        """
        Find API flows similar to the given flow.
        
        Args:
            flow: API flow dictionary
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            client_id: Optional client ID filter
        
        Returns:
            List of similar API flow patterns
        """
        try:
            # Generate embedding for the flow
            embedding_result = self.embedding_generator.embed_api_flow(flow)
            
            # Search for similar patterns
            patterns = self.vector_store.search_similar_patterns(
                query_embedding=embedding_result.embedding,
                pattern_type='api_flow',
                top_k=top_k,
                min_success_rate=0.7,
                client_id=client_id
            )
            
            logger.info(
                f"Found {len(patterns)} similar API flows for: "
                f"{flow.get('description', 'Unnamed')}"
            )
            return patterns
        
        except Exception as e:
            logger.error(f"Failed to find similar API flows: {str(e)}")
            return []
    
    def find_similar_tests(
        self,
        test_case_id: int,
        top_k: int = 3,
        client_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find test cases similar to the given test case.
        
        Uses pre-computed similarity scores from similar_tests table.
        
        Args:
            test_case_id: ID of the test case
            top_k: Number of results to return
            client_id: Optional client ID filter
        
        Returns:
            List of similar test case information
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Query similar tests
                query = """
                    SELECT 
                        st.test_case_id_2 as similar_test_id,
                        st.similarity_score,
                        st.reason,
                        tc.name as test_name,
                        tc.description,
                        tc.test_type
                    FROM similar_tests st
                    JOIN test_cases tc ON st.test_case_id_2 = tc.id
                    WHERE st.test_case_id_1 = %s
                    ORDER BY st.similarity_score DESC
                    LIMIT %s
                """
                params = [test_case_id, top_k]
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                results = []
                for row in rows:
                    result = {
                        'test_case_id': row[0],
                        'similarity_score': row[1],
                        'reason': row[2],
                        'test_name': row[3],
                        'description': row[4],
                        'test_type': row[5]
                    }
                    results.append(result)
                
                logger.info(
                    f"Found {len(results)} similar tests for test case {test_case_id}"
                )
                return results
        
        except Exception as e:
            logger.error(f"Failed to find similar tests: {str(e)}")
            return []
        finally:
            self.system.return_connection(conn)
    
    def find_error_resolutions(
        self,
        error: str,
        context: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.7,
        client_id: Optional[str] = None
    ) -> List[Pattern]:
        """
        Find error resolution patterns similar to the given error.
        
        Args:
            error: Error message or error type
            context: Optional context about the error
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            client_id: Optional client ID filter
        
        Returns:
            List of error resolution patterns
        """
        try:
            # Generate embedding for the error
            embedding_result = self.embedding_generator.embed_error_resolution(
                error=error,
                resolution="",  # We're searching, not providing resolution
                context=context
            )
            
            # Search for similar patterns
            patterns = self.vector_store.search_similar_patterns(
                query_embedding=embedding_result.embedding,
                pattern_type='error_resolution',
                top_k=top_k,
                min_success_rate=0.8,  # High threshold for error resolutions
                client_id=client_id
            )
            
            logger.info(f"Found {len(patterns)} error resolutions for: {error}")
            return patterns
        
        except Exception as e:
            logger.error(f"Failed to find error resolutions: {str(e)}")
            return []
    
    def find_ui_component_patterns(
        self,
        component_type: str,
        interaction: str,
        context: Optional[str] = None,
        top_k: int = 5,
        client_id: Optional[str] = None
    ) -> List[Pattern]:
        """
        Find UI component interaction patterns.
        
        Args:
            component_type: Type of component (button, input, etc.)
            interaction: Type of interaction (click, type, etc.)
            context: Optional context
            top_k: Number of results to return
            client_id: Optional client ID filter
        
        Returns:
            List of UI component patterns
        """
        try:
            # Generate embedding for the component
            embedding_result = self.embedding_generator.embed_ui_component(
                component_type=component_type,
                interaction=interaction,
                context=context
            )
            
            # Search for similar patterns
            patterns = self.vector_store.search_similar_patterns(
                query_embedding=embedding_result.embedding,
                pattern_type='ui_component',
                top_k=top_k,
                min_success_rate=0.75,
                client_id=client_id
            )
            
            logger.info(
                f"Found {len(patterns)} UI component patterns for: "
                f"{component_type} → {interaction}"
            )
            return patterns
        
        except Exception as e:
            logger.error(f"Failed to find UI component patterns: {str(e)}")
            return []
    
    def calculate_test_similarity(
        self,
        test_case_id_1: int,
        test_case_id_2: int
    ) -> float:
        """
        Calculate similarity between two test cases based on their steps.
        
        Args:
            test_case_id_1: First test case ID
            test_case_id_2: Second test case ID
        
        Returns:
            Similarity score (0-1)
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Get steps for both test cases
                cur.execute("""
                    SELECT id, action, element_path, value, description
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order
                """, (test_case_id_1,))
                
                steps_1 = cur.fetchall()
                
                cur.execute("""
                    SELECT id, action, element_path, value, description
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order
                """, (test_case_id_2,))
                
                steps_2 = cur.fetchall()
                
                # Simple similarity: matching actions / total steps
                if not steps_1 or not steps_2:
                    return 0.0
                
                matching_actions = 0
                for step1 in steps_1:
                    for step2 in steps_2:
                        if step1[1] == step2[1]:  # action matches
                            matching_actions += 1
                            break
                
                max_steps = max(len(steps_1), len(steps_2))
                similarity = matching_actions / max_steps if max_steps > 0 else 0.0
                
                logger.debug(
                    f"Calculated test similarity: {test_case_id_1} vs {test_case_id_2} = {similarity:.2f}"
                )
                
                return similarity
        
        except Exception as e:
            logger.error(f"Failed to calculate test similarity: {str(e)}")
            return 0.0
        finally:
            self.system.return_connection(conn)
    
    def store_test_similarity(
        self,
        test_case_id_1: int,
        test_case_id_2: int,
        similarity_score: float,
        reason: Optional[str] = None
    ) -> bool:
        """
        Store pre-computed similarity between two test cases.
        
        Args:
            test_case_id_1: First test case ID
            test_case_id_2: Second test case ID
            similarity_score: Similarity score (0-1)
            reason: Optional reason for similarity
        
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Ensure consistent ordering (smaller ID first)
                id1 = min(test_case_id_1, test_case_id_2)
                id2 = max(test_case_id_1, test_case_id_2)
                
                cur.execute("""
                    INSERT INTO similar_tests (test_case_id_1, test_case_id_2, similarity_score, reason)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (test_case_id_1, test_case_id_2) DO UPDATE
                    SET similarity_score = %s, created_at = CURRENT_TIMESTAMP
                """, (id1, id2, similarity_score, reason, similarity_score))
                
                conn.commit()
                
                logger.debug(
                    f"Stored test similarity: {id1} vs {id2} = {similarity_score:.2f}"
                )
                
                return True
        
        except Exception as e:
            logger.error(f"Failed to store test similarity: {str(e)}")
            return False
        finally:
            self.system.return_connection(conn)
