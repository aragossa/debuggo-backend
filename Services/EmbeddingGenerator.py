"""
EmbeddingGenerator Service

Generates embeddings for patterns, selectors, API flows, and error resolutions
using Gemini's embedding API. These embeddings are used for similarity search
and few-shot learning in the Phase 2 learning system.

Embeddings are 1536-dimensional vectors that capture semantic meaning.
"""

import json
import logging
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding generation"""
    text: str
    embedding: List[float]
    model: str
    created_at: datetime


class EmbeddingGenerator:
    """
    Generates embeddings for various pattern types using Gemini's embedding API.
    
    Supports:
    - Selectors (XPath/CSS with context)
    - API flows (sequences of API calls)
    - Error resolutions (error + solution pairs)
    - UI components (component type + interaction)
    - Test cases (full test description)
    """
    
    def __init__(self):
        """Initialize embedding generator with Gemini API"""
        self.model_name = "models/text-embedding-004"
        self.embedding_dimension = 1536
        logger.info(f"EmbeddingGenerator initialized with model: {self.model_name}")
    
    def embed_selector(self, selector: str, context: Optional[Dict[str, Any]] = None) -> EmbeddingResult:
        """
        Generate embedding for a selector (XPath or CSS).
        
        Args:
            selector: XPath or CSS selector string
            context: Optional context about the element (tag, attributes, purpose)
        
        Returns:
            EmbeddingResult with the embedding vector
        """
        # Build context string
        context_str = ""
        if context:
            if context.get('element_type'):
                context_str += f"Element type: {context['element_type']}. "
            if context.get('purpose'):
                context_str += f"Purpose: {context['purpose']}. "
            if context.get('attributes'):
                context_str += f"Attributes: {context['attributes']}. "
        
        text = f"Selector: {selector}. {context_str}".strip()
        return self._generate_embedding(text, "selector")
    
    def embed_api_flow(self, flow: Dict[str, Any]) -> EmbeddingResult:
        """
        Generate embedding for an API flow (sequence of API calls).
        
        Args:
            flow: Dictionary containing:
                - method: HTTP method (GET, POST, etc.)
                - endpoint: API endpoint
                - description: What the flow does
                - steps: List of steps in the flow
        
        Returns:
            EmbeddingResult with the embedding vector
        """
        text = f"""
API Flow: {flow.get('description', 'Unnamed flow')}
Method: {flow.get('method', 'GET')}
Endpoint: {flow.get('endpoint', 'Unknown')}
Steps: {len(flow.get('steps', []))} steps
Purpose: {flow.get('purpose', 'Unknown')}
        """.strip()
        
        return self._generate_embedding(text, "api_flow")
    
    def embed_error_resolution(self, error: str, resolution: str, context: Optional[str] = None) -> EmbeddingResult:
        """
        Generate embedding for an error resolution pattern.
        
        Args:
            error: The error message or error type
            resolution: How to resolve the error
            context: Optional context about when this error occurs
        
        Returns:
            EmbeddingResult with the embedding vector
        """
        text = f"""
Error: {error}
Resolution: {resolution}
        """
        if context:
            text += f"Context: {context}"
        
        return self._generate_embedding(text.strip(), "error_resolution")
    
    def embed_ui_component(self, component_type: str, interaction: str, context: Optional[str] = None) -> EmbeddingResult:
        """
        Generate embedding for a UI component interaction pattern.
        
        Args:
            component_type: Type of component (button, input, dropdown, etc.)
            interaction: How to interact with it (click, type, select, etc.)
            context: Optional context about the component
        
        Returns:
            EmbeddingResult with the embedding vector
        """
        text = f"""
UI Component: {component_type}
Interaction: {interaction}
        """
        if context:
            text += f"Context: {context}"
        
        return self._generate_embedding(text.strip(), "ui_component")
    
    def embed_test_case(self, test_case: Dict[str, Any]) -> EmbeddingResult:
        """
        Generate embedding for a complete test case.
        
        Args:
            test_case: Dictionary containing:
                - name: Test case name
                - description: Test description
                - steps: List of test steps
                - test_type: 'ui' or 'api'
        
        Returns:
            EmbeddingResult with the embedding vector
        """
        text = f"""
Test Case: {test_case.get('name', 'Unnamed')}
Type: {test_case.get('test_type', 'ui')}
Description: {test_case.get('description', 'No description')}
Steps: {len(test_case.get('steps', []))} steps
        """.strip()
        
        return self._generate_embedding(text, "test_case")
    
    def embed_text(self, text: str, pattern_type: str = "generic") -> EmbeddingResult:
        """
        Generate embedding for arbitrary text.
        
        Args:
            text: Text to embed
            pattern_type: Type of pattern (for logging)
        
        Returns:
            EmbeddingResult with the embedding vector
        """
        return self._generate_embedding(text, pattern_type)
    
    def _generate_embedding(self, text: str, pattern_type: str) -> EmbeddingResult:
        """
        Internal method to generate embedding using Gemini API.
        
        Args:
            text: Text to embed
            pattern_type: Type of pattern (for logging)
        
        Returns:
            EmbeddingResult with the embedding vector
        
        Raises:
            Exception: If embedding generation fails
        """
        try:
            # Use Gemini's embedding API
            response = genai.embed_content(
                model=self.model_name,
                content=text,
                task_type="SEMANTIC_SIMILARITY"
            )
            
            embedding = response['embedding']
            
            # Verify embedding dimension
            if len(embedding) != self.embedding_dimension:
                logger.warning(
                    f"Unexpected embedding dimension: {len(embedding)} "
                    f"(expected {self.embedding_dimension})"
                )
            
            logger.debug(
                f"Generated embedding for {pattern_type}: "
                f"{len(text)} chars → {len(embedding)} dimensions"
            )
            
            return EmbeddingResult(
                text=text,
                embedding=embedding,
                model=self.model_name,
                created_at=datetime.now()
            )
        
        except Exception as e:
            logger.error(f"Failed to generate embedding for {pattern_type}: {str(e)}")
            raise
    
    def batch_embed(self, texts: List[str], pattern_type: str = "generic") -> List[EmbeddingResult]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            pattern_type: Type of pattern (for logging)
        
        Returns:
            List of EmbeddingResult objects
        """
        results = []
        for i, text in enumerate(texts):
            try:
                result = self._generate_embedding(text, pattern_type)
                results.append(result)
                logger.debug(f"Embedded {i+1}/{len(texts)} texts")
            except Exception as e:
                logger.error(f"Failed to embed text {i+1}/{len(texts)}: {str(e)}")
                continue
        
        return results
    
    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
        
        Returns:
            Similarity score between -1 and 1 (1 = identical, 0 = orthogonal, -1 = opposite)
        """
        if len(embedding1) != len(embedding2):
            raise ValueError("Embeddings must have the same dimension")
        
        # Cosine similarity: (A · B) / (||A|| * ||B||)
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        
        norm1 = sum(a ** 2 for a in embedding1) ** 0.5
        norm2 = sum(b ** 2 for b in embedding2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        return similarity
    
    def find_most_similar(self, query_embedding: List[float], embeddings: List[List[float]], top_k: int = 5) -> List[tuple]:
        """
        Find the most similar embeddings to a query embedding.
        
        Args:
            query_embedding: Query embedding vector
            embeddings: List of embedding vectors to search
            top_k: Number of top results to return
        
        Returns:
            List of (index, similarity_score) tuples, sorted by similarity (highest first)
        """
        similarities = []
        for i, embedding in enumerate(embeddings):
            similarity = self.calculate_similarity(query_embedding, embedding)
            similarities.append((i, similarity))
        
        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]
