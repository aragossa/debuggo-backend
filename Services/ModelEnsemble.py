"""
Phase 4: Model Ensemble Service

Implements multi-model generation with consensus mechanisms.
Uses Gemini, Claude, and Deepseek for improved reliability.
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
class ModelResult:
    """Result from a single model"""
    model_name: str
    result: Dict
    confidence: float
    success: bool
    error: Optional[str] = None


@dataclass
class EnsembleComparison:
    """Comparison of multiple model results"""
    gemini_result: Optional[Dict]
    claude_result: Optional[Dict]
    deepseek_result: Optional[Dict]
    agreement_score: float
    consensus_result: Optional[Dict]
    selection_strategy: str


class ModelEnsemble:
    """
    Generates test steps using multiple AI models and selects best result.
    
    Responsibilities:
    - Generate with multiple models
    - Compare results
    - Calculate agreement scores
    - Select best result using various strategies
    """

    def __init__(self):
        self.system = System()
        self.logger = logger
        self.models = {
            'gemini': self._call_gemini,
            'claude': self._call_claude,
            'deepseek': self._call_deepseek,
        }

    def generate_with_all_models(
        self,
        prompt: str,
        context: Optional[Dict] = None
    ) -> List[ModelResult]:
        """
        Generate response from all available models.
        
        Args:
            prompt: The prompt to send to models
            context: Optional context information
            
        Returns:
            List of ModelResult objects
        """
        results = []
        
        for model_name, model_func in self.models.items():
            try:
                self.logger.info(f"Generating with {model_name}...")
                result = model_func(prompt, context)
                results.append(result)
            except Exception as e:
                self.logger.warning(f"Error generating with {model_name}: {str(e)}")
                results.append(ModelResult(
                    model_name=model_name,
                    result={},
                    confidence=0.0,
                    success=False,
                    error=str(e)
                ))
        
        return results

    def compare_results(self, results: List[ModelResult]) -> EnsembleComparison:
        """
        Compare results from multiple models.
        
        Args:
            results: List of ModelResult objects
            
        Returns:
            EnsembleComparison with analysis
        """
        # Extract successful results
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            self.logger.warning("No successful results from any model")
            return EnsembleComparison(
                gemini_result=None,
                claude_result=None,
                deepseek_result=None,
                agreement_score=0.0,
                consensus_result=None,
                selection_strategy='none'
            )
        
        # Calculate agreement score
        agreement_score = self._calculate_agreement(successful_results)
        
        # Extract individual results
        result_dict = {r.model_name: r.result for r in successful_results}
        
        return EnsembleComparison(
            gemini_result=result_dict.get('gemini'),
            claude_result=result_dict.get('claude'),
            deepseek_result=result_dict.get('deepseek'),
            agreement_score=agreement_score,
            consensus_result=None,  # Will be set by selection strategy
            selection_strategy='pending'
        )

    def select_best_result(
        self,
        results: List[ModelResult],
        strategy: str = 'consensus'
    ) -> Tuple[Dict, str, float]:
        """
        Select best result using specified strategy.
        
        Args:
            results: List of ModelResult objects
            strategy: Selection strategy ('voting', 'confidence', 'consensus', 'weighted')
            
        Returns:
            Tuple of (selected_result, strategy_used, confidence)
        """
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            self.logger.error("No successful results to select from")
            return {}, 'none', 0.0
        
        if strategy == 'voting':
            return self._select_by_voting(successful_results)
        elif strategy == 'confidence':
            return self._select_by_confidence(successful_results)
        elif strategy == 'consensus':
            return self._select_by_consensus(successful_results)
        elif strategy == 'weighted':
            return self._select_by_weighted(successful_results)
        else:
            # Default to confidence
            return self._select_by_confidence(successful_results)

    def calculate_agreement_score(self, results: List[ModelResult]) -> float:
        """
        Calculate how much models agree on the result.
        
        Args:
            results: List of ModelResult objects
            
        Returns:
            Agreement score 0.0-1.0
        """
        return self._calculate_agreement(results)

    def store_ensemble_result(
        self,
        test_case_id: int,
        step_number: int,
        results: List[ModelResult],
        selected_result: Dict,
        selection_strategy: str
    ) -> None:
        """
        Store ensemble results in database.
        
        Args:
            test_case_id: ID of test case
            step_number: Step number
            results: List of ModelResult objects
            selected_result: The selected result
            selection_strategy: Strategy used for selection
        """
        try:
            result_dict = {r.model_name: r.result for r in results if r.success}
            agreement_score = self._calculate_agreement(results)
            
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO model_ensemble_results
                    (test_case_id, step_number, gemini_result, claude_result, deepseek_result,
                     agreement_score, selected_result, selection_strategy)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    test_case_id,
                    step_number,
                    json.dumps(result_dict.get('gemini', {})),
                    json.dumps(result_dict.get('claude', {})),
                    json.dumps(result_dict.get('deepseek', {})),
                    agreement_score,
                    json.dumps(selected_result),
                    selection_strategy
                ))
                
                self.logger.info(f"Stored ensemble result for test {test_case_id}, step {step_number}")
                
        except Exception as e:
            self.logger.error(f"Error storing ensemble result: {str(e)}")

    def get_ensemble_statistics(self, limit: int = 100) -> Dict:
        """
        Get statistics about ensemble results.
        
        Args:
            limit: Number of recent results to analyze
            
        Returns:
            Dictionary with statistics
        """
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                cursor.execute("""
                    SELECT 
                        selection_strategy,
                        COUNT(*) as count,
                        AVG(agreement_score) as avg_agreement,
                        MIN(agreement_score) as min_agreement,
                        MAX(agreement_score) as max_agreement
                    FROM model_ensemble_results
                    ORDER BY id DESC
                    LIMIT %s
                    GROUP BY selection_strategy
                """, (limit,))
                
                stats = {
                    'total_results': 0,
                    'by_strategy': {},
                    'avg_agreement': 0.0
                }
                
                rows = cursor.fetchall()
                for row in rows:
                    stats['by_strategy'][row['selection_strategy']] = {
                        'count': row['count'],
                        'avg_agreement': row['avg_agreement'],
                        'min_agreement': row['min_agreement'],
                        'max_agreement': row['max_agreement']
                    }
                    stats['total_results'] += row['count']
                
                if stats['total_results'] > 0:
                    cursor.execute("""
                        SELECT AVG(agreement_score) as avg_agreement
                        FROM model_ensemble_results
                        ORDER BY id DESC
                        LIMIT %s
                    """, (limit,))
                    result = cursor.fetchone()
                    stats['avg_agreement'] = result['avg_agreement'] if result else 0.0
                
                return stats
                
        except Exception as e:
            self.logger.error(f"Error getting ensemble statistics: {str(e)}")
            return {}

    # Private helper methods

    def _call_gemini(self, prompt: str, context: Optional[Dict] = None) -> ModelResult:
        """Call Gemini API."""
        try:
            # This would be implemented with actual Gemini API call
            # For now, return placeholder
            self.logger.debug("Calling Gemini API")
            
            # Placeholder implementation
            result = {
                'model': 'gemini',
                'response': 'Gemini response',
                'confidence': 0.85
            }
            
            return ModelResult(
                model_name='gemini',
                result=result,
                confidence=0.85,
                success=True
            )
        except Exception as e:
            self.logger.error(f"Gemini API error: {str(e)}")
            return ModelResult(
                model_name='gemini',
                result={},
                confidence=0.0,
                success=False,
                error=str(e)
            )

    def _call_claude(self, prompt: str, context: Optional[Dict] = None) -> ModelResult:
        """Call Claude API."""
        try:
            # This would be implemented with actual Claude API call
            # For now, return placeholder
            self.logger.debug("Calling Claude API")
            
            # Placeholder implementation
            result = {
                'model': 'claude',
                'response': 'Claude response',
                'confidence': 0.82
            }
            
            return ModelResult(
                model_name='claude',
                result=result,
                confidence=0.82,
                success=True
            )
        except Exception as e:
            self.logger.error(f"Claude API error: {str(e)}")
            return ModelResult(
                model_name='claude',
                result={},
                confidence=0.0,
                success=False,
                error=str(e)
            )

    def _call_deepseek(self, prompt: str, context: Optional[Dict] = None) -> ModelResult:
        """Call Deepseek API."""
        try:
            # This would be implemented with actual Deepseek API call
            # For now, return placeholder
            self.logger.debug("Calling Deepseek API")
            
            # Placeholder implementation
            result = {
                'model': 'deepseek',
                'response': 'Deepseek response',
                'confidence': 0.80
            }
            
            return ModelResult(
                model_name='deepseek',
                result=result,
                confidence=0.80,
                success=True
            )
        except Exception as e:
            self.logger.error(f"Deepseek API error: {str(e)}")
            return ModelResult(
                model_name='deepseek',
                result={},
                confidence=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_agreement(self, results: List[ModelResult]) -> float:
        """
        Calculate agreement score between models.
        
        Simple approach: Compare JSON structures for similarity.
        """
        successful_results = [r for r in results if r.success]
        
        if len(successful_results) < 2:
            return 0.0 if len(successful_results) == 0 else 1.0
        
        # Compare results pairwise
        similarities = []
        for i in range(len(successful_results)):
            for j in range(i + 1, len(successful_results)):
                sim = self._calculate_similarity(
                    successful_results[i].result,
                    successful_results[j].result
                )
                similarities.append(sim)
        
        if not similarities:
            return 0.0
        
        return sum(similarities) / len(similarities)

    def _calculate_similarity(self, result1: Dict, result2: Dict) -> float:
        """
        Calculate similarity between two results.
        
        Returns score 0.0-1.0
        """
        if not result1 or not result2:
            return 0.0
        
        # Simple key overlap comparison
        keys1 = set(result1.keys())
        keys2 = set(result2.keys())
        
        if not keys1 or not keys2:
            return 0.0
        
        intersection = len(keys1 & keys2)
        union = len(keys1 | keys2)
        
        return intersection / union if union > 0 else 0.0

    def _select_by_voting(self, results: List[ModelResult]) -> Tuple[Dict, str, float]:
        """Select result by voting (most common)."""
        if not results:
            return {}, 'voting', 0.0
        
        # For simplicity, select highest confidence
        best = max(results, key=lambda r: r.confidence)
        agreement = self._calculate_agreement(results)
        
        return best.result, 'voting', agreement

    def _select_by_confidence(self, results: List[ModelResult]) -> Tuple[Dict, str, float]:
        """Select result with highest confidence."""
        if not results:
            return {}, 'confidence', 0.0
        
        best = max(results, key=lambda r: r.confidence)
        return best.result, 'confidence', best.confidence

    def _select_by_consensus(self, results: List[ModelResult]) -> Tuple[Dict, str, float]:
        """Select result if 2+ models agree."""
        if len(results) < 2:
            if results:
                return results[0].result, 'consensus', results[0].confidence
            return {}, 'consensus', 0.0
        
        # Check for agreement
        agreement = self._calculate_agreement(results)
        
        if agreement > 0.7:  # High agreement threshold
            # Return average of top 2 results
            sorted_results = sorted(results, key=lambda r: r.confidence, reverse=True)
            return sorted_results[0].result, 'consensus', agreement
        
        # No consensus, return highest confidence
        best = max(results, key=lambda r: r.confidence)
        return best.result, 'consensus', best.confidence

    def _select_by_weighted(self, results: List[ModelResult]) -> Tuple[Dict, str, float]:
        """Select result using weighted scoring."""
        if not results:
            return {}, 'weighted', 0.0
        
        # Weight by model performance history (would use stored metrics)
        weights = {
            'gemini': 0.4,
            'claude': 0.35,
            'deepseek': 0.25
        }
        
        best_score = -1
        best_result = None
        
        for result in results:
            weight = weights.get(result.model_name, 0.33)
            score = result.confidence * weight
            
            if score > best_score:
                best_score = score
                best_result = result
        
        if best_result:
            return best_result.result, 'weighted', best_result.confidence
        
        return {}, 'weighted', 0.0
