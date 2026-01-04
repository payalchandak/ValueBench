"""
Base embedding store with shared API calls, similarity math, and caching.

This module provides an abstract base class for embedding stores, handling:
- OpenRouter API calls for generating embeddings
- Cosine similarity calculations (single and batch)
- Loading and saving embeddings with caching
- Matrix caching for efficient batch similarity searches
"""

import json
import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class BaseEmbeddingStore(ABC):
    """
    Abstract base class for embedding stores.
    
    Provides shared functionality for:
    - Generating embeddings via OpenRouter API
    - Computing cosine similarity (single pair and batch)
    - Loading/saving embeddings with in-memory caching
    - Matrix-based batch similarity searches
    
    Subclasses must implement:
    - get_embedding_key(): Define the key format for stored embeddings
    - get_text_to_embed(): Define what text to embed from an item
    """
    
    # Available embedding models on OpenRouter
    EMBEDDING_MODELS = {
        'small': 'openai/text-embedding-3-small',  # 512 dimensions, cost-effective
        'large': 'openai/text-embedding-3-large',  # 3072 dimensions, higher quality
    }
    
    def __init__(
        self,
        embeddings_dir: str,
        embeddings_filename: str,
        model_size: str = 'small',
        api_key: Optional[str] = None
    ):
        """
        Initialize the base embedding store.
        
        Args:
            embeddings_dir: Directory containing embedding files
            embeddings_filename: Name of the embeddings JSON file
            model_size: 'small' or 'large' for embedding model
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
        """
        self.embeddings_dir = Path(embeddings_dir)
        self.embeddings_file = self.embeddings_dir / embeddings_filename
        self.model = self.EMBEDDING_MODELS.get(model_size, self.EMBEDDING_MODELS['small'])
        self.model_size = model_size
        
        # API configuration (lazy initialization - only needed for embedding generation)
        self._api_key = api_key
        self._api_url = "https://openrouter.ai/api/v1/embeddings"
        
        # Caching
        self._cache: Optional[Dict[str, Any]] = None
        self._matrix_cache: Optional[np.ndarray] = None
        self._keys_cache: Optional[List[str]] = None
    
    @property
    def api_key(self) -> str:
        """Get API key, raising error if not available."""
        if self._api_key is None:
            self._api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not self._api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter."
            )
        return self._api_key
    
    @property
    def _headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://github.com/valuebench',
            'X-Title': 'ValueBench Embedding Store'
        }
    
    # -------------------------------------------------------------------------
    # Abstract methods - must be implemented by subclasses
    # -------------------------------------------------------------------------
    
    @abstractmethod
    def get_embedding_key(self, item: Any) -> str:
        """
        Get the unique key for storing an item's embedding.
        
        Args:
            item: The item to generate a key for (could be a dict, object, etc.)
            
        Returns:
            Unique string key for the embedding
        """
        pass
    
    @abstractmethod
    def get_text_to_embed(self, item: Any) -> str:
        """
        Get the text content to embed from an item.
        
        Args:
            item: The item to extract text from
            
        Returns:
            Text string to embed
        """
        pass
    
    # -------------------------------------------------------------------------
    # API methods - generate embeddings via OpenRouter
    # -------------------------------------------------------------------------
    
    def embed_texts(self, texts: List[str], timeout: int = 30) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using OpenRouter API.
        
        Args:
            texts: List of text strings to embed
            timeout: Request timeout in seconds
            
        Returns:
            List of embedding vectors
            
        Raises:
            ValueError: If API returns an error or unexpected response
            requests.exceptions.RequestException: If request fails
        """
        if not texts:
            return []
        
        payload = {
            'model': self.model,
            'input': texts
        }
        
        response = requests.post(
            self._api_url,
            headers=self._headers,
            json=payload,
            timeout=timeout
        )
        
        if response.status_code != 200:
            # Parse error details from response
            err_detail: Optional[str] = None
            try:
                err_json = response.json()
                if isinstance(err_json, dict):
                    err_detail = (
                        err_json.get("error")
                        or err_json.get("message")
                        or err_json.get("detail")
                    )
                    if isinstance(err_detail, dict):
                        err_detail = json.dumps(err_detail, ensure_ascii=False)
            except ValueError:
                pass
            
            error_msg = err_detail if err_detail else response.text
            raise ValueError(f"API Error {response.status_code}: {error_msg}")
        
        # Parse and validate response
        try:
            data = response.json()
        except ValueError:
            raise ValueError(f"API returned non-JSON response: {response.text}")
        
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected API response format: expected dict, got {type(data).__name__}")
        
        data_items = data.get("data")
        if not isinstance(data_items, list):
            maybe_error = data.get("error") or data.get("message") or data
            raise ValueError(f"Unexpected API response structure: {maybe_error}")
        
        # Extract embeddings by index
        embeddings_by_index: Dict[int, List[float]] = {}
        for item in data_items:
            if not isinstance(item, dict):
                raise ValueError(f"Unexpected item in 'data': expected dict, got {type(item).__name__}")
            
            idx = item.get("index")
            emb = item.get("embedding")
            
            if not isinstance(idx, int):
                raise ValueError(f"Missing/invalid 'index' in embedding item: {item}")
            if not isinstance(emb, list) or not all(isinstance(x, (int, float)) for x in emb):
                raise ValueError(f"Missing/invalid 'embedding' vector at index {idx}")
            
            embeddings_by_index[idx] = emb
        
        if len(embeddings_by_index) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: got {len(embeddings_by_index)} for {len(texts)} inputs"
            )
        
        # Return embeddings in order
        return [embeddings_by_index[i] for i in sorted(embeddings_by_index)]
    
    def embed_text(self, text: str, timeout: int = 30) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string to embed
            timeout: Request timeout in seconds
            
        Returns:
            Embedding vector
        """
        return self.embed_texts([text], timeout=timeout)[0]
    
    # -------------------------------------------------------------------------
    # Similarity methods
    # -------------------------------------------------------------------------
    
    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """
        Calculate cosine similarity between two embedding vectors.
        
        Args:
            v1: First embedding vector
            v2: Second embedding vector
            
        Returns:
            Cosine similarity score (0-1), or 0.0 if either vector is zero
        """
        e1 = np.array(v1)
        e2 = np.array(v2)
        
        dot_product = np.dot(e1, e2)
        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)
        
        # Prevent division by zero for zero vectors
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def batch_similarities(
        self,
        query: List[float],
        top_k: Optional[int] = None
    ) -> List[Tuple[str, float]]:
        """
        Compute similarity between a query embedding and all stored embeddings.
        
        Uses cached numpy matrix for efficient vectorized computation.
        
        Args:
            query: Query embedding vector
            top_k: Number of top results to return (None for all)
            
        Returns:
            List of (key, similarity) tuples, sorted by similarity descending
        """
        # Ensure matrix cache is populated
        matrix, keys = self.get_all_embeddings_matrix()
        
        if matrix.size == 0:
            return []
        
        # Vectorized cosine similarity
        query_vec = np.array(query, dtype=np.float64)
        query_norm = np.linalg.norm(query_vec)
        
        if query_norm == 0.0:
            return [(k, 0.0) for k in keys]
        
        # Normalize query
        query_normalized = query_vec / query_norm
        
        # Compute norms for all embeddings
        matrix_float = matrix.astype(np.float64)
        norms = np.linalg.norm(matrix_float, axis=1)
        
        # Create mask for zero-norm vectors
        zero_mask = norms == 0.0
        
        # Avoid division by zero by setting zero norms to 1 (result will be zeroed later)
        safe_norms = np.where(zero_mask, 1.0, norms)
        
        # Normalize matrix rows
        matrix_normalized = matrix_float / safe_norms[:, np.newaxis]
        
        # Compute all similarities at once
        # Note: We suppress floating point warnings here as intermediate computations
        # may trigger them even when final results are valid and finite
        with np.errstate(divide='ignore', over='ignore', invalid='ignore'):
            similarities = matrix_normalized @ query_normalized
        
        # Zero out similarities for zero-norm vectors
        similarities = np.where(zero_mask, 0.0, similarities)
        
        # Handle any NaN values that might have slipped through
        similarities = np.nan_to_num(similarities, nan=0.0, posinf=1.0, neginf=-1.0)
        
        # Create sorted results
        results = [(keys[i], float(similarities[i])) for i in range(len(keys))]
        results.sort(key=lambda x: x[1], reverse=True)
        
        if top_k is not None:
            return results[:top_k]
        return results
    
    # -------------------------------------------------------------------------
    # Loading and saving methods
    # -------------------------------------------------------------------------
    
    def load_embeddings(self, reload: bool = False) -> Dict[str, Any]:
        """
        Load all embeddings from disk with caching.
        
        Args:
            reload: Force reload from disk even if cached
            
        Returns:
            Dictionary with embeddings and metadata
        """
        if self._cache is not None and not reload:
            return self._cache
        
        if not self.embeddings_file.exists():
            # Return empty structure if file doesn't exist
            return {'metadata': {}, 'embeddings': {}}
        
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self._cache = data
        # Invalidate matrix cache when data is reloaded
        self._matrix_cache = None
        self._keys_cache = None
        
        return data
    
    def save_embeddings(self, data: Dict[str, Any]) -> None:
        """
        Save embeddings to disk with atomic write and backup.
        
        Args:
            data: Dictionary with embeddings and metadata to save
        """
        # Ensure directory exists
        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        
        # Create backup if file exists
        if self.embeddings_file.exists():
            backup_file = self.embeddings_file.with_suffix('.json.bak')
            shutil.copy2(self.embeddings_file, backup_file)
        
        # Write to temp file first (atomic write)
        temp_file = self.embeddings_file.with_suffix('.json.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Move temp to final location
        temp_file.replace(self.embeddings_file)
        
        # Update cache
        self._cache = data
        # Invalidate matrix cache
        self._matrix_cache = None
        self._keys_cache = None
    
    def get_all_embeddings_matrix(self) -> Tuple[np.ndarray, List[str]]:
        """
        Get all embeddings as a numpy matrix with caching.
        
        Returns:
            Tuple of (embeddings_matrix, list of keys)
        """
        if self._matrix_cache is not None and self._keys_cache is not None:
            return self._matrix_cache, self._keys_cache
        
        data = self.load_embeddings()
        embeddings_dict = data.get('embeddings', {})
        
        if not embeddings_dict:
            return np.array([]), []
        
        keys = list(embeddings_dict.keys())
        embeddings = []
        
        for k in keys:
            emb_data = embeddings_dict[k]
            # Handle both dict format (with 'embedding' key) and direct list format
            if isinstance(emb_data, dict):
                embeddings.append(emb_data['embedding'])
            else:
                embeddings.append(emb_data)
        
        self._matrix_cache = np.array(embeddings)
        self._keys_cache = keys
        
        return self._matrix_cache, self._keys_cache
    
    def _has_embeddings(self) -> bool:
        """Check if any embeddings exist in the store."""
        data = self.load_embeddings()
        return bool(data.get('embeddings'))
    
    def get_embedding_by_key(self, key: str) -> Optional[List[float]]:
        """
        Get embedding vector for a specific key.
        
        Args:
            key: The embedding key
            
        Returns:
            Embedding vector or None if not found
        """
        data = self.load_embeddings()
        emb_data = data.get('embeddings', {}).get(key)
        
        if emb_data is None:
            return None
        
        # Handle both dict format (with 'embedding' key) and direct list format
        if isinstance(emb_data, dict):
            return emb_data.get('embedding')
        return emb_data
    
    def invalidate_cache(self) -> None:
        """Clear all caches, forcing reload on next access."""
        self._cache = None
        self._matrix_cache = None
        self._keys_cache = None
    
    # -------------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------------
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about stored embeddings.
        
        Returns:
            Metadata dictionary
        """
        data = self.load_embeddings()
        return data.get('metadata', {})
    
    def count_embeddings(self) -> int:
        """
        Get count of stored embeddings.
        
        Returns:
            Number of embeddings
        """
        data = self.load_embeddings()
        return len(data.get('embeddings', {}))

