"""
Generation Cost Analytics Service

Provides statistical analysis of AI generation job costs.
Calculates metrics like mean, median, percentiles, and aggregates by time period.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.System import System


class GenerationCostAnalytics:
    """
    Analyzes costs of AI generation jobs with comprehensive statistics.
    
    Features:
    - Aggregates costs by generation_job_id
    - Calculates statistical metrics (mean, median, percentiles, std dev)
    - Groups by time periods (day, week, month, year)
    - Provides min/max and total sum
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.system = System()
    
    def _setup_logger(self):
        """Setup logger for generation cost analytics."""
        logger = logging.getLogger('GenerationCostAnalytics')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def get_generation_costs(
        self,
        client_id: Optional[str] = None,
        period: str = 'day',
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get generation job cost statistics.
        
        Args:
            client_id: Optional client ID to filter by
            period: Time period ('day', 'week', 'month', 'year', 'all')
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Dictionary with statistics and individual job costs
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Build date filter based on period
                    date_filter = self._build_date_filter(period, start_date, end_date)
                    
                    # Get aggregated costs per generation_job_id
                    query = f"""
                        SELECT 
                            generation_job_id,
                            COUNT(*) as request_count,
                            SUM(total_cost) as total_cost,
                            MIN(created_at) as start_time,
                            MAX(created_at) as end_time,
                            STRING_AGG(DISTINCT request_type, ', ') as request_types
                        FROM ai_request_logs
                        WHERE generation_job_id IS NOT NULL
                            {' AND client_id = %s' if client_id else ''}
                            {date_filter}
                        GROUP BY generation_job_id
                        ORDER BY start_time DESC
                    """
                    
                    params = []
                    if client_id:
                        params.append(client_id)
                    
                    cur.execute(query, params if params else None)
                    job_costs = cur.fetchall()
                    
                    if not job_costs:
                        return {
                            'period': period,
                            'start_date': start_date.isoformat() if start_date else None,
                            'end_date': end_date.isoformat() if end_date else None,
                            'total_jobs': 0,
                            'statistics': self._empty_statistics(),
                            'jobs': []
                        }
                    
                    # Convert to list of dicts and extract costs
                    jobs = []
                    costs = []
                    for row in job_costs:
                        job_data = {
                            'generation_job_id': str(row[0]),
                            'request_count': row[1],
                            'total_cost': float(row[2]) if row[2] else 0.0,
                            'start_time': row[3].isoformat() if row[3] else None,
                            'end_time': row[4].isoformat() if row[4] else None,
                            'duration_seconds': (row[4] - row[3]).total_seconds() if (row[3] and row[4]) else 0,
                            'request_types': row[5]
                        }
                        jobs.append(job_data)
                        costs.append(job_data['total_cost'])
                    
                    # Calculate statistics
                    statistics = self._calculate_statistics(costs)
                    
                    return {
                        'period': period,
                        'start_date': start_date.isoformat() if start_date else None,
                        'end_date': end_date.isoformat() if end_date else None,
                        'total_jobs': len(jobs),
                        'statistics': statistics,
                        'jobs': jobs[:100]  # Limit to 100 most recent jobs
                    }
                    
        except Exception as e:
            self.logger.error(f"Error getting generation costs: {e}", exc_info=True)
            return {
                'error': str(e),
                'period': period,
                'statistics': self._empty_statistics(),
                'jobs': []
            }
    
    def _build_date_filter(
        self,
        period: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """Build SQL date filter based on period."""
        if start_date and end_date:
            return f"AND created_at BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'"
        
        now = datetime.now()
        
        if period == 'day':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return f"AND created_at >= '{start.isoformat()}'"
        elif period == 'week':
            start = now - timedelta(days=7)
            return f"AND created_at >= '{start.isoformat()}'"
        elif period == 'month':
            start = now - timedelta(days=30)
            return f"AND created_at >= '{start.isoformat()}'"
        elif period == 'year':
            start = now - timedelta(days=365)
            return f"AND created_at >= '{start.isoformat()}'"
        else:  # 'all'
            return ""
    
    def _calculate_statistics(self, costs: List[float]) -> Dict[str, Any]:
        """Calculate statistical metrics for costs."""
        if not costs:
            return self._empty_statistics()
        
        import statistics
        
        sorted_costs = sorted(costs)
        n = len(sorted_costs)
        
        try:
            return {
                'mean': round(statistics.mean(costs), 6),
                'median': round(statistics.median(costs), 6),
                'percentile_50': round(statistics.median(costs), 6),
                'percentile_90': round(self._percentile(sorted_costs, 90), 6),
                'percentile_95': round(self._percentile(sorted_costs, 95), 6),
                'percentile_99': round(self._percentile(sorted_costs, 99), 6),
                'min': round(min(costs), 6),
                'max': round(max(costs), 6),
                'std_dev': round(statistics.stdev(costs), 6) if n > 1 else 0.0,
                'total_sum': round(sum(costs), 6),
                'count': n
            }
        except Exception as e:
            self.logger.error(f"Error calculating statistics: {e}")
            return self._empty_statistics()
    
    def _percentile(self, sorted_data: List[float], percentile: int) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        
        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = f + 1
        
        if c >= len(sorted_data):
            return sorted_data[-1]
        
        d0 = sorted_data[f] * (c - k)
        d1 = sorted_data[c] * (k - f)
        
        return d0 + d1
    
    def _empty_statistics(self) -> Dict[str, Any]:
        """Return empty statistics structure."""
        return {
            'mean': 0.0,
            'median': 0.0,
            'percentile_50': 0.0,
            'percentile_90': 0.0,
            'percentile_95': 0.0,
            'percentile_99': 0.0,
            'min': 0.0,
            'max': 0.0,
            'std_dev': 0.0,
            'total_sum': 0.0,
            'count': 0
        }
    
    def get_cost_trends(
        self,
        client_id: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get daily cost trends over specified number of days.
        
        Args:
            client_id: Optional client ID to filter by
            days: Number of days to analyze
            
        Returns:
            List of daily statistics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT 
                            DATE(created_at) as date,
                            COUNT(DISTINCT generation_job_id) as jobs_count,
                            SUM(total_cost) as daily_cost,
                            AVG(total_cost) as avg_cost_per_request
                        FROM ai_request_logs
                        WHERE generation_job_id IS NOT NULL
                            AND created_at >= NOW() - INTERVAL '%s days'
                            {client_filter}
                        GROUP BY DATE(created_at)
                        ORDER BY date DESC
                    """.format(
                        client_filter='AND client_id = %s' if client_id else ''
                    )
                    
                    params = [days]
                    if client_id:
                        params.append(client_id)
                    
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    
                    trends = []
                    for row in rows:
                        trends.append({
                            'date': row[0].isoformat() if row[0] else None,
                            'jobs_count': row[1],
                            'daily_cost': float(row[2]) if row[2] else 0.0,
                            'avg_cost_per_request': float(row[3]) if row[3] else 0.0
                        })
                    
                    return trends
                    
        except Exception as e:
            self.logger.error(f"Error getting cost trends: {e}", exc_info=True)
            return []
