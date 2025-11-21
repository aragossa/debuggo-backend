import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)


class ABTestResultTracker:
    """Service for tracking A/B test results and calculating winners"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def link_test_run_to_ab_test(self, test_run_id: int, ab_test_id: int, variant: str) -> bool:
        """
        Link a test run to an A/B test and mark which variant it belongs to.
        
        Args:
            test_run_id: ID of the test run
            ab_test_id: ID of the A/B test
            variant: 'A' or 'B' to indicate which variant was executed
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE test_runs 
                        SET ab_test_id = %s, ab_variant = %s
                        WHERE id = %s
                    """, (ab_test_id, variant, test_run_id))
                    
                    conn.commit()
                    self.logger.info(f"Linked test run {test_run_id} to A/B test {ab_test_id} (variant {variant})")
                    return True
        except Exception as e:
            self.logger.error(f"Error linking test run to A/B test: {e}")
            return False
    
    def batch_link_test_runs(self, ab_test_id: int, variant_a_run_ids: List[int], variant_b_run_ids: List[int]) -> Dict[str, Any]:
        """
        Link multiple test runs to an A/B test in batch.
        
        Args:
            ab_test_id: ID of the A/B test
            variant_a_run_ids: List of test run IDs for variant A
            variant_b_run_ids: List of test run IDs for variant B
            
        Returns:
            Dictionary with success count and any errors
        """
        results = {
            'total_linked': 0,
            'variant_a_linked': 0,
            'variant_b_linked': 0,
            'errors': []
        }
        
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Link variant A runs
                    for test_run_id in variant_a_run_ids:
                        try:
                            cur.execute("""
                                UPDATE test_runs 
                                SET ab_test_id = %s, ab_variant = 'A'
                                WHERE id = %s
                            """, (ab_test_id, test_run_id))
                            results['variant_a_linked'] += 1
                            results['total_linked'] += 1
                        except Exception as e:
                            results['errors'].append(f"Failed to link variant A run {test_run_id}: {str(e)}")
                    
                    # Link variant B runs
                    for test_run_id in variant_b_run_ids:
                        try:
                            cur.execute("""
                                UPDATE test_runs 
                                SET ab_test_id = %s, ab_variant = 'B'
                                WHERE id = %s
                            """, (ab_test_id, test_run_id))
                            results['variant_b_linked'] += 1
                            results['total_linked'] += 1
                        except Exception as e:
                            results['errors'].append(f"Failed to link variant B run {test_run_id}: {str(e)}")
                    
                    conn.commit()
                    self.logger.info(f"Batch linked {results['total_linked']} test runs to A/B test {ab_test_id}")
            
            return results
        except Exception as e:
            self.logger.error(f"Error batch linking test runs: {e}")
            results['errors'].append(f"Batch linking failed: {str(e)}")
            return results
    
    def calculate_ab_test_results(self, ab_test_id: int) -> Dict[str, Any]:
        """
        Calculate A/B test results based on linked test runs.
        
        Args:
            ab_test_id: ID of the A/B test
            
        Returns:
            Dictionary with success rates, winner, and confidence level
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get A/B test details
                    cur.execute("""
                        SELECT id, test_case_id_a, test_case_id_b, 
                               variant_a_id, variant_b_id, sample_size_a, sample_size_b
                        FROM ab_test_results
                        WHERE id = %s
                    """, (ab_test_id,))
                    
                    ab_test = cur.fetchone()
                    if not ab_test:
                        self.logger.error(f"A/B test {ab_test_id} not found")
                        return {}
                    
                    # Get variant A results
                    cur.execute("""
                        SELECT COUNT(*) as total,
                               SUM(CASE WHEN result = 'completed' THEN 1 ELSE 0 END) as passed
                        FROM test_runs
                        WHERE ab_test_id = %s AND ab_variant = 'A'
                    """, (ab_test_id,))
                    
                    variant_a_row = cur.fetchone()
                    variant_a_total = variant_a_row[0] or 0
                    variant_a_passed = variant_a_row[1] or 0
                    variant_a_success_rate = (variant_a_passed / variant_a_total * 100) if variant_a_total > 0 else 0
                    
                    # Get variant B results
                    cur.execute("""
                        SELECT COUNT(*) as total,
                               SUM(CASE WHEN result = 'completed' THEN 1 ELSE 0 END) as passed
                        FROM test_runs
                        WHERE ab_test_id = %s AND ab_variant = 'B'
                    """, (ab_test_id,))
                    
                    variant_b_row = cur.fetchone()
                    variant_b_total = variant_b_row[0] or 0
                    variant_b_passed = variant_b_row[1] or 0
                    variant_b_success_rate = (variant_b_passed / variant_b_total * 100) if variant_b_total > 0 else 0
                    
                    # Determine winner
                    winner = None
                    confidence_level = 0
                    
                    if variant_a_total > 0 and variant_b_total > 0:
                        if variant_a_success_rate > variant_b_success_rate:
                            winner = 'A'
                            # Simple confidence calculation based on difference
                            confidence_level = min(100, abs(variant_a_success_rate - variant_b_success_rate) * 2)
                        elif variant_b_success_rate > variant_a_success_rate:
                            winner = 'B'
                            confidence_level = min(100, abs(variant_b_success_rate - variant_a_success_rate) * 2)
                        else:
                            winner = 'TIE'
                            confidence_level = 0
                    
                    # Determine if test is complete
                    status = 'active'
                    sample_size_a = ab_test[5] or 0
                    sample_size_b = ab_test[6] or 0
                    if sample_size_a > 0 and sample_size_b > 0:
                        if variant_a_total >= sample_size_a and variant_b_total >= sample_size_b:
                            status = 'completed'
                    
                    return {
                        'ab_test_id': ab_test_id,
                        'variant_a_id': ab_test[3],
                        'variant_b_id': ab_test[4],
                        'variant_a_success_rate': round(variant_a_success_rate, 2),
                        'variant_b_success_rate': round(variant_b_success_rate, 2),
                        'variant_a_runs': variant_a_total,
                        'variant_b_runs': variant_b_total,
                        'winner': winner,
                        'confidence_level': round(confidence_level, 2),
                        'status': status
                    }
        except Exception as e:
            self.logger.error(f"Error calculating A/B test results: {e}")
            return {}
    
    def update_ab_test_results(self, ab_test_id: int) -> bool:
        """
        Update A/B test record with calculated results.
        
        Args:
            ab_test_id: ID of the A/B test
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            results = self.calculate_ab_test_results(ab_test_id)
            
            if not results:
                return False
            
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE ab_test_results
                        SET variant_a_success_rate = %s,
                            variant_b_success_rate = %s,
                            winner = %s,
                            confidence_level = %s,
                            status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (
                        results['variant_a_success_rate'],
                        results['variant_b_success_rate'],
                        results['winner'],
                        results['confidence_level'],
                        results['status'],
                        ab_test_id
                    ))
                    
                    conn.commit()
                    self.logger.info(f"Updated A/B test {ab_test_id} results: winner={results['winner']}, confidence={results['confidence_level']}")
                    return True
        except Exception as e:
            self.logger.error(f"Error updating A/B test results: {e}")
            return False
    
    def get_ab_test_status(self, ab_test_id: int) -> Dict[str, Any]:
        """
        Get current status of an A/B test including progress and results.
        
        Args:
            ab_test_id: ID of the A/B test
            
        Returns:
            Dictionary with A/B test status and results
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get A/B test details
                    cur.execute("""
                        SELECT id, test_case_id_a, test_case_id_b, 
                               variant_a_id, variant_b_id, sample_size_a, sample_size_b,
                               status, created_at
                        FROM ab_test_results
                        WHERE id = %s
                    """, (ab_test_id,))
                    
                    ab_test = cur.fetchone()
                    if not ab_test:
                        return {}
                    
                    # Calculate current results
                    results = self.calculate_ab_test_results(ab_test_id)
                    
                    return {
                        'ab_test_id': ab_test[0],
                        'test_case_id_a': ab_test[1],
                        'test_case_id_b': ab_test[2],
                        'variant_a_id': ab_test[3],
                        'variant_b_id': ab_test[4],
                        'sample_size_a': ab_test[5],
                        'sample_size_b': ab_test[6],
                        'status': ab_test[7],
                        'created_at': ab_test[8].isoformat() if ab_test[8] else None,
                        'results': results
                    }
        except Exception as e:
            self.logger.error(f"Error getting A/B test status: {e}")
            return {}
    
    def get_all_ab_tests_with_progress(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get all A/B tests with their current progress and results.
        
        Args:
            limit: Maximum number of tests to return
            
        Returns:
            List of A/B tests with progress information
        """
        try:
            ab_tests = []
            
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get all A/B tests
                    cur.execute("""
                        SELECT id, test_case_id_a, test_case_id_b,
                               variant_a_id, variant_b_id, sample_size_a, sample_size_b,
                               status, created_at
                        FROM ab_test_results
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (limit,))
                    
                    for row in cur.fetchall():
                        ab_test_id = row[0]
                        results = self.calculate_ab_test_results(ab_test_id)
                        
                        ab_tests.append({
                            'ab_test_id': ab_test_id,
                            'test_case_id_a': row[1],
                            'test_case_id_b': row[2],
                            'variant_a_id': row[3],
                            'variant_b_id': row[4],
                            'sample_size_a': row[5],
                            'sample_size_b': row[6],
                            'status': row[7],
                            'created_at': row[8].isoformat() if row[8] else None,
                            'results': results
                        })
            
            return ab_tests
        except Exception as e:
            self.logger.error(f"Error getting A/B tests with progress: {e}")
            return []
    
    def get_available_test_runs(self, test_case_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get available test runs for a test case that haven't been linked to an A/B test.
        
        Args:
            test_case_id: ID of the test case
            limit: Maximum number of runs to return
            
        Returns:
            List of available test runs
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, test_case_id, result, run_date, duration
                        FROM test_runs
                        WHERE test_case_id = %s AND ab_test_id IS NULL
                        ORDER BY run_date DESC
                        LIMIT %s
                    """, (test_case_id, limit))
                    
                    runs = []
                    for row in cur.fetchall():
                        runs.append({
                            'test_run_id': row[0],
                            'test_case_id': row[1],
                            'result': row[2],
                            'created_at': row[3].isoformat() if row[3] else None,
                            'execution_time_seconds': row[4]
                        })
                    
                    return runs
        except Exception as e:
            self.logger.error(f"Error getting available test runs: {e}")
            return []
