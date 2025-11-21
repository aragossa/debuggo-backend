"""
Performance Optimizer Service
Handles caching, batch processing, query optimization, and async operations
"""

import hashlib
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)


class PerformanceOptimizer:
    """Optimizes system performance through caching, batching, and optimization"""

    def __init__(self):
        """Initialize Performance Optimizer"""
        self.cache_ttl = 3600  # 1 hour default TTL
        self.batch_size = 32
        self.max_workers = 4

    # ==================== Embedding Cache ====================

    def cache_embedding(self, content_hash: str, embedding: List[float], 
                       metadata: Optional[Dict] = None) -> bool:
        """
        Cache an embedding in the database
        
        Args:
            content_hash: Hash of the content
            embedding: Vector embedding
            metadata: Optional metadata about the embedding
            
        Returns:
            True if cached successfully
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    embedding_json = json.dumps(embedding)
                    metadata_json = json.dumps(metadata or {})
                    
                    cur.execute("""
                        INSERT INTO embedding_cache 
                        (content_hash, embedding, metadata, access_count, last_accessed)
                        VALUES (%s, %s, %s, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT (content_hash) 
                        DO UPDATE SET 
                            access_count = access_count + 1,
                            last_accessed = CURRENT_TIMESTAMP
                    """, (content_hash, embedding_json, metadata_json))
                    
                    conn.commit()
                    logger.info(f"Cached embedding for hash: {content_hash}")
                    return True
        except Exception as e:
            logger.error(f"Error caching embedding: {e}")
            return False

    def get_cached_embedding(self, content_hash: str) -> Optional[List[float]]:
        """
        Retrieve a cached embedding
        
        Args:
            content_hash: Hash of the content
            
        Returns:
            Embedding vector or None if not found/expired
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT embedding, last_accessed
                        FROM embedding_cache
                        WHERE content_hash = %s
                    """, (content_hash,))
                    
                    result = cur.fetchone()
                    if not result:
                        return None
                    
                    embedding_json, last_accessed = result
                    
                    # Check if expired
                    if datetime.now() - last_accessed > timedelta(seconds=self.cache_ttl):
                        self.invalidate_embedding_cache(content_hash)
                        return None
                    
                    # Update access count
                    cur.execute("""
                        UPDATE embedding_cache
                        SET access_count = access_count + 1,
                            last_accessed = CURRENT_TIMESTAMP
                        WHERE content_hash = %s
                    """, (content_hash,))
                    conn.commit()
                    
                    return json.loads(embedding_json)
        except Exception as e:
            logger.error(f"Error retrieving cached embedding: {e}")
            return None

    def invalidate_embedding_cache(self, content_hash: str) -> bool:
        """
        Invalidate a cached embedding
        
        Args:
            content_hash: Hash of the content
            
        Returns:
            True if invalidated successfully
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM embedding_cache
                        WHERE content_hash = %s
                    """, (content_hash,))
                    conn.commit()
                    logger.info(f"Invalidated embedding cache for hash: {content_hash}")
                    return True
        except Exception as e:
            logger.error(f"Error invalidating embedding cache: {e}")
            return False

    def clear_expired_embeddings(self) -> int:
        """
        Clear expired embeddings from cache
        
        Returns:
            Number of embeddings cleared
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM embedding_cache
                        WHERE CURRENT_TIMESTAMP - last_accessed > INTERVAL '1 hour'
                    """)
                    count = cur.rowcount
                    conn.commit()
                    logger.info(f"Cleared {count} expired embeddings")
                    return count
        except Exception as e:
            logger.error(f"Error clearing expired embeddings: {e}")
            return 0

    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get embedding cache statistics
        
        Returns:
            Dictionary with cache stats
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_embeddings,
                            AVG(hit_count) as avg_accesses,
                            MAX(hit_count) as max_accesses,
                            SUM(CASE WHEN hit_count > 1 THEN 1 ELSE 0 END) as reused_count
                        FROM embedding_cache
                    """)
                    
                    result = cur.fetchone()
                    total, avg_access, max_access, reused = result
                    
                    hit_rate = (reused / total * 100) if total > 0 else 0
                    
                    return {
                        'total_embeddings': total or 0,
                        'avg_accesses': float(avg_access or 0),
                        'max_accesses': max_access or 0,
                        'reused_count': reused or 0,
                        'hit_rate_percent': round(hit_rate, 2)
                    }
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {}

    # ==================== Batch Processing ====================

    def batch_process(self, items: List[Any], processor_func, 
                     batch_size: Optional[int] = None) -> List[Any]:
        """
        Process items in batches
        
        Args:
            items: List of items to process
            processor_func: Function to process each batch
            batch_size: Size of each batch (default: self.batch_size)
            
        Returns:
            List of processed results
        """
        batch_size = batch_size or self.batch_size
        results = []
        
        try:
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                logger.info(f"Processing batch {i // batch_size + 1} of {(len(items) + batch_size - 1) // batch_size}")
                
                batch_result = processor_func(batch)
                results.extend(batch_result if isinstance(batch_result, list) else [batch_result])
                
                # Small delay between batches
                time.sleep(0.1)
            
            logger.info(f"Batch processing complete: {len(results)} items processed")
            return results
        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            return results

    def parallel_process(self, items: List[Any], processor_func,
                        max_workers: Optional[int] = None) -> List[Any]:
        """
        Process items in parallel
        
        Args:
            items: List of items to process
            processor_func: Function to process each item
            max_workers: Maximum number of worker threads
            
        Returns:
            List of processed results
        """
        max_workers = max_workers or self.max_workers
        results = []
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(processor_func, item): item for item in items}
                
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Error processing item: {e}")
            
            logger.info(f"Parallel processing complete: {len(results)} items processed")
            return results
        except Exception as e:
            logger.error(f"Error in parallel processing: {e}")
            return results

    # ==================== Query Optimization ====================

    def log_query_performance(self, query: str, duration_ms: float,
                             operation: str, success: bool = True) -> bool:
        """
        Log query performance metrics
        
        Args:
            query: SQL query executed
            duration_ms: Duration in milliseconds
            operation: Operation name
            success: Whether query succeeded
            
        Returns:
            True if logged successfully
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO performance_logs
                        (operation, query, duration_ms, success, created_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (operation, query, duration_ms, success))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Error logging query performance: {e}")
            return False

    def get_slow_queries(self, threshold_ms: float = 1000, limit: int = 50) -> List[Dict]:
        """
        Get slow queries from performance logs
        
        Args:
            threshold_ms: Threshold for slow queries
            limit: Maximum number of results
            
        Returns:
            List of slow queries
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            query_type,
                            AVG(execution_time_ms) as avg_duration,
                            MAX(execution_time_ms) as max_duration,
                            COUNT(*) as execution_count,
                            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count
                        FROM performance_logs
                        WHERE execution_time_ms > %s
                        GROUP BY query_type
                        ORDER BY avg_duration DESC
                        LIMIT %s
                    """, (threshold_ms, limit))
                    
                    results = []
                    for row in cur.fetchall():
                        results.append({
                            'operation': row[0],
                            'avg_duration_ms': float(row[1]),
                            'max_duration_ms': float(row[2]),
                            'execution_count': row[3],
                            'success_count': row[4]
                        })
                    
                    return results
        except Exception as e:
            logger.error(f"Error getting slow queries: {e}")
            return []

    def get_performance_metrics(self, operation: Optional[str] = None,
                               hours: int = 24) -> Dict[str, Any]:
        """
        Get performance metrics for operations
        
        Args:
            operation: Specific operation to analyze (None for all)
            hours: Number of hours to look back
            
        Returns:
            Dictionary with performance metrics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    if operation:
                        cur.execute("""
                            SELECT 
                                AVG(duration_ms) as avg_duration,
                                MIN(duration_ms) as min_duration,
                                MAX(duration_ms) as max_duration,
                                STDDEV(duration_ms) as stddev_duration,
                                COUNT(*) as total_queries,
                                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_queries
                            FROM performance_logs
                            WHERE operation = %s
                            AND created_at > CURRENT_TIMESTAMP - INTERVAL '%s hours'
                        """, (operation, hours))
                    else:
                        cur.execute("""
                            SELECT 
                                AVG(duration_ms) as avg_duration,
                                MIN(duration_ms) as min_duration,
                                MAX(duration_ms) as max_duration,
                                STDDEV(duration_ms) as stddev_duration,
                                COUNT(*) as total_queries,
                                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_queries
                            FROM performance_logs
                            WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '%s hours'
                        """, (hours,))
                    
                    result = cur.fetchone()
                    if result:
                        avg, min_d, max_d, stddev, total, successful = result
                        success_rate = (successful / total * 100) if total > 0 else 0
                        
                        return {
                            'avg_duration_ms': float(avg or 0),
                            'min_duration_ms': float(min_d or 0),
                            'max_duration_ms': float(max_d or 0),
                            'stddev_duration_ms': float(stddev or 0),
                            'total_queries': total or 0,
                            'successful_queries': successful or 0,
                            'success_rate_percent': round(success_rate, 2)
                        }
                    return {}
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}

    # ==================== Lazy Loading ====================

    def lazy_load_data(self, query: str, params: Tuple = (),
                      chunk_size: int = 100):
        """
        Lazy load data from database in chunks
        
        Args:
            query: SQL query
            params: Query parameters
            chunk_size: Size of each chunk
            
        Yields:
            Chunks of data
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    
                    while True:
                        rows = cur.fetchmany(chunk_size)
                        if not rows:
                            break
                        yield rows
        except Exception as e:
            logger.error(f"Error in lazy loading: {e}")

    # ==================== Async Operations ====================

    async def async_batch_process(self, items: List[Any], 
                                 async_processor_func) -> List[Any]:
        """
        Process items asynchronously in batches
        
        Args:
            items: List of items to process
            async_processor_func: Async function to process each item
            
        Returns:
            List of processed results
        """
        try:
            tasks = [async_processor_func(item) for item in items]
            results = await asyncio.gather(*tasks)
            logger.info(f"Async batch processing complete: {len(results)} items processed")
            return results
        except Exception as e:
            logger.error(f"Error in async batch processing: {e}")
            return []

    # ==================== Index Optimization ====================

    def analyze_index_usage(self) -> Dict[str, Any]:
        """
        Analyze database index usage
        
        Returns:
            Dictionary with index statistics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            schemaname,
                            relname,
                            indexrelname,
                            idx_scan as index_scans,
                            idx_tup_read as tuples_read,
                            idx_tup_fetch as tuples_fetched
                        FROM pg_stat_user_indexes
                        ORDER BY idx_scan DESC
                        LIMIT 20
                    """)
                    
                    results = []
                    for row in cur.fetchall():
                        results.append({
                            'schema': row[0],
                            'table': row[1],
                            'index': row[2],
                            'scans': row[3],
                            'tuples_read': row[4],
                            'tuples_fetched': row[5]
                        })
                    
                    return {'indexes': results}
        except Exception as e:
            logger.error(f"Error analyzing index usage: {e}")
            return {}

    def get_unused_indexes(self) -> List[Dict]:
        """
        Get unused indexes that could be dropped
        
        Returns:
            List of unused indexes
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            schemaname,
                            relname,
                            indexrelname,
                            idx_scan
                        FROM pg_stat_user_indexes
                        WHERE idx_scan = 0
                        AND indexrelname NOT LIKE 'pg_toast%'
                        ORDER BY pg_relation_size(indexrelid) DESC
                    """)
                    
                    results = []
                    for row in cur.fetchall():
                        results.append({
                            'schema': row[0],
                            'table': row[1],
                            'index': row[2],
                            'scans': row[3]
                        })
                    
                    return results
        except Exception as e:
            logger.error(f"Error getting unused indexes: {e}")
            return []

    # ==================== Connection Pooling ====================

    def get_pool_status(self) -> Dict[str, Any]:
        """
        Get database connection pool status
        
        Returns:
            Dictionary with pool statistics
        """
        try:
            pool = System.db_pool
            return {
                'min_connections': pool.minconn,
                'max_connections': pool.maxconn,
                'available_connections': pool.closed,
                'total_connections': pool.maxconn
            }
        except Exception as e:
            logger.error(f"Error getting pool status: {e}")
            return {}

    # ==================== Optimization Recommendations ====================

    def generate_optimization_recommendations(self) -> List[Dict]:
        """
        Generate performance optimization recommendations
        
        Returns:
            List of recommendations
        """
        recommendations = []
        
        try:
            # Check cache hit rate
            cache_stats = self.get_cache_statistics()
            if cache_stats.get('hit_rate_percent', 0) < 50:
                recommendations.append({
                    'type': 'cache',
                    'priority': 'high',
                    'description': 'Low embedding cache hit rate',
                    'action': 'Increase cache TTL or review caching strategy',
                    'current_value': f"{cache_stats.get('hit_rate_percent', 0):.1f}%",
                    'target_value': '70%'
                })
            
            # Check slow queries
            slow_queries = self.get_slow_queries(threshold_ms=2000)
            if slow_queries:
                recommendations.append({
                    'type': 'query',
                    'priority': 'high',
                    'description': f'{len(slow_queries)} slow queries detected',
                    'action': 'Optimize slow queries or add indexes',
                    'current_value': f"{slow_queries[0]['avg_duration_ms']:.0f}ms",
                    'target_value': '<1000ms'
                })
            
            # Check unused indexes
            unused = self.get_unused_indexes()
            if unused:
                recommendations.append({
                    'type': 'index',
                    'priority': 'medium',
                    'description': f'{len(unused)} unused indexes found',
                    'action': 'Consider dropping unused indexes',
                    'current_value': f'{len(unused)} indexes',
                    'target_value': '0 unused indexes'
                })
            
            return recommendations
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return []
