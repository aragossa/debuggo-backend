"""
AgentMonitoring Service

Collects and exposes metrics for Phase 1 services.
Provides real-time monitoring of validation, confidence scoring, and feedback collection.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from auroqa.Utils.Connectors.db_utils import get_db_connection_context


class AgentMonitoring:
    """
    Monitoring service for Phase 1 AI Agent services.
    Tracks validation, confidence scoring, feedback collection, and retry metrics.
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        """Setup logger for AgentMonitoring."""
        logger = logging.getLogger('AgentMonitoring')
        logger.setLevel(logging.DEBUG)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    # ==================== VALIDATION METRICS ====================
    
    def get_validation_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get validation metrics for the last N hours.
        
        Args:
            hours: Number of hours to look back (default 24)
            
        Returns:
            Dictionary with validation metrics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get total validations
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total,
                            SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid_count,
                            AVG(confidence) as avg_confidence,
                            MIN(confidence) as min_confidence,
                            MAX(confidence) as max_confidence
                        FROM validation_results
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                    """, (hours,))
                    
                    row = cursor.fetchone()
                    total = row[0] or 0
                    valid_count = row[1] or 0
                    avg_confidence = float(row[2]) if row[2] else 0
                    min_confidence = float(row[3]) if row[3] else 0
                    max_confidence = float(row[4]) if row[4] else 0
                    
                    # Get error distribution from execution_feedback instead
                    cursor.execute("""
                        SELECT error_type, COUNT(*) as count
                        FROM execution_feedback
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                        GROUP BY error_type
                        ORDER BY count DESC
                    """, (hours,))
                    
                    errors = {row[0]: row[1] for row in cursor.fetchall()}
            
            success_rate = (valid_count / total * 100) if total > 0 else 0
            
            metrics = {
                'total_validations': total,
                'valid_steps': valid_count,
                'invalid_steps': total - valid_count,
                'success_rate': round(success_rate, 2),
                'avg_confidence': round(avg_confidence, 2),
                'min_confidence': round(min_confidence, 2),
                'max_confidence': round(max_confidence, 2),
                'error_distribution': errors,
                'unique_error_types': len(errors),
                'time_period_hours': hours
            }
            
            self.logger.info(f"📊 Validation metrics: {success_rate:.1f}% success rate")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting validation metrics: {str(e)}")
            return {}
    
    # ==================== CONFIDENCE METRICS ====================
    
    def get_confidence_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get confidence scoring metrics for the last N hours.
        
        Args:
            hours: Number of hours to look back (default 24)
            
        Returns:
            Dictionary with confidence metrics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get confidence distribution
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total,
                            AVG(overall_confidence) as avg_confidence,
                            MIN(overall_confidence) as min_confidence,
                            MAX(overall_confidence) as max_confidence,
                            SUM(CASE WHEN risk_level = 'low' THEN 1 ELSE 0 END) as low_risk,
                            SUM(CASE WHEN risk_level = 'medium' THEN 1 ELSE 0 END) as medium_risk,
                            SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) as high_risk
                        FROM confidence_scores
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                    """, (hours,))
                    
                    row = cursor.fetchone()
                    total = row[0] or 0
                    avg_confidence = float(row[1]) if row[1] else 0
                    min_confidence = float(row[2]) if row[2] else 0
                    max_confidence = float(row[3]) if row[3] else 0
                    low_risk = row[4] or 0
                    medium_risk = row[5] or 0
                    high_risk = row[6] or 0
                    
                    # Get factor averages
                    cursor.execute("""
                        SELECT 
                            AVG(selector_confidence) as selector,
                            AVG(action_confidence) as action,
                            AVG(data_confidence) as data,
                            AVG(pattern_confidence) as pattern
                        FROM confidence_scores
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                    """, (hours,))
                    
                    factor_row = cursor.fetchone()
                    factors = {
                        'selector': round(float(factor_row[0]) if factor_row[0] else 0, 2),
                        'action': round(float(factor_row[1]) if factor_row[1] else 0, 2),
                        'data': round(float(factor_row[2]) if factor_row[2] else 0, 2),
                        'pattern': round(float(factor_row[3]) if factor_row[3] else 0, 2)
                    }
            
            low_risk_pct = (low_risk / total * 100) if total > 0 else 0
            medium_risk_pct = (medium_risk / total * 100) if total > 0 else 0
            high_risk_pct = (high_risk / total * 100) if total > 0 else 0
            
            metrics = {
                'total_scored': total,
                'avg_confidence': round(avg_confidence, 2),
                'min_confidence': round(min_confidence, 2),
                'max_confidence': round(max_confidence, 2),
                'low_risk_steps': low_risk,
                'medium_risk_steps': medium_risk,
                'high_risk_steps': high_risk,
                'low_risk_percentage': round(low_risk_pct, 2),
                'medium_risk_percentage': round(medium_risk_pct, 2),
                'high_risk_percentage': round(high_risk_pct, 2),
                'factor_averages': factors,
                'time_period_hours': hours
            }
            
            self.logger.info(f"📊 Confidence metrics: {avg_confidence:.1f}% avg confidence")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting confidence metrics: {str(e)}")
            return {}
    
    # ==================== FEEDBACK METRICS ====================
    
    def get_feedback_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get execution feedback metrics for the last N hours.
        
        Args:
            hours: Number of hours to look back (default 24)
            
        Returns:
            Dictionary with feedback metrics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get total failures and error categories
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_failures,
                            COUNT(DISTINCT error_type) as unique_error_types
                        FROM execution_feedback
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                    """, (hours,))
                    
                    row = cursor.fetchone()
                    total_failures = row[0] or 0
                    unique_error_types = row[1] or 0
                    
                    # Get error category distribution
                    cursor.execute("""
                        SELECT error_type, COUNT(*) as count
                        FROM execution_feedback
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                        GROUP BY error_type
                        ORDER BY count DESC
                        LIMIT 10
                    """, (hours,))
                    
                    error_categories = {row[0]: row[1] for row in cursor.fetchall()}
                    
                    # Get most common errors
                    cursor.execute("""
                        SELECT error_message, COUNT(*) as count
                        FROM execution_feedback
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                        GROUP BY error_message
                        ORDER BY count DESC
                        LIMIT 5
                    """, (hours,))
                    
                    common_errors = [
                        {'message': row[0], 'count': row[1]}
                        for row in cursor.fetchall()
                    ]
            
            metrics = {
                'total_failures': total_failures,
                'unique_error_types': unique_error_types,
                'error_categories': error_categories,
                'most_common_errors': common_errors,
                'time_period_hours': hours
            }
            
            self.logger.info(f"📊 Feedback metrics: {total_failures} failures in last {hours}h")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting feedback metrics: {str(e)}")
            return {}
    
    # ==================== RETRY METRICS ====================
    
    def get_retry_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get retry attempt metrics for the last N hours.
        
        Args:
            hours: Number of hours to look back (default 24)
            
        Returns:
            Dictionary with retry metrics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get retry statistics
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_retries,
                            SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_retries,
                            AVG(attempt_number) as avg_attempts,
                            MAX(attempt_number) as max_attempts
                        FROM retry_attempts
                        WHERE created_at >= NOW() - INTERVAL '%s hours'
                    """, (hours,))
                    
                    row = cursor.fetchone()
                    total_retries = row[0] or 0
                    successful_retries = row[1] or 0
                    avg_attempts = float(row[2]) if row[2] else 0
                    max_attempts = row[3] or 0
            
            success_rate = (successful_retries / total_retries * 100) if total_retries > 0 else 0
            
            metrics = {
                'total_retry_attempts': total_retries,
                'successful_retries': successful_retries,
                'failed_retries': total_retries - successful_retries,
                'retry_success_rate': round(success_rate, 2),
                'avg_attempts_per_step': round(avg_attempts, 2),
                'max_attempts': max_attempts,
                'time_period_hours': hours
            }
            
            self.logger.info(f"📊 Retry metrics: {success_rate:.1f}% retry success rate")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting retry metrics: {str(e)}")
            return {}
    
    # ==================== COMBINED METRICS ====================
    
    def get_all_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get all Phase 1 metrics combined.
        
        Args:
            hours: Number of hours to look back (default 24)
            
        Returns:
            Dictionary with all metrics
        """
        try:
            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'time_period_hours': hours,
                'validation': self.get_validation_metrics(hours),
                'confidence': self.get_confidence_metrics(hours),
                'feedback': self.get_feedback_metrics(hours),
                'retry': self.get_retry_metrics(hours)
            }
            
            self.logger.info("📊 All metrics retrieved successfully")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting all metrics: {str(e)}")
            return {}
    
    # ==================== HEALTH CHECK ====================
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of all Phase 1 services.
        
        Returns:
            Dictionary with health status
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Check if tables exist and have data
                    tables = ['validation_results', 'execution_feedback', 'confidence_scores', 'retry_attempts']
                    table_status = {}
                    
                    for table in tables:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        table_status[table] = {
                            'exists': True,
                            'record_count': count,
                            'status': 'healthy' if count > 0 else 'empty'
                        }
            
            # Check recent activity (last hour)
            recent_metrics = self.get_all_metrics(hours=1)
            
            overall_status = 'healthy'
            if not recent_metrics.get('validation') or recent_metrics['validation'].get('total_validations', 0) == 0:
                overall_status = 'warning'
            
            health = {
                'overall_status': overall_status,
                'timestamp': datetime.utcnow().isoformat(),
                'tables': table_status,
                'recent_activity': {
                    'validations_1h': recent_metrics.get('validation', {}).get('total_validations', 0),
                    'failures_1h': recent_metrics.get('feedback', {}).get('total_failures', 0),
                    'retries_1h': recent_metrics.get('retry', {}).get('total_retry_attempts', 0)
                }
            }
            
            self.logger.info(f"🏥 Health check: {overall_status}")
            return health
            
        except Exception as e:
            self.logger.error(f"Error getting health status: {str(e)}")
            return {'overall_status': 'error', 'error': str(e)}
    
    # ==================== ALERTS ====================
    
    def check_alerts(self) -> Dict[str, Any]:
        """
        Check for alert conditions based on metrics.
        
        Returns:
            Dictionary with alerts
        """
        alerts = []
        
        try:
            # Get recent metrics (last hour)
            metrics = self.get_all_metrics(hours=1)
            
            # Check validation success rate
            validation = metrics.get('validation', {})
            if validation.get('success_rate', 100) < 85:
                alerts.append({
                    'severity': 'warning',
                    'type': 'validation_success_rate',
                    'message': f"Validation success rate is {validation.get('success_rate')}% (target: >90%)",
                    'value': validation.get('success_rate')
                })
            
            # Check average confidence
            confidence = metrics.get('confidence', {})
            if confidence.get('avg_confidence', 100) < 70:
                alerts.append({
                    'severity': 'warning',
                    'type': 'low_confidence',
                    'message': f"Average confidence is {confidence.get('avg_confidence')}% (target: >75%)",
                    'value': confidence.get('avg_confidence')
                })
            
            # Check high risk steps
            high_risk_pct = confidence.get('high_risk_percentage', 0)
            if high_risk_pct > 30:
                alerts.append({
                    'severity': 'warning',
                    'type': 'high_risk_steps',
                    'message': f"High risk steps: {high_risk_pct}% (target: <30%)",
                    'value': high_risk_pct
                })
            
            # Check error types
            feedback = metrics.get('feedback', {})
            if feedback.get('unique_error_types', 0) > 10:
                alerts.append({
                    'severity': 'info',
                    'type': 'many_error_types',
                    'message': f"Found {feedback.get('unique_error_types')} unique error types",
                    'value': feedback.get('unique_error_types')
                })
            
            # Check total failures
            total_failures = feedback.get('total_failures', 0)
            if total_failures > 50:
                alerts.append({
                    'severity': 'warning',
                    'type': 'high_failure_rate',
                    'message': f"High failure count: {total_failures} in last hour",
                    'value': total_failures
                })
            
            result = {
                'timestamp': datetime.utcnow().isoformat(),
                'alert_count': len(alerts),
                'alerts': alerts
            }
            
            if alerts:
                self.logger.warning(f"⚠️ {len(alerts)} alerts detected")
            else:
                self.logger.info("✅ No alerts")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error checking alerts: {str(e)}")
            return {'error': str(e), 'alerts': []}
    
    # ==================== TREND ANALYSIS ====================
    
    def get_trends(self, hours: int = 24, interval_minutes: int = 60) -> Dict[str, Any]:
        """
        Get metric trends over time.
        
        Args:
            hours: Number of hours to look back
            interval_minutes: Interval for data points (default 60 minutes)
            
        Returns:
            Dictionary with trend data
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get validation trend
                    cursor.execute(f"""
                        SELECT 
                            DATE_TRUNC('hour', created_at) as hour,
                            COUNT(*) as total,
                            SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid,
                            AVG(confidence) as avg_confidence
                        FROM validation_results
                        WHERE created_at >= NOW() - INTERVAL '{hours} hours'
                        GROUP BY DATE_TRUNC('hour', created_at)
                        ORDER BY hour ASC
                    """)
                    
                    validation_trend = [
                        {
                            'timestamp': row[0].isoformat() if row[0] else None,
                            'total': row[1],
                            'valid': row[2],
                            'success_rate': round((row[2] / row[1] * 100) if row[1] > 0 else 0, 2),
                            'avg_confidence': round(float(row[3]) if row[3] else 0, 2)
                        }
                        for row in cursor.fetchall()
                    ]
                    
                    # Get confidence trend
                    cursor.execute(f"""
                        SELECT 
                            DATE_TRUNC('hour', created_at) as hour,
                            AVG(overall_confidence) as avg_confidence,
                            SUM(CASE WHEN risk_level = 'low' THEN 1 ELSE 0 END) as low_risk,
                            SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) as high_risk
                        FROM confidence_scores
                        WHERE created_at >= NOW() - INTERVAL '{hours} hours'
                        GROUP BY DATE_TRUNC('hour', created_at)
                        ORDER BY hour ASC
                    """)
                    
                    confidence_trend = [
                        {
                            'timestamp': row[0].isoformat() if row[0] else None,
                            'avg_confidence': round(float(row[1]) if row[1] else 0, 2),
                            'low_risk': row[2],
                            'high_risk': row[3]
                        }
                        for row in cursor.fetchall()
                    ]
                    
                    # Get failure trend
                    cursor.execute(f"""
                        SELECT 
                            DATE_TRUNC('hour', created_at) as hour,
                            COUNT(*) as total_failures
                        FROM execution_feedback
                        WHERE created_at >= NOW() - INTERVAL '{hours} hours'
                        GROUP BY DATE_TRUNC('hour', created_at)
                        ORDER BY hour ASC
                    """)
                    
                    failure_trend = [
                        {
                            'timestamp': row[0].isoformat() if row[0] else None,
                            'total_failures': row[1]
                        }
                        for row in cursor.fetchall()
                    ]
            
            trends = {
                'timestamp': datetime.utcnow().isoformat(),
                'time_period_hours': hours,
                'validation_trend': validation_trend,
                'confidence_trend': confidence_trend,
                'failure_trend': failure_trend
            }
            
            self.logger.info(f"📈 Trends retrieved for {hours}h period")
            return trends
            
        except Exception as e:
            self.logger.error(f"Error getting trends: {str(e)}")
            return {}
