"""
VectorStore Service

Manages storage and retrieval of patterns in the vector database.
Handles pattern storage, similarity search, success rate tracking, and pattern lifecycle.

Uses PostgreSQL with pgvector extension for vector similarity search.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import uuid

from auroqa.Utils.System import System

logger = logging.getLogger(__name__)


@dataclass
class Pattern:
    """Represents a stored pattern"""
    id: int
    pattern_type: str  # 'selector', 'api_flow', 'error_resolution', 'ui_component'
    pattern_data: Dict[str, Any]
    embedding: List[float]
    success_rate: float
    usage_count: int
    tags: List[str]
    created_at: datetime
    last_used: Optional[datetime]
    created_by: Optional[int]
    client_id: Optional[str]


class VectorStore:
    """
    Vector database store for patterns.
    
    Responsibilities:
    - Store patterns with embeddings
    - Search for similar patterns
    - Track pattern usage and success rates
    - Update pattern statistics
    - Retrieve patterns by type, tags, or similarity
    """
    
    def __init__(self):
        """Initialize vector store"""
        self.system = System()
        logger.info("VectorStore initialized")
    
    def store_pattern(
        self,
        pattern_type: str,
        pattern_data: Dict[str, Any],
        embedding: List[float],
        tags: Optional[List[str]] = None,
        created_by: Optional[int] = None,
        client_id: Optional[str] = None
    ) -> int:
        """
        Store a new pattern in the vector database.
        
        Args:
            pattern_type: Type of pattern ('selector', 'api_flow', 'error_resolution', 'ui_component')
            pattern_data: The actual pattern data (dict)
            embedding: Embedding vector from EmbeddingGenerator
            tags: Optional tags for categorization
            created_by: User ID who created the pattern
            client_id: Client ID for multi-tenancy
        
        Returns:
            Pattern ID
        
        Raises:
            Exception: If storage fails
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Convert embedding to PostgreSQL vector format
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                
                # Convert pattern_data to JSON
                pattern_json = json.dumps(pattern_data)
                
                # Convert tags to PostgreSQL array format
                tags_array = tags if tags else []
                
                cur.execute("""
                    INSERT INTO patterns (
                        pattern_type, pattern_data, embedding, 
                        tags, created_by, client_id, success_rate, usage_count
                    )
                    VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    pattern_type,
                    pattern_json,
                    embedding_str,
                    tags_array,
                    created_by,
                    client_id,
                    0.5,  # Initial success rate
                    0     # Initial usage count
                ))
                
                pattern_id = cur.fetchone()[0]
                conn.commit()
                
                logger.info(
                    f"Stored pattern {pattern_id} (type: {pattern_type}, "
                    f"tags: {tags}, client: {client_id})"
                )
                
                return pattern_id
        
        except Exception as e:
            logger.error(f"Failed to store pattern: {str(e)}")
            raise
        finally:
            self.system.return_connection(conn)
    
    def search_similar_patterns(
        self,
        query_embedding: List[float],
        pattern_type: Optional[str] = None,
        top_k: int = 5,
        min_success_rate: float = 0.0,
        client_id: Optional[str] = None
    ) -> List[Pattern]:
        """
        Search for patterns similar to the query embedding.
        
        Uses PostgreSQL pgvector cosine similarity search.
        
        Args:
            query_embedding: Query embedding vector
            pattern_type: Optional filter by pattern type
            top_k: Number of results to return
            min_success_rate: Minimum success rate filter (0-1)
            client_id: Optional client ID filter
        
        Returns:
            List of similar patterns, sorted by similarity (highest first)
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Build query
                embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
                
                query = """
                    SELECT 
                        id, pattern_type, pattern_data, embedding,
                        success_rate, usage_count, tags, created_at,
                        last_used, created_by, client_id,
                        embedding <=> %s::vector as distance
                    FROM patterns
                    WHERE success_rate >= %s
                """
                params = [embedding_str, min_success_rate]
                
                if pattern_type:
                    query += " AND pattern_type = %s"
                    params.append(pattern_type)
                
                if client_id:
                    query += " AND client_id = %s"
                    params.append(client_id)
                
                query += """
                    ORDER BY distance ASC
                    LIMIT %s
                """
                params.append(top_k)
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                patterns = []
                for row in rows:
                    pattern = Pattern(
                        id=row[0],
                        pattern_type=row[1],
                        pattern_data=json.loads(row[2]),
                        embedding=row[3],
                        success_rate=row[4],
                        usage_count=row[5],
                        tags=row[6] or [],
                        created_at=row[7],
                        last_used=row[8],
                        created_by=row[9],
                        client_id=row[10]
                    )
                    patterns.append(pattern)
                
                logger.debug(
                    f"Found {len(patterns)} similar patterns "
                    f"(type: {pattern_type}, min_success: {min_success_rate})"
                )
                
                return patterns
        
        except Exception as e:
            logger.error(f"Failed to search similar patterns: {str(e)}")
            return []
        finally:
            self.system.return_connection(conn)
    
    def get_patterns_by_type(
        self,
        pattern_type: str,
        min_success_rate: float = 0.7,
        client_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Pattern]:
        """
        Get all patterns of a specific type.
        
        Args:
            pattern_type: Type of patterns to retrieve
            min_success_rate: Minimum success rate filter
            client_id: Optional client ID filter
            limit: Maximum number of patterns to return
        
        Returns:
            List of patterns sorted by success rate (highest first)
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                query = """
                    SELECT 
                        id, pattern_type, pattern_data, embedding,
                        success_rate, usage_count, tags, created_at,
                        last_used, created_by, client_id
                    FROM patterns
                    WHERE pattern_type = %s AND success_rate >= %s
                """
                params = [pattern_type, min_success_rate]
                
                if client_id:
                    query += " AND client_id = %s"
                    params.append(client_id)
                
                query += """
                    ORDER BY success_rate DESC, usage_count DESC
                    LIMIT %s
                """
                params.append(limit)
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                patterns = []
                for row in rows:
                    pattern = Pattern(
                        id=row[0],
                        pattern_type=row[1],
                        pattern_data=json.loads(row[2]),
                        embedding=row[3],
                        success_rate=row[4],
                        usage_count=row[5],
                        tags=row[6] or [],
                        created_at=row[7],
                        last_used=row[8],
                        created_by=row[9],
                        client_id=row[10]
                    )
                    patterns.append(pattern)
                
                logger.debug(
                    f"Retrieved {len(patterns)} patterns of type {pattern_type} "
                    f"(min_success: {min_success_rate})"
                )
                
                return patterns
        
        except Exception as e:
            logger.error(f"Failed to get patterns by type: {str(e)}")
            return []
        finally:
            self.system.return_connection(conn)
    
    def record_pattern_usage(
        self,
        pattern_id: int,
        test_case_id: int,
        step_number: int,
        success: bool,
        execution_time_ms: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> int:
        """
        Record usage of a pattern.
        
        Args:
            pattern_id: ID of the pattern used
            test_case_id: ID of the test case using the pattern
            step_number: Step number in the test case
            success: Whether the pattern execution succeeded
            execution_time_ms: Optional execution time in milliseconds
            error_message: Optional error message if failed
        
        Returns:
            Usage record ID
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Record usage
                cur.execute("""
                    INSERT INTO pattern_usage (
                        pattern_id, test_case_id, step_number,
                        success, execution_time_ms, error_message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    pattern_id, test_case_id, step_number,
                    success, execution_time_ms, error_message
                ))
                
                usage_id = cur.fetchone()[0]
                
                # Update pattern statistics
                self._update_pattern_success_rate(pattern_id, success, conn)
                
                conn.commit()
                
                logger.debug(
                    f"Recorded pattern usage {usage_id} "
                    f"(pattern: {pattern_id}, test: {test_case_id}, success: {success})"
                )
                
                return usage_id
        
        except Exception as e:
            logger.error(f"Failed to record pattern usage: {str(e)}")
            raise
        finally:
            self.system.return_connection(conn)
    
    def _update_pattern_success_rate(self, pattern_id: int, success: bool, conn=None) -> None:
        """
        Update pattern success rate based on usage.
        
        Uses exponential moving average to weight recent usage more heavily.
        
        Args:
            pattern_id: ID of the pattern
            success: Whether the usage was successful
            conn: Optional database connection to reuse
        """
        should_close = False
        if conn is None:
            conn = self.system.get_db_connection()
            should_close = True
        
        try:
            with conn.cursor() as cur:
                # Get current stats
                cur.execute("""
                    SELECT success_rate, usage_count FROM patterns WHERE id = %s
                """, (pattern_id,))
                
                row = cur.fetchone()
                if not row:
                    logger.warning(f"Pattern {pattern_id} not found")
                    return
                
                current_rate, usage_count = row
                new_usage_count = usage_count + 1
                
                # Exponential moving average: new_rate = 0.7 * old_rate + 0.3 * new_success
                new_success_value = 1.0 if success else 0.0
                new_rate = 0.7 * current_rate + 0.3 * new_success_value
                
                # Update pattern
                cur.execute("""
                    UPDATE patterns
                    SET success_rate = %s, usage_count = %s, last_used = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_rate, new_usage_count, pattern_id))
                
                logger.debug(
                    f"Updated pattern {pattern_id} success rate: "
                    f"{current_rate:.2f} → {new_rate:.2f} (usage: {new_usage_count})"
                )
        
        except Exception as e:
            logger.error(f"Failed to update pattern success rate: {str(e)}")
        
        finally:
            if should_close:
                self.system.return_connection(conn)
    
    def get_pattern_by_id(self, pattern_id: int) -> Optional[Pattern]:
        """
        Retrieve a pattern by ID.
        
        Args:
            pattern_id: ID of the pattern
        
        Returns:
            Pattern object or None if not found
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id, pattern_type, pattern_data, embedding,
                        success_rate, usage_count, tags, created_at,
                        last_used, created_by, client_id
                    FROM patterns
                    WHERE id = %s
                """, (pattern_id,))
                
                row = cur.fetchone()
                if not row:
                    return None
                
                pattern = Pattern(
                    id=row[0],
                    pattern_type=row[1],
                    pattern_data=json.loads(row[2]),
                    embedding=row[3],
                    success_rate=row[4],
                    usage_count=row[5],
                    tags=row[6] or [],
                    created_at=row[7],
                    last_used=row[8],
                    created_by=row[9],
                    client_id=row[10]
                )
                
                return pattern
        
        except Exception as e:
            logger.error(f"Failed to get pattern {pattern_id}: {str(e)}")
            return None
        finally:
            self.system.return_connection(conn)
    
    def delete_pattern(self, pattern_id: int) -> bool:
        """
        Delete a pattern and its usage records.
        
        Args:
            pattern_id: ID of the pattern to delete
        
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self.system.get_db_connection()
            
            with conn.cursor() as cur:
                # Delete usage records first (cascade)
                cur.execute("DELETE FROM pattern_usage WHERE pattern_id = %s", (pattern_id,))
                
                # Delete pattern
                cur.execute("DELETE FROM patterns WHERE id = %s", (pattern_id,))
                
                conn.commit()
                
                logger.info(f"Deleted pattern {pattern_id}")
                return True
        
        except Exception as e:
            logger.error(f"Failed to delete pattern {pattern_id}: {str(e)}")
            return False
        finally:
            self.system.return_connection(conn)
