"""
MetricsService: Collects and analyzes test execution metrics

Features:
- Test execution metrics (pass rate, duration, etc.)
- Suite performance metrics
- Plan execution statistics
- Trend analysis
- Performance benchmarking
- Failure analysis
"""

import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class MetricsService:
    """Manages test execution metrics and analytics"""
    
    def __init__(self):
        """Initialize MetricsService"""
        self.logger = logging.getLogger(__name__)
        self.system = System()
    
    # ========================================================================
    # Execution Statistics
    # ========================================================================
    
    def get_plan_execution_stats(self, plan_id: int) -> Optional[Dict]:
        """
        Get execution statistics for a plan
        
        Args:
            plan_id: ID of the plan
            
        Returns:
            Execution statistics or None
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total_runs,
                               SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                               AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
                               MIN(EXTRACT(EPOCH FROM (completed_at - started_at))) as min_duration_seconds,
                               MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) as max_duration_seconds,
                               SUM(total_tests) as total_tests,
                               SUM(passed_tests) as total_passed_tests,
                               SUM(failed_tests) as total_failed_tests
                        FROM execution_suite_plan_runs
                        WHERE execution_suite_plan_id = %s
                        """,
                        (plan_id,)
                    )
                    
                    result = cursor.fetchone()
                    if not result or result[0] == 0:
                        return None
                    
                    total_runs = result[0]
                    passed_runs = result[1] or 0
                    failed_runs = result[2] or 0
                    
                    return {
                        'plan_id': plan_id,
                        'total_runs': total_runs,
                        'passed_runs': passed_runs,
                        'failed_runs': failed_runs,
                        'pass_rate': (passed_runs / total_runs * 100) if total_runs > 0 else 0,
                        'avg_duration_seconds': float(result[3]) if result[3] else 0,
                        'min_duration_seconds': float(result[4]) if result[4] else 0,
                        'max_duration_seconds': float(result[5]) if result[5] else 0,
                        'total_tests': result[6] or 0,
                        'total_passed_tests': result[7] or 0,
                        'total_failed_tests': result[8] or 0,
                        'overall_pass_rate': (result[7] / result[6] * 100) if result[6] and result[6] > 0 else 0
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting plan execution stats: {e}")
            return None
    
    def get_suite_execution_stats(self, suite_id: int) -> Optional[Dict]:
        """
        Get execution statistics for a suite
        
        Args:
            suite_id: ID of the suite
            
        Returns:
            Execution statistics or None
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total_runs,
                               SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                               AVG(duration_seconds) as avg_duration_seconds,
                               MIN(duration_seconds) as min_duration_seconds,
                               MAX(duration_seconds) as max_duration_seconds,
                               SUM(total_tests) as total_tests,
                               SUM(passed_tests) as total_passed_tests,
                               SUM(failed_tests) as total_failed_tests
                        FROM execution_suite_plan_suite_runs
                        WHERE test_suite_id = %s
                        """,
                        (suite_id,)
                    )
                    
                    result = cursor.fetchone()
                    if not result or result[0] == 0:
                        return None
                    
                    total_runs = result[0]
                    passed_runs = result[1] or 0
                    failed_runs = result[2] or 0
                    
                    return {
                        'suite_id': suite_id,
                        'total_runs': total_runs,
                        'passed_runs': passed_runs,
                        'failed_runs': failed_runs,
                        'pass_rate': (passed_runs / total_runs * 100) if total_runs > 0 else 0,
                        'avg_duration_seconds': float(result[3]) if result[3] else 0,
                        'min_duration_seconds': float(result[4]) if result[4] else 0,
                        'max_duration_seconds': float(result[5]) if result[5] else 0,
                        'total_tests': result[6] or 0,
                        'total_passed_tests': result[7] or 0,
                        'total_failed_tests': result[8] or 0,
                        'overall_pass_rate': (result[7] / result[6] * 100) if result[6] and result[6] > 0 else 0
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting suite execution stats: {e}")
            return None
    
    # ========================================================================
    # Trend Analysis
    # ========================================================================
    
    def get_execution_trend(
        self,
        plan_id: int,
        days: int = 30
    ) -> List[Dict]:
        """
        Get execution trend over time
        
        Args:
            plan_id: ID of the plan
            days: Number of days to analyze
            
        Returns:
            List of daily trend data
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DATE(started_at) as execution_date,
                               COUNT(*) as total_runs,
                               SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                               AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
                               SUM(total_tests) as total_tests,
                               SUM(passed_tests) as total_passed_tests,
                               SUM(failed_tests) as total_failed_tests
                        FROM execution_suite_plan_runs
                        WHERE execution_suite_plan_id = %s
                        AND started_at >= NOW() - INTERVAL '%s days'
                        GROUP BY DATE(started_at)
                        ORDER BY execution_date DESC
                        """,
                        (plan_id, days)
                    )
                    
                    trend = []
                    for row in cursor.fetchall():
                        total_runs = row[1]
                        passed_runs = row[2] or 0
                        failed_runs = row[3] or 0
                        total_tests = row[5] or 0
                        passed_tests = row[6] or 0
                        
                        trend.append({
                            'date': str(row[0]),
                            'total_runs': total_runs,
                            'passed_runs': passed_runs,
                            'failed_runs': failed_runs,
                            'pass_rate': (passed_runs / total_runs * 100) if total_runs > 0 else 0,
                            'avg_duration_seconds': float(row[4]) if row[4] else 0,
                            'total_tests': total_tests,
                            'total_passed_tests': passed_tests,
                            'total_failed_tests': row[7] or 0,
                            'test_pass_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0
                        })
                    
                    return trend
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting execution trend: {e}")
            return []
    
    # ========================================================================
    # Performance Analysis
    # ========================================================================
    
    def get_slowest_suites(
        self,
        plan_id: int,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get slowest performing suites
        
        Args:
            plan_id: ID of the plan
            limit: Number of suites to return
            
        Returns:
            List of slowest suites
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT test_suite_id,
                               COUNT(*) as total_runs,
                               AVG(duration_seconds) as avg_duration_seconds,
                               MAX(duration_seconds) as max_duration_seconds,
                               SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs
                        FROM execution_suite_plan_suite_runs
                        WHERE execution_suite_plan_run_id IN (
                            SELECT id FROM execution_suite_plan_runs
                            WHERE execution_suite_plan_id = %s
                        )
                        GROUP BY test_suite_id
                        ORDER BY avg_duration_seconds DESC
                        LIMIT %s
                        """,
                        (plan_id, limit)
                    )
                    
                    slowest = []
                    for row in cursor.fetchall():
                        total_runs = row[1]
                        passed_runs = row[4] or 0
                        
                        slowest.append({
                            'suite_id': row[0],
                            'total_runs': total_runs,
                            'avg_duration_seconds': float(row[2]) if row[2] else 0,
                            'max_duration_seconds': float(row[3]) if row[3] else 0,
                            'passed_runs': passed_runs,
                            'failed_runs': row[5] or 0,
                            'pass_rate': (passed_runs / total_runs * 100) if total_runs > 0 else 0
                        })
                    
                    return slowest
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting slowest suites: {e}")
            return []
    
    def get_most_flaky_suites(
        self,
        plan_id: int,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get most flaky (inconsistent) suites
        
        Args:
            plan_id: ID of the plan
            limit: Number of suites to return
            
        Returns:
            List of flakiest suites
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT test_suite_id,
                               COUNT(*) as total_runs,
                               SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                               STDDEV(duration_seconds) as duration_stddev,
                               AVG(duration_seconds) as avg_duration_seconds
                        FROM execution_suite_plan_suite_runs
                        WHERE execution_suite_plan_run_id IN (
                            SELECT id FROM execution_suite_plan_runs
                            WHERE execution_suite_plan_id = %s
                        )
                        GROUP BY test_suite_id
                        HAVING COUNT(*) >= 5
                        ORDER BY STDDEV(duration_seconds) DESC NULLS LAST
                        LIMIT %s
                        """,
                        (plan_id, limit)
                    )
                    
                    flaky = []
                    for row in cursor.fetchall():
                        total_runs = row[1]
                        passed_runs = row[2] or 0
                        
                        flaky.append({
                            'suite_id': row[0],
                            'total_runs': total_runs,
                            'passed_runs': passed_runs,
                            'failed_runs': row[3] or 0,
                            'pass_rate': (passed_runs / total_runs * 100) if total_runs > 0 else 0,
                            'duration_stddev': float(row[4]) if row[4] else 0,
                            'avg_duration_seconds': float(row[5]) if row[5] else 0,
                            'flakiness_score': float(row[4]) if row[4] else 0
                        })
                    
                    return flaky
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting most flaky suites: {e}")
            return []
    
    # ========================================================================
    # Failure Analysis
    # ========================================================================
    
    def get_failure_analysis(self, plan_id: int) -> Optional[Dict]:
        """
        Get failure analysis for a plan
        
        Args:
            plan_id: ID of the plan
            
        Returns:
            Failure analysis or None
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Get total failures
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total_failures,
                               COUNT(DISTINCT test_suite_id) as suites_with_failures,
                               SUM(failed_tests) as total_failed_tests
                        FROM execution_suite_plan_suite_runs
                        WHERE execution_suite_plan_run_id IN (
                            SELECT id FROM execution_suite_plan_runs
                            WHERE execution_suite_plan_id = %s
                        )
                        AND status = 'failed'
                        """,
                        (plan_id,)
                    )
                    
                    result = cursor.fetchone()
                    total_failures = result[0] or 0
                    suites_with_failures = result[1] or 0
                    total_failed_tests = result[2] or 0
                    
                    # Get failure rate
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total_runs,
                               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs
                        FROM execution_suite_plan_runs
                        WHERE execution_suite_plan_id = %s
                        """,
                        (plan_id,)
                    )
                    
                    result2 = cursor.fetchone()
                    total_runs = result2[0] or 0
                    failed_runs = result2[1] or 0
                    
                    return {
                        'plan_id': plan_id,
                        'total_failures': total_failures,
                        'suites_with_failures': suites_with_failures,
                        'total_failed_tests': total_failed_tests,
                        'failure_rate': (failed_runs / total_runs * 100) if total_runs > 0 else 0,
                        'avg_failures_per_run': (total_failures / total_runs) if total_runs > 0 else 0
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error getting failure analysis: {e}")
            return None
    
    # ========================================================================
    # Comparison Analysis
    # ========================================================================
    
    def compare_plan_runs(
        self,
        plan_id: int,
        run_id_1: int,
        run_id_2: int
    ) -> Optional[Dict]:
        """
        Compare two plan runs
        
        Args:
            plan_id: ID of the plan
            run_id_1: ID of first run
            run_id_2: ID of second run
            
        Returns:
            Comparison data or None
        """
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Get run 1 stats
                    cursor.execute(
                        """
                        SELECT status, total_tests, passed_tests, failed_tests,
                               EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds
                        FROM execution_suite_plan_runs
                        WHERE id = %s AND execution_suite_plan_id = %s
                        """,
                        (run_id_1, plan_id)
                    )
                    
                    run1 = cursor.fetchone()
                    if not run1:
                        return None
                    
                    # Get run 2 stats
                    cursor.execute(
                        """
                        SELECT status, total_tests, passed_tests, failed_tests,
                               EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds
                        FROM execution_suite_plan_runs
                        WHERE id = %s AND execution_suite_plan_id = %s
                        """,
                        (run_id_2, plan_id)
                    )
                    
                    run2 = cursor.fetchone()
                    if not run2:
                        return None
                    
                    return {
                        'plan_id': plan_id,
                        'run_1': {
                            'id': run_id_1,
                            'status': run1[0],
                            'total_tests': run1[1],
                            'passed_tests': run1[2],
                            'failed_tests': run1[3],
                            'duration_seconds': float(run1[4]) if run1[4] else 0,
                            'pass_rate': (run1[2] / run1[1] * 100) if run1[1] > 0 else 0
                        },
                        'run_2': {
                            'id': run_id_2,
                            'status': run2[0],
                            'total_tests': run2[1],
                            'passed_tests': run2[2],
                            'failed_tests': run2[3],
                            'duration_seconds': float(run2[4]) if run2[4] else 0,
                            'pass_rate': (run2[2] / run2[1] * 100) if run2[1] > 0 else 0
                        },
                        'differences': {
                            'test_count_change': run2[1] - run1[1],
                            'passed_tests_change': run2[2] - run1[2],
                            'failed_tests_change': run2[3] - run1[3],
                            'duration_change_seconds': (run2[4] if run2[4] else 0) - (run1[4] if run1[4] else 0),
                            'pass_rate_change': ((run2[2] / run2[1] * 100) if run2[1] > 0 else 0) - 
                                               ((run1[2] / run1[1] * 100) if run1[1] > 0 else 0)
                        }
                    }
            finally:
                return_db_connection(conn)
        except Exception as e:
            self.logger.error(f"Error comparing plan runs: {e}")
            return None
    
    # ========================================================================
    # Summary Statistics
    # ========================================================================
    
    def get_dashboard_summary(self, plan_id: int) -> Optional[Dict]:
        """
        Get dashboard summary for a plan
        
        Args:
            plan_id: ID of the plan
            
        Returns:
            Dashboard summary or None
        """
        try:
            stats = self.get_plan_execution_stats(plan_id)
            if not stats:
                return None
            
            failure_analysis = self.get_failure_analysis(plan_id)
            slowest_suites = self.get_slowest_suites(plan_id, 5)
            flaky_suites = self.get_most_flaky_suites(plan_id, 5)
            trend = self.get_execution_trend(plan_id, 7)
            
            return {
                'plan_id': plan_id,
                'execution_stats': stats,
                'failure_analysis': failure_analysis,
                'slowest_suites': slowest_suites,
                'flaky_suites': flaky_suites,
                'recent_trend': trend,
                'generated_at': datetime.now()
            }
        except Exception as e:
            self.logger.error(f"Error generating dashboard summary: {e}")
            return None


# Global metrics service instance
_metrics_service_instance = None


def get_metrics_service() -> MetricsService:
    """Get or create global metrics service instance"""
    global _metrics_service_instance
    if _metrics_service_instance is None:
        _metrics_service_instance = MetricsService()
    return _metrics_service_instance
