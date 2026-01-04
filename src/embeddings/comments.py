"""
Comment embedding store for evaluator comments.

This module provides CommentEmbeddingStore, a subclass of BaseEmbeddingStore
specialized for working with evaluator comment embeddings.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.embeddings.base import BaseEmbeddingStore


class CommentEmbeddingStore(BaseEmbeddingStore):
    """
    Embedding store for evaluator comments.
    
    Extends BaseEmbeddingStore with comment-specific functionality:
    - Key format: f"{case_id}_{evaluator}"
    - Text to embed: the comment text
    - Metadata: evaluator, decision, problem_axes
    - Methods for finding similar comments, clustering, and theme generation
    """
    
    DEFAULT_BATCH_SIZE = 100
    
    def __init__(
        self,
        embeddings_dir: str = "data/embeddings",
        evaluations_dir: str = "data/evaluations",
        model_size: str = 'small',
        api_key: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE
    ):
        """
        Initialize the comment embedding store.
        
        Args:
            embeddings_dir: Directory containing embedding files
            evaluations_dir: Directory containing evaluation files
            model_size: 'small' or 'large' for embedding model
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            batch_size: Number of comments to process in one API call
        """
        super().__init__(
            embeddings_dir=embeddings_dir,
            embeddings_filename="comment_embeddings.json",
            model_size=model_size,
            api_key=api_key
        )
        self.evaluations_dir = Path(evaluations_dir)
        self.batch_size = batch_size
        self.index_file = self.embeddings_dir / "embedding_index.json"
        self._metadata_cache: Optional[Dict[str, Any]] = None
    
    # -------------------------------------------------------------------------
    # Abstract method implementations
    # -------------------------------------------------------------------------
    
    def get_embedding_key(self, item: Any) -> str:
        """
        Get the unique key for a comment embedding.
        
        Args:
            item: Dictionary or object with case_id and evaluator
            
        Returns:
            Key in format "{case_id}_{evaluator}"
        """
        if isinstance(item, dict):
            return f"{item['case_id']}_{item['evaluator']}"
        # Handle object with attributes
        return f"{item.case_id}_{item.evaluator}"
    
    def get_text_to_embed(self, item: Any) -> str:
        """
        Get the comment text to embed.
        
        Args:
            item: Dictionary or object with comments field
            
        Returns:
            The comment text
        """
        if isinstance(item, dict):
            return item['comments']
        return item.comments
    
    # -------------------------------------------------------------------------
    # Evaluation loading and embedding generation
    # -------------------------------------------------------------------------
    
    def load_all_evaluations(self) -> List[Dict[str, Any]]:
        """
        Load all evaluation files from all evaluators.
        
        Scans data/evaluations/case_evaluations/{evaluator}/*.json and loads
        evaluations that have comments.
        
        Returns:
            List of evaluation dictionaries with metadata including:
            - case_id, evaluator, comments, decision, problem_axes, evaluated_at
        """
        evaluations = []
        case_evaluations_dir = self.evaluations_dir / "case_evaluations"
        
        if not case_evaluations_dir.exists():
            return evaluations
        
        for evaluator_dir in case_evaluations_dir.iterdir():
            if not evaluator_dir.is_dir():
                continue
            
            evaluator_name = evaluator_dir.name
            
            for eval_file in evaluator_dir.glob("case_*.json"):
                try:
                    with open(eval_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Only include evaluations with comments
                    if data.get('comments'):
                        evaluations.append({
                            'case_id': data['case_id'],
                            'evaluator': data['evaluator'],
                            'comments': data['comments'],
                            'decision': data['decision'],
                            'problem_axes': data.get('problem_axes'),
                            'evaluated_at': data['evaluated_at'],
                            'file_path': str(eval_file)
                        })
                
                except Exception:
                    # Skip files that can't be loaded
                    continue
        
        return evaluations
    
    def generate_all_embeddings(
        self,
        force: bool = False,
        verbose: bool = False
    ) -> Dict[str, int]:
        """
        Generate embeddings for all evaluator comments.
        
        Loads all evaluations, filters to new ones (unless force=True),
        generates embeddings in batches, and stores them with metadata.
        
        Args:
            force: If True, regenerate embeddings even if they exist
            verbose: If True, print progress information
            
        Returns:
            Dictionary with generation statistics:
            - total_evaluations: Total evaluations with comments found
            - embeddings_generated: Number of new embeddings generated
            - embeddings_skipped: Number of existing embeddings skipped
            - embeddings_failed: Number of failed embedding generations
            - total_stored: Total embeddings stored after operation
        """
        # Load all evaluations with comments
        evaluations = self.load_all_evaluations()
        
        if not evaluations:
            return {
                'total_evaluations': 0,
                'embeddings_generated': 0,
                'embeddings_skipped': 0,
                'embeddings_failed': 0,
                'total_stored': 0
            }
        
        if verbose:
            print(f"Found {len(evaluations)} evaluations with comments")
        
        # Load existing embeddings
        if force:
            existing_data = {'metadata': {}, 'embeddings': {}}
        else:
            existing_data = self.load_embeddings()
        
        existing_embeddings = existing_data.get('embeddings', {})
        
        # Filter to new evaluations
        new_evaluations = [
            e for e in evaluations
            if f"{e['case_id']}_{e['evaluator']}" not in existing_embeddings
        ]
        
        skipped_count = len(evaluations) - len(new_evaluations)
        
        if verbose:
            if force:
                print(f"Regenerating all {len(new_evaluations)} embeddings")
            else:
                print(f"{len(new_evaluations)} new embeddings to generate, {skipped_count} skipped")
        
        if not new_evaluations:
            return {
                'total_evaluations': len(evaluations),
                'embeddings_generated': 0,
                'embeddings_skipped': skipped_count,
                'embeddings_failed': 0,
                'total_stored': len(existing_embeddings)
            }
        
        # Generate embeddings in batches
        generated_count = 0
        failed_count = 0
        
        for i in range(0, len(new_evaluations), self.batch_size):
            batch = new_evaluations[i:i + self.batch_size]
            batch_texts = [e['comments'] for e in batch]
            
            if verbose:
                batch_num = i // self.batch_size + 1
                total_batches = (len(new_evaluations) - 1) // self.batch_size + 1
                print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} comments)...")
            
            try:
                embeddings = self.embed_texts(batch_texts)
                
                # Store embeddings with metadata
                for eval_data, embedding in zip(batch, embeddings):
                    key = f"{eval_data['case_id']}_{eval_data['evaluator']}"
                    existing_embeddings[key] = {
                        'case_id': eval_data['case_id'],
                        'evaluator': eval_data['evaluator'],
                        'comments': eval_data['comments'],
                        'decision': eval_data['decision'],
                        'problem_axes': eval_data['problem_axes'],
                        'evaluated_at': eval_data['evaluated_at'],
                        'embedding': embedding,
                        'embedding_model': self.model,
                        'generated_at': datetime.now().isoformat()
                    }
                    generated_count += 1
                
                # Rate limiting - be respectful to the API
                if i + self.batch_size < len(new_evaluations):
                    time.sleep(1)
                    
            except Exception as e:
                failed_count += len(batch)
                if verbose:
                    print(f"Failed to generate embeddings for batch: {e}")
        
        # Prepare output data
        embedding_dimension = 0
        if existing_embeddings:
            first_emb = next(iter(existing_embeddings.values()))
            if isinstance(first_emb, dict) and 'embedding' in first_emb:
                embedding_dimension = len(first_emb['embedding'])
        
        output_data = {
            'metadata': {
                'model': self.model,
                'total_embeddings': len(existing_embeddings),
                'generated_at': datetime.now().isoformat(),
                'embedding_dimension': embedding_dimension
            },
            'embeddings': existing_embeddings
        }
        
        # Save embeddings
        self.save_embeddings(output_data)
        
        # Save metadata-only index for quick lookup
        self._save_index(existing_embeddings)
        
        if verbose:
            print(f"Generated {generated_count} new embeddings, {failed_count} failed")
            print(f"Total embeddings stored: {len(existing_embeddings)}")
        
        return {
            'total_evaluations': len(evaluations),
            'embeddings_generated': generated_count,
            'embeddings_skipped': skipped_count,
            'embeddings_failed': failed_count,
            'total_stored': len(existing_embeddings)
        }
    
    def _save_index(self, embeddings_dict: Dict[str, Any]) -> None:
        """
        Save a metadata-only index for quick lookup.
        
        Args:
            embeddings_dict: Dictionary of embeddings to index
        """
        index_data = {
            key: {
                'case_id': val['case_id'],
                'evaluator': val['evaluator'],
                'comments_preview': val['comments'][:100] + '...' if len(val['comments']) > 100 else val['comments'],
                'decision': val['decision'],
                'problem_axes': val['problem_axes'],
                'evaluated_at': val['evaluated_at'],
                'embedding_model': val.get('embedding_model', self.model),
                'generated_at': val.get('generated_at', '')
            }
            for key, val in embeddings_dict.items()
        }
        
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)
    
    # -------------------------------------------------------------------------
    # Comment-specific methods
    # -------------------------------------------------------------------------
    
    def load_index(self, reload: bool = False) -> Dict[str, Any]:
        """
        Load embedding index (metadata only, faster for browsing).
        
        Args:
            reload: Force reload from disk even if cached
            
        Returns:
            Dictionary with embedding metadata
        """
        if self._metadata_cache is not None and not reload:
            return self._metadata_cache
        
        import json
        
        if not self.index_file.exists():
            # Fall back to full embeddings file
            data = self.load_embeddings(reload)
            self._metadata_cache = data.get('embeddings', {})
            return self._metadata_cache
        
        with open(self.index_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self._metadata_cache = data
        return data
    
    def get_embedding(self, case_id: str, evaluator: str) -> Optional[List[float]]:
        """
        Get embedding for a specific case and evaluator.
        
        Args:
            case_id: Case ID
            evaluator: Evaluator username
            
        Returns:
            Embedding vector or None if not found
        """
        key = f"{case_id}_{evaluator}"
        return self.get_embedding_by_key(key)
    
    def find_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        exclude_keys: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find most similar comments to a query embedding.
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            exclude_keys: Keys to exclude from search (e.g., the query itself)
            
        Returns:
            List of dictionaries with similarity scores and metadata
        """
        data = self.load_embeddings()
        embeddings_dict = data.get('embeddings', {})
        
        exclude_keys = exclude_keys or []
        
        # Use batch_similarities for efficiency if no exclusions or few exclusions
        all_results = self.batch_similarities(query_embedding, top_k=None)
        
        # Filter and enrich results
        results = []
        for key, similarity in all_results:
            if key in exclude_keys:
                continue
            
            val = embeddings_dict[key]
            results.append({
                'key': key,
                'case_id': val['case_id'],
                'evaluator': val['evaluator'],
                'comments': val['comments'],
                'decision': val['decision'],
                'problem_axes': val.get('problem_axes'),
                'similarity': similarity
            })
            
            if len(results) >= top_k:
                break
        
        return results
    
    def find_similar_to_comment(
        self,
        case_id: str,
        evaluator: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find comments similar to a specific evaluation.
        
        Args:
            case_id: Case ID
            evaluator: Evaluator username
            top_k: Number of results to return
            
        Returns:
            List of similar comments with scores
        """
        query_embedding = self.get_embedding(case_id, evaluator)
        
        if query_embedding is None:
            raise ValueError(f"No embedding found for case {case_id} by {evaluator}")
        
        exclude_key = f"{case_id}_{evaluator}"
        return self.find_similar(query_embedding, top_k, exclude_keys=[exclude_key])
    
    # -------------------------------------------------------------------------
    # Clustering methods
    # -------------------------------------------------------------------------
    
    def cluster_comments(
        self,
        n_clusters: int = 5,
        method: str = 'kmeans'
    ) -> Dict[str, Any]:
        """
        Cluster comments based on embeddings.
        
        Args:
            n_clusters: Number of clusters
            method: Clustering method ('kmeans' or 'hierarchical')
            
        Returns:
            Dictionary with cluster data including:
            - `clusters`: list of cluster objects
            - `metadata`: clustering metadata
        """
        clusters, labels, embeddings_matrix = self._cluster_assignments(
            n_clusters=n_clusters,
            method=method
        )

        # Calculate silhouette score (only if we have more than 1 cluster and less than total points)
        silhouette_avg = None
        quality_assessment = None
        if 1 < n_clusters < len(embeddings_matrix):
            try:
                from sklearn.metrics import silhouette_score

                silhouette_avg = float(silhouette_score(embeddings_matrix, labels))

                if silhouette_avg > 0.7:
                    quality_assessment = "Excellent - clusters are well-separated"
                elif silhouette_avg > 0.5:
                    quality_assessment = "Good - reasonable cluster structure"
                elif silhouette_avg > 0.25:
                    quality_assessment = "Fair - some cluster overlap"
                else:
                    quality_assessment = "Poor - significant cluster overlap"
            except Exception as e:
                print(f"Warning: Could not calculate silhouette score: {e}")

        enriched_clusters = self._enrich_clusters(
            clusters=clusters,
            method=method,
            embeddings_matrix=embeddings_matrix,
            labels=labels,
            generate_descriptions=False,
            max_samples_per_cluster=5
        )

        return {
            'clusters': enriched_clusters,
            'metadata': {
                'n_clusters': len(enriched_clusters),
                'method': method,
                'total_comments': sum(c['size'] for c in enriched_clusters),
                'generated_descriptions': False,
                'silhouette_score': silhouette_avg,
                'quality_assessment': quality_assessment
            }
        }
    
    def cluster_with_descriptions(
        self,
        n_clusters: int = 5,
        method: str = 'kmeans',
        generate_descriptions: bool = True,
        max_samples_per_cluster: int = 5
    ) -> Dict[str, Any]:
        """
        Enhanced clustering with semantic theme descriptions.
        
        Args:
            n_clusters: Number of clusters (3-10 recommended)
            method: Clustering method ('kmeans' or 'hierarchical')
            generate_descriptions: Whether to generate LLM descriptions
            max_samples_per_cluster: Number of sample comments to include
            
        Returns:
            Dictionary with enriched cluster data including:
            - Cluster assignments
            - Theme descriptions
            - Sample comments
            - Problem axes aggregations
            - Statistics
            - Quality metrics (silhouette score)
        """
        clusters, labels, embeddings_matrix = self._cluster_assignments(
            n_clusters=n_clusters,
            method=method
        )

        # Calculate silhouette score (only if we have more than 1 cluster and less than total points)
        silhouette_avg = None
        quality_assessment = None
        if 1 < n_clusters < len(embeddings_matrix):
            try:
                from sklearn.metrics import silhouette_score

                silhouette_avg = float(silhouette_score(embeddings_matrix, labels))

                if silhouette_avg > 0.7:
                    quality_assessment = "Excellent - clusters are well-separated"
                elif silhouette_avg > 0.5:
                    quality_assessment = "Good - reasonable cluster structure"
                elif silhouette_avg > 0.25:
                    quality_assessment = "Fair - some cluster overlap"
                else:
                    quality_assessment = "Poor - significant cluster overlap"
            except Exception as e:
                print(f"Warning: Could not calculate silhouette score: {e}")

        enriched_clusters = self._enrich_clusters(
            clusters=clusters,
            method=method,
            embeddings_matrix=embeddings_matrix,
            labels=labels,
            generate_descriptions=generate_descriptions,
            max_samples_per_cluster=max_samples_per_cluster
        )
        
        return {
            'clusters': enriched_clusters,
            'metadata': {
                'n_clusters': len(enriched_clusters),
                'method': method,
                'total_comments': sum(c['size'] for c in enriched_clusters),
                'generated_descriptions': generate_descriptions,
                'silhouette_score': silhouette_avg,
                'quality_assessment': quality_assessment
            }
        }
    
    def _cluster_assignments(
        self,
        n_clusters: int,
        method: str
    ) -> Tuple[Dict[int, List[Dict[str, Any]]], Any, Any]:
        """
        Internal helper to compute cluster assignments and the per-item payload.

        Returns:
            (clusters_by_id, labels, embeddings_matrix)
        """
        try:
            from sklearn.cluster import KMeans, AgglomerativeClustering
        except ImportError:
            raise ImportError(
                "scikit-learn is required for clustering. "
                "Install with: uv add scikit-learn"
            )

        embeddings_matrix, keys = self.get_all_embeddings_matrix()

        if method == 'kmeans':
            clusterer = KMeans(n_clusters=n_clusters, random_state=42)
        elif method == 'hierarchical':
            clusterer = AgglomerativeClustering(n_clusters=n_clusters)
        else:
            raise ValueError(f"Unknown clustering method: {method}")

        labels = clusterer.fit_predict(embeddings_matrix)

        data = self.load_embeddings()
        embeddings_dict = data.get('embeddings', {})

        clusters: Dict[int, List[Dict[str, Any]]] = {}
        for key, label in zip(keys, labels):
            cluster_id = int(label)
            clusters.setdefault(cluster_id, []).append({
                'key': key,
                'case_id': embeddings_dict[key]['case_id'],
                'evaluator': embeddings_dict[key]['evaluator'],
                'comments': embeddings_dict[key]['comments'],
                'decision': embeddings_dict[key]['decision'],
                'problem_axes': embeddings_dict[key].get('problem_axes')
            })

        return clusters, labels, embeddings_matrix
    
    def _enrich_clusters(
        self,
        clusters: Dict[int, List[Dict[str, Any]]],
        method: str,
        embeddings_matrix: Any,
        labels: Any,
        generate_descriptions: bool,
        max_samples_per_cluster: int
    ) -> List[Dict[str, Any]]:
        """Internal helper to convert cluster dicts into a list of enriched cluster objects."""
        # Calculate silhouette score when possible
        silhouette_avg = None
        quality_assessment = None

        if embeddings_matrix is not None and labels is not None:
            try:
                from sklearn.metrics import silhouette_score

                n_clusters = len(clusters)
                if 1 < n_clusters < len(embeddings_matrix):
                    silhouette_avg = float(silhouette_score(embeddings_matrix, labels))

                    if silhouette_avg > 0.7:
                        quality_assessment = "Excellent - clusters are well-separated"
                    elif silhouette_avg > 0.5:
                        quality_assessment = "Good - reasonable cluster structure"
                    elif silhouette_avg > 0.25:
                        quality_assessment = "Fair - some cluster overlap"
                    else:
                        quality_assessment = "Poor - significant cluster overlap"
            except Exception as e:
                print(f"Warning: Could not calculate silhouette score: {e}")

        enriched_clusters: List[Dict[str, Any]] = []
        for cluster_id in sorted(clusters.keys()):
            cluster_items = clusters[cluster_id]
            problem_axes = self.get_cluster_problem_axes(cluster_items)

            if generate_descriptions:
                theme_description = self.generate_theme_description(
                    cluster_items,
                    max_samples=10
                )
            else:
                theme_description = self._generate_fallback_description(cluster_items)

            sample_comments = cluster_items[:max_samples_per_cluster]

            enriched_clusters.append({
                'id': cluster_id,
                'size': len(cluster_items),
                'theme_description': theme_description,
                'problem_axes': problem_axes,
                'sample_comments': sample_comments,
                'all_comment_keys': [item['key'] for item in cluster_items]
            })

        # Attach metadata to each cluster list consumer via a stable top-level key (handled by callers).
        # Silhouette/quality are returned from cluster_with_descriptions via metadata.
        _ = (method, silhouette_avg, quality_assessment)
        return enriched_clusters
    
    def get_cluster_problem_axes(
        self,
        cluster_items: List[Dict[str, Any]]
    ) -> List[Tuple[str, int]]:
        """
        Aggregate and rank problem axes for a cluster.
        
        Args:
            cluster_items: List of comment items in the cluster
            
        Returns:
            Sorted list of (axis, count) tuples
        """
        axis_counts: Dict[str, int] = {}
        
        for item in cluster_items:
            axes = item.get('problem_axes', [])
            if axes:
                for axis in axes:
                    axis_counts[axis] = axis_counts.get(axis, 0) + 1
        
        # Sort by count descending
        return sorted(axis_counts.items(), key=lambda x: x[1], reverse=True)
    
    # -------------------------------------------------------------------------
    # Theme generation methods
    # -------------------------------------------------------------------------
    
    def generate_theme_description(
        self,
        cluster_comments: List[Dict[str, Any]],
        max_samples: int = 10,
        api_key: Optional[str] = None
    ) -> str:
        """
        Generate a semantic theme description for a cluster using LLM.
        
        Args:
            cluster_comments: List of comments in the cluster
            max_samples: Maximum number of samples to use for generation
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            
        Returns:
            Theme description string
        """
        import os
        import requests
        
        api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        
        if not api_key:
            # Fallback: generate description from problem axes
            return self._generate_fallback_description(cluster_comments)
        
        # Select sample comments
        samples = cluster_comments[:max_samples]
        
        # Build sample text
        sample_text = "\n\n".join([
            f"{i+1}. \"{c['comments']}\" [Decision: {c['decision']}]"
            for i, c in enumerate(samples)
        ])
        
        # Build prompt
        prompt = f"""You are analyzing a cluster of evaluator comments about medical ethics cases.

Here are {len(samples)} sample comments from this cluster:

{sample_text}

Generate a concise 2-3 sentence description that captures the SEMANTIC THEME connecting these comments. Focus on:
- What common issues or concerns do they raise?
- What patterns in reasoning appear?
- What values or principles are at stake?

Provide only the theme description, no preamble."""
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://github.com/valuebench',
                    'X-Title': 'ValueBench Theme Clustering'
                },
                json={
                    'model': 'anthropic/claude-3.5-sonnet',
                    'messages': [
                        {'role': 'user', 'content': prompt}
                    ],
                    'max_tokens': 300
                },
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    return self._generate_fallback_description(cluster_comments)

                choices = data.get('choices') if isinstance(data, dict) else None
                if not isinstance(choices, list) or not choices:
                    return self._generate_fallback_description(cluster_comments)

                first_choice = choices[0] if isinstance(choices[0], dict) else None
                message = first_choice.get('message') if isinstance(first_choice, dict) else None
                content = message.get('content') if isinstance(message, dict) else None

                if not isinstance(content, str) or not content.strip():
                    return self._generate_fallback_description(cluster_comments)

                return content.strip()
            else:
                return self._generate_fallback_description(cluster_comments)
        
        except Exception as e:
            print(f"Warning: LLM theme generation failed: {e}")
            return self._generate_fallback_description(cluster_comments)
    
    def _generate_fallback_description(
        self,
        cluster_comments: List[Dict[str, Any]]
    ) -> str:
        """
        Generate a fallback description based on problem axes and decisions.
        
        Args:
            cluster_comments: List of comments in the cluster
            
        Returns:
            Fallback description string
        """
        # Aggregate problem axes
        axes = self.get_cluster_problem_axes(cluster_comments)
        
        # Count decisions
        decision_counts: Dict[str, int] = {}
        for comment in cluster_comments:
            dec = comment.get('decision', 'unknown')
            decision_counts[dec] = decision_counts.get(dec, 0) + 1
        
        # Build description
        description_parts = []
        
        if axes:
            top_axes = [axis for axis, _ in axes[:3]]
            description_parts.append(
                f"Comments primarily focused on {', '.join(top_axes)}"
            )
        
        # Add decision context
        if decision_counts:
            max_decision = max(decision_counts.items(), key=lambda x: x[1])
            if max_decision[1] / len(cluster_comments) > 0.6:
                description_parts.append(
                    f"predominantly {max_decision[0]} decisions"
                )
        
        if description_parts:
            return ". ".join(description_parts) + "."
        else:
            return f"Cluster of {len(cluster_comments)} related comments."
    
    # -------------------------------------------------------------------------
    # Statistics methods
    # -------------------------------------------------------------------------
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored embeddings.
        
        Returns:
            Dictionary with statistics
        """
        data = self.load_embeddings()
        metadata = data.get('metadata', {})
        embeddings_dict = data.get('embeddings', {})
        
        # Count by evaluator
        evaluator_counts: Dict[str, int] = {}
        decision_counts: Dict[str, int] = {}
        problem_axes_counts: Dict[str, int] = {}
        unexpected_decisions = set()
        known_decisions = {'approve', 'reject', 'skip'}
        
        for val in embeddings_dict.values():
            evaluator = val['evaluator']
            evaluator_counts[evaluator] = evaluator_counts.get(evaluator, 0) + 1
            
            decision = val.get('decision') or 'unknown'
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            if decision not in known_decisions:
                unexpected_decisions.add(decision)
            
            if val.get('problem_axes'):
                for axis in val['problem_axes']:
                    problem_axes_counts[axis] = problem_axes_counts.get(axis, 0) + 1
        
        return {
            'total_embeddings': metadata.get('total_embeddings', len(embeddings_dict)),
            'embedding_dimension': metadata.get('embedding_dimension', 0),
            'model': metadata.get('model', 'unknown'),
            'generated_at': metadata.get('generated_at', 'unknown'),
            'evaluator_counts': evaluator_counts,
            'decision_counts': decision_counts,
            'problem_axes_counts': problem_axes_counts,
            'unexpected_decisions': sorted(unexpected_decisions)
        }
    
    # -------------------------------------------------------------------------
    # Override invalidate_cache to also clear metadata cache
    # -------------------------------------------------------------------------
    
    def invalidate_cache(self) -> None:
        """Clear all caches, forcing reload on next access."""
        super().invalidate_cache()
        self._metadata_cache = None

