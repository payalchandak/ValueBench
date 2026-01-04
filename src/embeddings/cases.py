"""
Case embedding store for diversity gating during case generation.

This module provides CaseEmbeddingStore, a subclass of BaseEmbeddingStore
that handles embeddings for case vignettes and choices. It supports:
- Checking diversity of new cases against existing benchmark
- Adding new case embeddings after successful generation
- Finding similar cases for analysis
- Bootstrapping embeddings for all existing cases in data/cases/
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.embeddings.base import BaseEmbeddingStore


class CaseEmbeddingStore(BaseEmbeddingStore):
    """
    Embedding store for case vignettes and choices.
    
    Used primarily for the diversity gate during case generation to ensure
    newly generated cases are sufficiently different from existing ones.
    
    Only stores case_id and embedding vectors. All other metadata (seed context,
    vignette text, etc.) is stored in the case records at data/cases/.
    
    Storage format in case_embeddings.json:
    {
        "metadata": {
            "model": "openai/text-embedding-3-small",
            "total_embeddings": 105,
            "last_updated": "2025-01-03T12:00:00"
        },
        "embeddings": {
            "case_id_1": {
                "embedding": [0.1, 0.2, ...],
                "created_at": "2025-01-01T10:00:00"
            },
            ...
        }
    }
    """
    
    DEFAULT_SIMILARITY_THRESHOLD = 0.80
    
    def __init__(
        self,
        embeddings_dir: str = "data/embeddings",
        cases_dir: str = "data/cases",
        model_size: str = 'small',
        api_key: Optional[str] = None,
        include_statuses: Optional[List[str]] = None
    ):
        """
        Initialize the case embedding store.
        
        Args:
            embeddings_dir: Directory containing embedding files
            cases_dir: Directory containing case JSON files
            model_size: 'small' or 'large' for embedding model
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            include_statuses: List of status values to include in diversity checks
                            (e.g., ["completed"]). Defaults to ["completed"].
        """
        super().__init__(
            embeddings_dir=embeddings_dir,
            embeddings_filename="case_embeddings.json",
            model_size=model_size,
            api_key=api_key
        )
        self.cases_dir = Path(cases_dir)
        self.include_statuses = include_statuses if include_statuses is not None else ["completed"]
    
    # -------------------------------------------------------------------------
    # Static utility methods
    # -------------------------------------------------------------------------
    
    @staticmethod
    def case_to_text(vignette: str, choice_1: str, choice_2: str) -> str:
        """
        Convert case components to embeddable text.
        
        Args:
            vignette: The case vignette text
            choice_1: Text for first choice
            choice_2: Text for second choice
            
        Returns:
            Combined text suitable for embedding
        """
        return f"{vignette}\n\nChoice 1: {choice_1}\n\nChoice 2: {choice_2}"
    
    def get_embedding_key(self, item: Any) -> str:
        """
        Get the unique key for storing a case's embedding.
        
        Args:
            item: Case data - can be a dict, DraftCase, or BenchmarkCandidate
            
        Returns:
            Case ID string
        """
        if hasattr(item, 'case_id'):
            return item.case_id
        elif isinstance(item, dict):
            return item.get('case_id', '')
        else:
            raise ValueError(f"Cannot extract case_id from item of type {type(item).__name__}")
    
    def get_text_to_embed(self, item: Any) -> str:
        """
        Get the text content to embed from a case.
        
        Combines vignette and both choices into a single text for embedding.
        Handles both dict format (from JSON files) and Pydantic model format.
        
        Args:
            item: Case data with vignette and choices
            
        Returns:
            Combined text string: vignette + choice_1 + choice_2
        """
        # Extract vignette
        if hasattr(item, 'vignette'):
            vignette = item.vignette
        elif isinstance(item, dict):
            vignette = item.get('vignette', '')
        else:
            raise ValueError(f"Cannot extract vignette from item of type {type(item).__name__}")
        
        # Extract choice_1 text
        if hasattr(item, 'choice_1'):
            choice_1 = item.choice_1
            # Handle ChoiceWithValues objects that have a 'choice' field
            if hasattr(choice_1, 'choice'):
                choice_1 = choice_1.choice
        elif isinstance(item, dict):
            choice_1 = item.get('choice_1', '')
            # Handle nested dict format from JSON
            if isinstance(choice_1, dict):
                choice_1 = choice_1.get('choice', '')
        else:
            choice_1 = ''
        
        # Extract choice_2 text
        if hasattr(item, 'choice_2'):
            choice_2 = item.choice_2
            # Handle ChoiceWithValues objects that have a 'choice' field
            if hasattr(choice_2, 'choice'):
                choice_2 = choice_2.choice
        elif isinstance(item, dict):
            choice_2 = item.get('choice_2', '')
            # Handle nested dict format from JSON
            if isinstance(choice_2, dict):
                choice_2 = choice_2.get('choice', '')
        else:
            choice_2 = ''
        
        return f"{vignette}\n\nChoice 1: {choice_1}\n\nChoice 2: {choice_2}"
    
    def check_diversity(
        self,
        draft: Any,
        threshold: Optional[float] = None
    ) -> Tuple[bool, Optional[str], float]:
        """
        Check if a draft case is sufficiently different from existing cases.
        
        This is the core diversity gate method used during case generation.
        Returns early with (True, None, 0.0) if the benchmark is empty.
        
        Args:
            draft: Draft case with vignette and choices
            threshold: Similarity threshold (0-1). Cases with similarity >= threshold
                      are considered too similar. Defaults to 0.80.
            
        Returns:
            Tuple of (is_diverse, similar_case_id, max_similarity):
            - is_diverse: True if draft passes diversity check
            - similar_case_id: ID of most similar case if too similar, else None
            - max_similarity: Similarity score to most similar case
        """
        if threshold is None:
            threshold = self.DEFAULT_SIMILARITY_THRESHOLD
        
        # Empty benchmark = always diverse
        if not self._has_embeddings():
            return (True, None, 0.0)
        
        # Generate embedding for the draft
        try:
            text_to_embed = self.get_text_to_embed(draft)
            query_embedding = self.embed_text(text_to_embed)
        except Exception as e:
            # Log warning and proceed (don't block generation on API failure)
            import logging
            logging.warning(f"[DIVERSITY] Failed to generate embedding: {e}. Passing diversity check.")
            return (True, None, 0.0)
        
        # Find most similar existing case
        similarities = self.batch_similarities(query_embedding, top_k=1)
        
        if not similarities:
            return (True, None, 0.0)
        
        most_similar_id, max_similarity = similarities[0]
        
        if max_similarity >= threshold:
            return (False, most_similar_id, max_similarity)
        
        return (True, None, max_similarity)
    
    def add_case(self, case_id: str, case_data: Any) -> None:
        """
        Add a new case embedding after successful generation.
        
        Only stores case_id and embedding. All other metadata (seed context, etc.)
        is already stored in the case record at data/cases/.
        
        Args:
            case_id: Unique case identifier
            case_data: Case data with vignette and choices
        """
        # Generate embedding
        text_to_embed = self.get_text_to_embed(case_data)
        embedding = self.embed_text(text_to_embed)
        
        # Load existing data
        data = self.load_embeddings()
        
        # Initialize structure if needed
        if 'embeddings' not in data:
            data['embeddings'] = {}
        if 'metadata' not in data:
            data['metadata'] = {}
        
        # Add embedding (metadata lives in data/cases/)
        data['embeddings'][case_id] = {
            'embedding': embedding,
            'created_at': datetime.now().isoformat()
        }
        
        # Update metadata
        data['metadata']['model'] = self.model
        data['metadata']['total_embeddings'] = len(data['embeddings'])
        data['metadata']['last_updated'] = datetime.now().isoformat()
        
        # Save
        self.save_embeddings(data)
    
    def find_similar_cases(
        self,
        case_id: str,
        top_k: int = 5,
        exclude_self: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find cases most similar to a given case.
        
        Args:
            case_id: ID of the case to find similar cases for
            top_k: Number of similar cases to return
            exclude_self: Whether to exclude the query case from results
            
        Returns:
            List of dicts with case_id and similarity
        """
        # Get the query case's embedding
        query_embedding = self.get_embedding_by_key(case_id)
        
        if query_embedding is None:
            raise ValueError(f"No embedding found for case {case_id}")
        
        # Get all similarities
        all_similarities = self.batch_similarities(query_embedding)
        
        # Filter and format results
        results = []
        for similar_id, similarity in all_similarities:
            if exclude_self and similar_id == case_id:
                continue
            
            results.append({
                'case_id': similar_id,
                'similarity': similarity
            })
            
            if len(results) >= top_k:
                break
        
        return results
    
    def find_similar_to_text(
        self,
        text: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find cases most similar to arbitrary text.
        
        Useful for finding cases similar to a proposed vignette without
        it being in the database yet.
        
        Args:
            text: Text to find similar cases for
            top_k: Number of similar cases to return
            
        Returns:
            List of dicts with case_id and similarity
        """
        # Generate embedding for the text
        query_embedding = self.embed_text(text)
        
        # Get all similarities
        all_similarities = self.batch_similarities(query_embedding, top_k=top_k)
        
        # Format results
        results = []
        for similar_id, similarity in all_similarities:
            results.append({
                'case_id': similar_id,
                'similarity': similarity
            })
        
        return results
    
    def remove_case(self, case_id: str) -> bool:
        """
        Remove a case embedding from the store.
        
        Args:
            case_id: ID of the case to remove
            
        Returns:
            True if case was removed, False if not found
        """
        data = self.load_embeddings()
        embeddings = data.get('embeddings', {})
        
        if case_id not in embeddings:
            return False
        
        del embeddings[case_id]
        
        # Update metadata
        data['metadata']['total_embeddings'] = len(embeddings)
        data['metadata']['last_updated'] = datetime.now().isoformat()
        
        self.save_embeddings(data)
        return True
    
    # -------------------------------------------------------------------------
    # Bulk loading and embedding generation methods
    # -------------------------------------------------------------------------
    
    def load_all_cases(
        self,
        include_statuses: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Load cases from the cases directory (data/cases/) filtered by status.
        
        Parses case JSON files and extracts the final refinement data
        with vignette and choices. Handles both string and dict formats
        for choice_1/choice_2. By default, only loads active cases (completed status)
        to ensure the diversity gate protects final benchmark quality.
        
        Args:
            include_statuses: List of status values to include (e.g., ["completed", "draft"]).
                            Defaults to the instance's include_statuses setting.
                            Pass an empty list to load all cases regardless of status.
        
        Returns:
            List of dictionaries with case_id, vignette, choice_1, choice_2, and seed info
        """
        # Default to instance setting for diversity gating
        if include_statuses is None:
            include_statuses = self.include_statuses
        
        cases = []
        
        if not self.cases_dir.exists():
            return cases
        
        for filepath in self.cases_dir.glob("case_*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                # Filter by status if include_statuses is specified
                if include_statuses:
                    case_status = case_data.get('status', '')
                    if case_status not in include_statuses:
                        continue
                
                # Get the final refinement iteration (last in refinement_history)
                refinement_history = case_data.get('refinement_history', [])
                if not refinement_history:
                    continue
                
                final_data = refinement_history[-1].get('data', {})
                
                # Extract vignette
                vignette = final_data.get('vignette', '')
                if not vignette:
                    continue
                
                # Extract choice_1 (handle both string and dict formats)
                choice_1 = final_data.get('choice_1', '')
                if isinstance(choice_1, dict):
                    choice_1 = choice_1.get('choice', '')
                
                # Extract choice_2 (handle both string and dict formats)
                choice_2 = final_data.get('choice_2', '')
                if isinstance(choice_2, dict):
                    choice_2 = choice_2.get('choice', '')
                
                # Get seed information
                seed = case_data.get('seed', {})
                
                cases.append({
                    'case_id': case_data.get('case_id', ''),
                    'vignette': vignette,
                    'choice_1': choice_1,
                    'choice_2': choice_2,
                    'seed': seed
                })
                
            except (json.JSONDecodeError, KeyError) as e:
                # Skip malformed files
                import logging
                logging.warning(f"Skipping malformed case file {filepath}: {e}")
                continue
        
        return cases
    
    def generate_all_embeddings(
        self,
        force: bool = False,
        include_statuses: Optional[List[str]] = None
    ) -> int:
        """
        Generate embeddings for all cases in the cases directory.
        
        This is used to bootstrap the embedding store from existing cases.
        By default, skips cases that already have embeddings unless force=True.
        Only generates embeddings for active cases (completed status) by default.
        
        Args:
            force: If True, regenerate embeddings even for cases that already exist
            include_statuses: List of status values to include (e.g., ["completed"]).
                            Defaults to the instance's include_statuses setting.
            
        Returns:
            Number of new embeddings generated
        """
        # Use instance setting if not explicitly provided
        if include_statuses is None:
            include_statuses = self.include_statuses
        cases = self.load_all_cases(include_statuses=include_statuses)
        
        if not cases:
            return 0
        
        # Load existing embeddings (unless forcing full regeneration)
        if force:
            data = {'metadata': {}, 'embeddings': {}}
        else:
            data = self.load_embeddings()
        
        existing_embeddings = data.get('embeddings', {})
        
        new_count = 0
        
        for case in cases:
            case_id = case['case_id']
            
            # Skip if already embedded (unless force=True)
            if case_id in existing_embeddings and not force:
                continue
            
            # Generate embedding
            try:
                text = self.case_to_text(case['vignette'], case['choice_1'], case['choice_2'])
                embedding = self.embed_text(text)
            except Exception as e:
                import logging
                logging.warning(f"Failed to generate embedding for case {case_id}: {e}")
                continue
            
            # Store embedding (metadata lives in data/cases/)
            if 'embeddings' not in data:
                data['embeddings'] = {}
            
            data['embeddings'][case_id] = {
                'embedding': embedding,
                'created_at': datetime.now().isoformat()
            }
            
            new_count += 1
        
        # Update metadata
        data['metadata'] = {
            'model': self.model,
            'total_embeddings': len(data.get('embeddings', {})),
            'last_updated': datetime.now().isoformat()
        }
        
        # Save
        self.save_embeddings(data)
        
        return new_count
    
    def prune_inactive_embeddings(
        self,
        include_statuses: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Remove embeddings for cases that are no longer active.
        
        This keeps the embedding store in sync with active cases by removing
        embeddings for cases that have been deprecated, failed, or deleted.
        An embedding is considered "orphaned" if:
        - The case file no longer exists in the cases directory
        - The case exists but has a status not in include_statuses
        
        Args:
            include_statuses: List of status values considered "active".
                            Defaults to ["completed"] to match load_all_cases() behavior.
        
        Returns:
            Dictionary with pruning statistics:
            - pruned_count: Number of embeddings removed
            - pruned_ids: List of case IDs that were removed
            - reason: Mapping of case_id to reason for removal ('deleted' or 'status:<status>')
            - remaining_count: Number of embeddings still in store
        """
        if include_statuses is None:
            include_statuses = ["completed"]
        
        # Load existing embeddings
        data = self.load_embeddings()
        embeddings = data.get('embeddings', {})
        
        if not embeddings:
            return {
                'pruned_count': 0,
                'pruned_ids': [],
                'reason': {},
                'remaining_count': 0
            }
        
        # Build a mapping of case_id -> status for all cases in the directory
        case_status_map: Dict[str, str] = {}
        if self.cases_dir.exists():
            for filepath in self.cases_dir.glob("case_*.json"):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        case_data = json.load(f)
                    case_id = case_data.get('case_id', '')
                    status = case_data.get('status', '')
                    if case_id:
                        case_status_map[case_id] = status
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed files
                    continue
        
        # Identify embeddings to prune
        pruned_ids = []
        reasons = {}
        
        for case_id in list(embeddings.keys()):
            if case_id not in case_status_map:
                # Case file no longer exists
                pruned_ids.append(case_id)
                reasons[case_id] = 'deleted'
            elif case_status_map[case_id] not in include_statuses:
                # Case exists but has inactive status
                pruned_ids.append(case_id)
                reasons[case_id] = f'status:{case_status_map[case_id]}'
        
        # Remove pruned embeddings
        for case_id in pruned_ids:
            del embeddings[case_id]
        
        # Update metadata and save if anything was pruned
        if pruned_ids:
            data['metadata']['total_embeddings'] = len(embeddings)
            data['metadata']['last_updated'] = datetime.now().isoformat()
            self.save_embeddings(data)
        
        return {
            'pruned_count': len(pruned_ids),
            'pruned_ids': pruned_ids,
            'reason': reasons,
            'remaining_count': len(embeddings)
        }
    
    # -------------------------------------------------------------------------
    # Statistics methods
    # -------------------------------------------------------------------------
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored case embeddings.
        
        Returns:
            Dictionary with statistics
        """
        data = self.load_embeddings()
        metadata = data.get('metadata', {})
        embeddings_dict = data.get('embeddings', {})
        
        return {
            'total_embeddings': metadata.get('total_embeddings', len(embeddings_dict)),
            'model': metadata.get('model', 'unknown'),
            'last_updated': metadata.get('last_updated', 'unknown')
        }

