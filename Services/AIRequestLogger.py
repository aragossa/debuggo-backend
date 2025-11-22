"""
AIRequestLogger Service

Logs all AI API requests with token counts, pricing, and metadata.
Captures pricing at the time of request to maintain immutable cost records.
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.System import System


class AIRequestLogger:
    """
    Logs AI API requests with token usage and pricing information.
    
    Features:
    - Captures input/output tokens from Gemini responses
    - Snapshots pricing at time of request (immutable)
    - Calculates cost based on tiered pricing
    - Tracks request type (ui_step, api_test, etc.)
    - Stores metadata for analysis
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.system = System()
    
    def _setup_logger(self):
        """Setup logger for AI request logging."""
        logger = logging.getLogger('AIRequestLogger')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def log_request(
        self,
        ai_model_id: int,
        request_type: str,
        input_tokens: int,
        output_tokens: int,
        response_time_ms: int = 0,
        client_id: Optional[str] = None,
        user_id: Optional[int] = None,
        request_context: Optional[str] = None,
        prompt_length: int = 0,
        response_length: int = 0,
        status: str = 'success',
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cache_input_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_storage_tokens: int = 0
    ) -> Optional[int]:
        """
        Log an AI API request with token usage and pricing.
        
        Args:
            ai_model_id: ID of the AI model used
            request_type: Type of request ('ui_step', 'ui_error', 'api_test', 'api_schema', 'image_analysis', 'text_analysis', 'other')
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            response_time_ms: Response time in milliseconds
            client_id: Optional client ID (UUID)
            user_id: Optional user ID
            request_context: Optional context (e.g., test_case_id, schema_id)
            prompt_length: Length of the prompt in characters
            response_length: Length of the response in characters
            status: Request status ('success', 'error', 'rate_limited', 'blocked')
            error_message: Optional error message
            metadata: Optional metadata dictionary
            cache_input_tokens: Number of cache input tokens (context caching)
            cache_creation_tokens: Number of cache creation tokens
            cache_read_tokens: Number of cache read tokens
            cache_storage_tokens: Number of cache storage tokens
            
        Returns:
            int: The ID of the logged request, or None if logging failed
        """
        try:
            # Get model pricing information
            model_pricing = self._get_model_pricing(ai_model_id)
            if not model_pricing:
                self.logger.error(f"Failed to get pricing for model {ai_model_id}")
                return None
            
            # Calculate costs based on tiered pricing
            total_tokens = input_tokens + output_tokens
            input_cost = self._calculate_cost(
                input_tokens,
                model_pricing['input_price_per_1m'],
                model_pricing.get('tier_threshold', 0),
                model_pricing.get('input_price_per_1m_above', model_pricing['input_price_per_1m'])
            )
            output_cost = self._calculate_cost(
                output_tokens,
                model_pricing['output_price_per_1m'],
                model_pricing.get('tier_threshold', 0),
                model_pricing.get('output_price_per_1m_above', model_pricing['output_price_per_1m'])
            )
            
            # Calculate cache costs
            cache_input_cost = self._calculate_cost(
                cache_input_tokens,
                model_pricing.get('cache_input_price_per_1m', 0),
                model_pricing.get('tier_threshold', 0),
                model_pricing.get('cache_input_price_per_1m_above', model_pricing.get('cache_input_price_per_1m', 0))
            )
            cache_creation_cost = self._calculate_cost(
                cache_creation_tokens,
                model_pricing['input_price_per_1m'],  # Creation uses input pricing
                model_pricing.get('tier_threshold', 0),
                model_pricing.get('input_price_per_1m_above', model_pricing['input_price_per_1m'])
            )
            cache_read_cost = self._calculate_cost(
                cache_read_tokens,
                model_pricing.get('cache_input_price_per_1m', 0) * 0.1,  # Read is 10% of cache input price
                model_pricing.get('tier_threshold', 0),
                model_pricing.get('cache_input_price_per_1m_above', model_pricing.get('cache_input_price_per_1m', 0)) * 0.1
            )
            cache_storage_cost = self._calculate_cost(
                cache_storage_tokens,
                model_pricing.get('cache_storage_price_per_1m_hour', 0),
                0,  # No tier for storage
                0
            )
            
            total_cost = input_cost + output_cost + cache_input_cost + cache_creation_cost + cache_read_cost + cache_storage_cost
            
            # Log to database
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO ai_request_logs (
                            ai_model_id,
                            model_name,
                            client_id,
                            user_id,
                            request_type,
                            request_context,
                            input_tokens,
                            output_tokens,
                            total_tokens,
                            input_price_per_1m,
                            output_price_per_1m,
                            tier_threshold,
                            input_price_per_1m_above,
                            output_price_per_1m_above,
                            input_cost,
                            output_cost,
                            total_cost,
                            cache_input_tokens,
                            cache_creation_tokens,
                            cache_read_tokens,
                            cache_storage_tokens,
                            cache_input_price_per_1m,
                            cache_input_price_per_1m_above,
                            cache_storage_price_per_1m_hour,
                            cache_input_cost,
                            cache_creation_cost,
                            cache_read_cost,
                            cache_storage_cost,
                            prompt_length,
                            response_length,
                            response_time_ms,
                            status,
                            error_message,
                            metadata,
                            created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        RETURNING id
                    """, (
                        ai_model_id,
                        model_pricing.get('name', 'Unknown'),
                        client_id,
                        user_id,
                        request_type,
                        request_context,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                        Decimal(str(model_pricing['input_price_per_1m'])),
                        Decimal(str(model_pricing['output_price_per_1m'])),
                        model_pricing.get('tier_threshold', 0),
                        Decimal(str(model_pricing.get('input_price_per_1m_above', model_pricing['input_price_per_1m']))),
                        Decimal(str(model_pricing.get('output_price_per_1m_above', model_pricing['output_price_per_1m']))),
                        Decimal(str(input_cost)),
                        Decimal(str(output_cost)),
                        Decimal(str(total_cost)),
                        cache_input_tokens,
                        cache_creation_tokens,
                        cache_read_tokens,
                        cache_storage_tokens,
                        Decimal(str(model_pricing.get('cache_input_price_per_1m', 0))),
                        Decimal(str(model_pricing.get('cache_input_price_per_1m_above', model_pricing.get('cache_input_price_per_1m', 0)))),
                        Decimal(str(model_pricing.get('cache_storage_price_per_1m_hour', 0))),
                        Decimal(str(cache_input_cost)),
                        Decimal(str(cache_creation_cost)),
                        Decimal(str(cache_read_cost)),
                        Decimal(str(cache_storage_cost)),
                        prompt_length,
                        response_length,
                        response_time_ms,
                        status,
                        error_message,
                        json.dumps(metadata) if metadata else None,
                        datetime.now()
                    ))
                    
                    request_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    # Log summary
                    self.logger.info(
                        f"✅ Logged AI request #{request_id}: "
                        f"type={request_type}, "
                        f"tokens={total_tokens} (in={input_tokens}, out={output_tokens}), "
                        f"cost=${total_cost:.8f}, "
                        f"time={response_time_ms}ms"
                    )
                    
                    return request_id
                    
        except Exception as e:
            self.logger.error(f"Error logging AI request: {str(e)}", exc_info=True)
            return None
    
    def _get_model_pricing(self, ai_model_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current pricing for an AI model.
        
        Args:
            ai_model_id: ID of the AI model
            
        Returns:
            Dict with pricing information, or None if not found
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            id,
                            name,
                            input_price_per_1m,
                            output_price_per_1m,
                            tier_threshold,
                            input_price_per_1m_above,
                            output_price_per_1m_above,
                            cache_input_price_per_1m,
                            cache_input_price_per_1m_above,
                            cache_storage_price_per_1m_hour
                        FROM ai_models
                        WHERE id = %s
                    """, (ai_model_id,))
                    
                    row = cursor.fetchone()
                    if not row:
                        self.logger.warning(f"AI model {ai_model_id} not found")
                        return None
                    
                    return {
                        'id': row[0],
                        'name': row[1],
                        'input_price_per_1m': float(row[2]) if row[2] else 0,
                        'output_price_per_1m': float(row[3]) if row[3] else 0,
                        'tier_threshold': row[4] or 0,
                        'input_price_per_1m_above': float(row[5]) if row[5] else float(row[2]) if row[2] else 0,
                        'output_price_per_1m_above': float(row[6]) if row[6] else float(row[3]) if row[3] else 0,
                        'cache_input_price_per_1m': float(row[7]) if row[7] else 0,
                        'cache_input_price_per_1m_above': float(row[8]) if row[8] else float(row[7]) if row[7] else 0,
                        'cache_storage_price_per_1m_hour': float(row[9]) if row[9] else 0,
                    }
                    
        except Exception as e:
            self.logger.error(f"Error getting model pricing: {str(e)}")
            return None
    
    def _calculate_cost(
        self,
        tokens: int,
        price_per_1m: float,
        tier_threshold: int = 0,
        price_per_1m_above: Optional[float] = None
    ) -> float:
        """
        Calculate cost for tokens with optional tiered pricing.
        
        Args:
            tokens: Number of tokens
            price_per_1m: Price per 1 million tokens (base tier)
            tier_threshold: Token threshold for tier change (0 = no tier)
            price_per_1m_above: Price per 1M tokens above threshold
            
        Returns:
            float: Total cost in dollars
        """
        if tokens == 0:
            return 0.0
        
        # If no tier threshold, use simple calculation
        if tier_threshold == 0:
            return (tokens / 1_000_000) * price_per_1m
        
        # Tiered pricing
        if price_per_1m_above is None:
            price_per_1m_above = price_per_1m
        
        if tokens <= tier_threshold:
            # All tokens in base tier
            return (tokens / 1_000_000) * price_per_1m
        else:
            # Some tokens in base tier, some in higher tier
            base_tier_tokens = tier_threshold
            above_tier_tokens = tokens - tier_threshold
            
            base_cost = (base_tier_tokens / 1_000_000) * price_per_1m
            above_cost = (above_tier_tokens / 1_000_000) * price_per_1m_above
            
            return base_cost + above_cost
    
    def get_usage_stats(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get AI usage statistics for a client or globally.
        
        Args:
            client_id: Optional client ID (UUID) to filter by
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Dict with usage statistics
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Build query
                    query = """
                        SELECT 
                            COUNT(*) as total_requests,
                            SUM(input_tokens) as total_input_tokens,
                            SUM(output_tokens) as total_output_tokens,
                            SUM(total_tokens) as total_tokens,
                            SUM(total_cost) as total_cost,
                            AVG(response_time_ms) as avg_response_time_ms,
                            MIN(created_at) as first_request_at,
                            MAX(created_at) as last_request_at
                        FROM ai_request_logs
                        WHERE 1=1
                    """
                    
                    params = []
                    
                    if client_id:
                        query += " AND client_id = %s"
                        params.append(client_id)
                    
                    if start_date:
                        query += " AND created_at >= %s"
                        params.append(start_date)
                    
                    if end_date:
                        query += " AND created_at <= %s"
                        params.append(end_date)
                    
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    
                    if not row:
                        return {
                            'total_requests': 0,
                            'total_input_tokens': 0,
                            'total_output_tokens': 0,
                            'total_tokens': 0,
                            'total_cost': 0,
                            'avg_response_time_ms': 0
                        }
                    
                    return {
                        'total_requests': row[0] or 0,
                        'total_input_tokens': row[1] or 0,
                        'total_output_tokens': row[2] or 0,
                        'total_tokens': row[3] or 0,
                        'total_cost': float(row[4]) if row[4] else 0,
                        'avg_response_time_ms': float(row[5]) if row[5] else 0,
                        'first_request_at': row[6],
                        'last_request_at': row[7]
                    }
                    
        except Exception as e:
            self.logger.error(f"Error getting usage stats: {str(e)}")
            return {}
    
    def get_request_type_stats(
        self,
        client_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics grouped by request type.
        
        Args:
            client_id: Optional client ID (UUID) to filter by
            
        Returns:
            Dict with statistics by request type
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    query = """
                        SELECT 
                            request_type,
                            COUNT(*) as total_requests,
                            SUM(input_tokens) as total_input_tokens,
                            SUM(output_tokens) as total_output_tokens,
                            SUM(total_tokens) as total_tokens,
                            SUM(total_cost) as total_cost,
                            AVG(response_time_ms) as avg_response_time_ms
                        FROM ai_request_logs
                        WHERE 1=1
                    """
                    
                    params = []
                    
                    if client_id:
                        query += " AND client_id = %s"
                        params.append(client_id)
                    
                    query += " GROUP BY request_type ORDER BY total_cost DESC"
                    
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    stats = {}
                    for row in rows:
                        stats[row[0]] = {
                            'total_requests': row[1],
                            'total_input_tokens': row[2] or 0,
                            'total_output_tokens': row[3] or 0,
                            'total_tokens': row[4] or 0,
                            'total_cost': float(row[5]) if row[5] else 0,
                            'avg_response_time_ms': float(row[6]) if row[6] else 0
                        }
                    
                    return stats
                    
        except Exception as e:
            self.logger.error(f"Error getting request type stats: {str(e)}")
            return {}
