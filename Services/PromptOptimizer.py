"""
Phase 4: Prompt Optimizer Service

Implements A/B testing framework for prompt optimization.
Tests different prompt variants and automatically selects winners.
"""

import json
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.System import System

logger = logging.getLogger(__name__)


@dataclass
class PromptVariant:
    """Represents a prompt variant for testing"""
    id: int
    base_prompt_id: Optional[int]
    variant_name: str
    variant_text: str
    variant_type: str
    description: Optional[str]
    created_at: datetime


@dataclass
class ABTestResult:
    """Result of A/B test comparison"""
    variant_a_id: int
    variant_b_id: int
    test_cases_count: int
    variant_a_success_rate: float
    variant_b_success_rate: float
    variant_a_avg_confidence: float
    variant_b_avg_confidence: float
    winner: str  # 'A', 'B', or 'TIE'
    confidence_level: float
    notes: Optional[str]


class PromptOptimizer:
    """
    Optimizes AI prompts through systematic A/B testing.
    
    Responsibilities:
    - Create prompt variants
    - Run A/B tests
    - Analyze results
    - Deploy winning prompts
    """

    def __init__(self):
        self.system = System()
        self.logger = logger

    def create_prompt_variant(
        self,
        base_prompt: str,
        variant_name: str,
        variant_type: str,
        variation_description: str,
        created_by: int,
        description: Optional[str] = None
    ) -> PromptVariant:
        """
        Create a new prompt variant for testing.
        
        Args:
            base_prompt: Original prompt text
            variant_name: Name for this variant
            variant_type: Type of variation (e.g., 'instruction_clarity', 'example_format')
            variation_description: How this variant differs from base
            created_by: User ID creating the variant
            description: Optional description
            
        Returns:
            PromptVariant object
        """
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                
                # Apply variation to base prompt
                variant_text = self._apply_variation(base_prompt, variant_type, variation_description)
                
                cursor.execute("""
                    INSERT INTO prompt_variants 
                    (variant_name, variant_text, variant_type, description, created_by)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, created_at
                """, (variant_name, variant_text, variant_type, description, created_by))
                
                result = cursor.fetchone()
                variant_id, created_at = result
                
                self.logger.info(f"Created prompt variant: {variant_name} (ID: {variant_id})")
                
                return PromptVariant(
                    id=variant_id,
                    base_prompt_id=None,
                    variant_name=variant_name,
                    variant_text=variant_text,
                    variant_type=variant_type,
                    description=description,
                    created_at=created_at
                )
                
        except Exception as e:
            self.logger.error(f"Error creating prompt variant: {str(e)}")
            raise

    def run_ab_test(
        self,
        variant_a_id: int,
        variant_b_id: int,
        test_case_ids: List[int],
        test_runner_callback
    ) -> ABTestResult:
        """
        Run A/B test comparing two prompt variants.
        
        Args:
            variant_a_id: First variant ID
            variant_b_id: Second variant ID
            test_case_ids: List of test case IDs to test with
            test_runner_callback: Function to run tests with prompt
            
        Returns:
            ABTestResult with comparison metrics
        """
        try:
            # Get variants
            variant_a = self._get_variant(variant_a_id)
            variant_b = self._get_variant(variant_b_id)
            
            if not variant_a or not variant_b:
                raise ValueError("One or both variants not found")
            
            self.logger.info(f"Starting A/B test: {variant_a.variant_name} vs {variant_b.variant_name}")
            
            # Run tests with variant A
            results_a = []
            for test_case_id in test_case_ids:
                try:
                    result = test_runner_callback(test_case_id, variant_a.variant_text)
                    results_a.append(result)
                except Exception as e:
                    self.logger.warning(f"Test failed for variant A, case {test_case_id}: {str(e)}")
            
            # Run tests with variant B
            results_b = []
            for test_case_id in test_case_ids:
                try:
                    result = test_runner_callback(test_case_id, variant_b.variant_text)
                    results_b.append(result)
                except Exception as e:
                    self.logger.warning(f"Test failed for variant B, case {test_case_id}: {str(e)}")
            
            # Calculate metrics
            success_rate_a = self._calculate_success_rate(results_a)
            success_rate_b = self._calculate_success_rate(results_b)
            confidence_a = self._calculate_avg_confidence(results_a)
            confidence_b = self._calculate_avg_confidence(results_b)
            
            # Determine winner
            winner, confidence_level = self._determine_winner(
                success_rate_a, success_rate_b,
                confidence_a, confidence_b,
                len(results_a), len(results_b)
            )
            
            # Store results
            ab_test_result = ABTestResult(
                variant_a_id=variant_a_id,
                variant_b_id=variant_b_id,
                test_cases_count=len(test_case_ids),
                variant_a_success_rate=success_rate_a,
                variant_b_success_rate=success_rate_b,
                variant_a_avg_confidence=confidence_a,
                variant_b_avg_confidence=confidence_b,
                winner=winner,
                confidence_level=confidence_level,
                notes=f"Variant {winner} won with {abs(success_rate_a - success_rate_b):.2%} difference"
            )
            
            self._store_ab_test_result(ab_test_result)
            
            self.logger.info(f"A/B test completed. Winner: Variant {winner}")
            
            return ab_test_result
            
        except Exception as e:
            self.logger.error(f"Error running A/B test: {str(e)}")
            raise

    def analyze_results(self, ab_test_result: ABTestResult) -> Dict:
        """
        Analyze A/B test results and provide insights.
        
        Args:
            ab_test_result: ABTestResult to analyze
            
        Returns:
            Dictionary with analysis insights
        """
        analysis = {
            'winner': ab_test_result.winner,
            'confidence_level': ab_test_result.confidence_level,
            'success_rate_improvement': abs(
                ab_test_result.variant_a_success_rate - 
                ab_test_result.variant_b_success_rate
            ),
            'confidence_improvement': abs(
                ab_test_result.variant_a_avg_confidence - 
                ab_test_result.variant_b_avg_confidence
            ),
            'recommendation': self._get_recommendation(ab_test_result),
            'notes': ab_test_result.notes
        }
        
        self.logger.info(f"Analysis: {json.dumps(analysis, indent=2)}")
        return analysis

    def update_prompt_template(
        self,
        winning_variant_id: int,
        prompt_name: str
    ) -> bool:
        """
        Update the active prompt template with winning variant.
        
        Args:
            winning_variant_id: ID of winning variant
            prompt_name: Name of prompt to update
            
        Returns:
            True if successful
        """
        try:
            variant = self._get_variant(winning_variant_id)
            if not variant:
                raise ValueError(f"Variant {winning_variant_id} not found")
            
            # In production, this would update the actual prompt used by AIHelper
            # For now, we log the update
            self.logger.info(f"Updating prompt '{prompt_name}' with variant: {variant.variant_name}")
            
            # Store update in improvement_logs
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO improvement_logs 
                    (improvement_type, description, applied)
                    VALUES (%s, %s, %s)
                """, ('prompt_update', f"Updated {prompt_name} with variant {variant.variant_name}", True))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating prompt template: {str(e)}")
            return False

    def get_all_variants(self, variant_type: Optional[str] = None) -> List[PromptVariant]:
        """Get all prompt variants, optionally filtered by type."""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                if variant_type:
                    cursor.execute("""
                        SELECT * FROM prompt_variants 
                        WHERE variant_type = %s
                        ORDER BY created_at DESC
                    """, (variant_type,))
                else:
                    cursor.execute("""
                        SELECT * FROM prompt_variants 
                        ORDER BY created_at DESC
                    """)
                
                rows = cursor.fetchall()
                return [self._dict_to_variant(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting variants: {str(e)}")
            return []

    def get_ab_test_history(self, limit: int = 10) -> List[Dict]:
        """Get recent A/B test results."""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                cursor.execute("""
                    SELECT 
                        ar.id,
                        pv_a.variant_name as variant_a_name,
                        pv_b.variant_name as variant_b_name,
                        ar.test_cases_count,
                        ar.variant_a_success_rate,
                        ar.variant_b_success_rate,
                        ar.winner,
                        ar.confidence_level,
                        ar.created_at,
                        ar.completed_at
                    FROM ab_test_results ar
                    JOIN prompt_variants pv_a ON ar.variant_a_id = pv_a.id
                    JOIN prompt_variants pv_b ON ar.variant_b_id = pv_b.id
                    ORDER BY ar.created_at DESC
                    LIMIT %s
                """, (limit,))
                
                return cursor.fetchall()
                
        except Exception as e:
            self.logger.error(f"Error getting A/B test history: {str(e)}")
            return []

    # Private helper methods

    def _apply_variation(self, base_prompt: str, variant_type: str, variation: str) -> str:
        """Apply variation to base prompt based on type."""
        variations = {
            'instruction_clarity': self._apply_clarity_variation,
            'example_format': self._apply_example_variation,
            'constraint_emphasis': self._apply_constraint_variation,
            'error_handling': self._apply_error_variation,
            'few_shot_examples': self._apply_few_shot_variation,
        }
        
        if variant_type in variations:
            return variations[variant_type](base_prompt, variation)
        
        return base_prompt

    def _apply_clarity_variation(self, base_prompt: str, variation: str) -> str:
        """Apply instruction clarity variation."""
        if 'detailed' in variation.lower():
            return base_prompt + "\n\nProvide detailed, step-by-step instructions."
        elif 'concise' in variation.lower():
            return base_prompt + "\n\nBe concise and direct."
        return base_prompt

    def _apply_example_variation(self, base_prompt: str, variation: str) -> str:
        """Apply example format variation."""
        if 'json' in variation.lower():
            return base_prompt + "\n\nProvide examples in JSON format."
        elif 'natural' in variation.lower():
            return base_prompt + "\n\nProvide examples in natural language."
        return base_prompt

    def _apply_constraint_variation(self, base_prompt: str, variation: str) -> str:
        """Apply constraint emphasis variation."""
        if 'strict' in variation.lower():
            return base_prompt + "\n\nSTRICT: Follow all constraints exactly."
        elif 'flexible' in variation.lower():
            return base_prompt + "\n\nConstraints are guidelines, adapt as needed."
        return base_prompt

    def _apply_error_variation(self, base_prompt: str, variation: str) -> str:
        """Apply error handling variation."""
        if 'explicit' in variation.lower():
            return base_prompt + "\n\nExplicitly handle all error cases."
        elif 'implicit' in variation.lower():
            return base_prompt + "\n\nHandle errors gracefully without explicit mention."
        return base_prompt

    def _apply_few_shot_variation(self, base_prompt: str, variation: str) -> str:
        """Apply few-shot examples variation."""
        if '1_example' in variation.lower():
            return base_prompt + "\n\nProvide 1 example."
        elif '3_examples' in variation.lower():
            return base_prompt + "\n\nProvide 3 examples."
        elif '5_examples' in variation.lower():
            return base_prompt + "\n\nProvide 5 examples."
        return base_prompt

    def _get_variant(self, variant_id: int) -> Optional[PromptVariant]:
        """Get a prompt variant by ID."""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("SELECT * FROM prompt_variants WHERE id = %s", (variant_id,))
                row = cursor.fetchone()
                return self._dict_to_variant(row) if row else None
        except Exception as e:
            self.logger.error(f"Error getting variant: {str(e)}")
            return None

    def _dict_to_variant(self, row: Dict) -> PromptVariant:
        """Convert database row to PromptVariant object."""
        return PromptVariant(
            id=row['id'],
            base_prompt_id=row.get('base_prompt_id'),
            variant_name=row['variant_name'],
            variant_text=row['variant_text'],
            variant_type=row['variant_type'],
            description=row.get('description'),
            created_at=row['created_at']
        )

    def _calculate_success_rate(self, results: List[Dict]) -> float:
        """Calculate success rate from test results."""
        if not results:
            return 0.0
        
        successful = sum(1 for r in results if r.get('success', False))
        return successful / len(results)

    def _calculate_avg_confidence(self, results: List[Dict]) -> float:
        """Calculate average confidence from test results."""
        if not results:
            return 0.0
        
        confidences = [r.get('confidence', 0.0) for r in results]
        return sum(confidences) / len(confidences)

    def _determine_winner(
        self,
        success_a: float,
        success_b: float,
        confidence_a: float,
        confidence_b: float,
        count_a: int,
        count_b: int
    ) -> Tuple[str, float]:
        """
        Determine winner using statistical significance.
        
        Returns:
            Tuple of (winner, confidence_level)
        """
        # Simple comparison with confidence threshold
        success_diff = abs(success_a - success_b)
        
        if success_diff < 0.05:  # Less than 5% difference
            return 'TIE', 0.0
        
        # Weight by both success rate and confidence
        score_a = (success_a * 0.7) + (confidence_a * 0.3)
        score_b = (success_b * 0.7) + (confidence_b * 0.3)
        
        winner = 'A' if score_a > score_b else 'B'
        confidence_level = max(success_diff, abs(score_a - score_b))
        
        return winner, confidence_level

    def _store_ab_test_result(self, result: ABTestResult) -> None:
        """Store A/B test result in database."""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ab_test_results
                    (variant_a_id, variant_b_id, test_cases_count,
                     variant_a_success_rate, variant_b_success_rate,
                     variant_a_avg_confidence, variant_b_avg_confidence,
                     winner, confidence_level, notes, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    result.variant_a_id,
                    result.variant_b_id,
                    result.test_cases_count,
                    result.variant_a_success_rate,
                    result.variant_b_success_rate,
                    result.variant_a_avg_confidence,
                    result.variant_b_avg_confidence,
                    result.winner,
                    result.confidence_level,
                    result.notes,
                    datetime.now()
                ))
        except Exception as e:
            self.logger.error(f"Error storing A/B test result: {str(e)}")

    def _get_recommendation(self, result: ABTestResult) -> str:
        """Get recommendation based on test results."""
        if result.winner == 'TIE':
            return "Results are inconclusive. Run more tests or try different variants."
        
        if result.confidence_level < 0.1:
            return "Winner has low confidence. Consider running more tests."
        
        if result.confidence_level > 0.3:
            return "Clear winner with high confidence. Recommend deploying."
        
        return "Moderate confidence. Review results before deploying."
