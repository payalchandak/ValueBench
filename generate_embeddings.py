"""
Generate and Store LLM Embeddings for Evaluator Comments

This script generates embeddings for all evaluator comments using OpenRouter's API
and stores them for later use in analysis and similarity search.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class EmbeddingGenerator:
    """Generates and manages embeddings for evaluator comments using OpenRouter."""
    
    # Available embedding models on OpenRouter
    EMBEDDING_MODELS = {
        'small': 'openai/text-embedding-3-small',  # 512 dimensions, cost-effective
        'large': 'openai/text-embedding-3-large',  # 3072 dimensions, higher quality
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_size: str = 'small',
        batch_size: int = 100,
        evaluations_dir: str = "data/evaluations",
        embeddings_dir: str = "data/embeddings"
    ):
        """
        Initialize the embedding generator.
        
        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model_size: 'small' or 'large' for embedding model
            batch_size: Number of comments to process in one API call
            evaluations_dir: Directory containing evaluation files
            embeddings_dir: Directory to store embeddings
        """
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.model = self.EMBEDDING_MODELS[model_size]
        self.batch_size = batch_size
        self.evaluations_dir = Path(evaluations_dir)
        self.embeddings_dir = Path(embeddings_dir)
        self.embeddings_dir.mkdir(exist_ok=True, parents=True)
        
        self.api_url = "https://openrouter.ai/api/v1/embeddings"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://github.com/valuebench',  # Optional but recommended
            'X-Title': 'ValueBench Embedding Generator'
        }
    
    def load_all_evaluations(self) -> List[Dict[str, Any]]:
        """
        Load all evaluation files from all evaluators.
        
        Returns:
            List of evaluation dictionaries with metadata
        """
        evaluations = []
        case_evaluations_dir = self.evaluations_dir / "case_evaluations"
        
        if not case_evaluations_dir.exists():
            print(f"❌ Evaluations directory not found: {case_evaluations_dir}")
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
                
                except Exception as e:
                    print(f"⚠️  Warning: Could not load {eval_file}: {e}")
        
        return evaluations
    
    def generate_embeddings_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Generate embeddings for a batch of texts using OpenRouter API.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors or None if error
        """
        if not texts:
            return []
        
        payload = {
            'model': self.model,
            'input': texts
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # Extract embeddings in order
                embeddings = [item['embedding'] for item in sorted(data['data'], key=lambda x: x['index'])]
                return embeddings
            else:
                print(f"❌ API Error {response.status_code}: {response.text}")
                return None
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
    
    def generate_all_embeddings(self, force_regenerate: bool = False) -> Dict[str, Any]:
        """
        Generate embeddings for all evaluator comments.
        
        Args:
            force_regenerate: If True, regenerate embeddings even if they exist
            
        Returns:
            Dictionary with generation statistics
        """
        print("=" * 80)
        print("EMBEDDING GENERATION FOR EVALUATOR COMMENTS")
        print("=" * 80)
        
        # Load all evaluations with comments
        print("\n📂 Loading evaluations...")
        evaluations = self.load_all_evaluations()
        
        if not evaluations:
            print("❌ No evaluations with comments found.")
            return {'total_evaluations': 0, 'embeddings_generated': 0}
        
        print(f"✓ Found {len(evaluations)} evaluations with comments")
        
        # Check for existing embeddings
        embeddings_file = self.embeddings_dir / "comment_embeddings.json"
        existing_embeddings = {}
        
        if embeddings_file.exists() and not force_regenerate:
            try:
                with open(embeddings_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    existing_embeddings = existing_data.get('embeddings', {})
                print(f"✓ Loaded {len(existing_embeddings)} existing embeddings")
            except Exception as e:
                print(f"⚠️  Could not load existing embeddings: {e}")
        
        # Filter out evaluations that already have embeddings
        if not force_regenerate:
            new_evaluations = [
                e for e in evaluations
                if f"{e['case_id']}_{e['evaluator']}" not in existing_embeddings
            ]
            print(f"📊 {len(new_evaluations)} new embeddings to generate")
        else:
            new_evaluations = evaluations
            existing_embeddings = {}
            print(f"🔄 Regenerating all {len(new_evaluations)} embeddings")
        
        if not new_evaluations:
            print("✅ All embeddings are up to date!")
            return {
                'total_evaluations': len(evaluations),
                'embeddings_generated': 0,
                'embeddings_skipped': len(evaluations)
            }
        
        # Generate embeddings in batches
        print(f"\n🚀 Generating embeddings using model: {self.model}")
        print(f"   Batch size: {self.batch_size}")
        
        generated_count = 0
        failed_count = 0
        
        for i in range(0, len(new_evaluations), self.batch_size):
            batch = new_evaluations[i:i + self.batch_size]
            batch_texts = [e['comments'] for e in batch]
            
            print(f"\n📦 Processing batch {i // self.batch_size + 1}/{(len(new_evaluations) - 1) // self.batch_size + 1} ({len(batch)} comments)...")
            
            embeddings = self.generate_embeddings_batch(batch_texts)
            
            if embeddings:
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
                
                print(f"   ✓ Generated {len(embeddings)} embeddings")
                
                # Rate limiting - be respectful to the API
                if i + self.batch_size < len(new_evaluations):
                    time.sleep(1)  # Wait 1 second between batches
            else:
                failed_count += len(batch)
                print(f"   ✗ Failed to generate embeddings for this batch")
        
        # Save all embeddings
        print(f"\n💾 Saving embeddings to {embeddings_file}...")
        output_data = {
            'metadata': {
                'model': self.model,
                'total_embeddings': len(existing_embeddings),
                'generated_at': datetime.now().isoformat(),
                'embedding_dimension': len(next(iter(existing_embeddings.values()))['embedding']) if existing_embeddings else 0
            },
            'embeddings': existing_embeddings
        }
        
        with open(embeddings_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved {len(existing_embeddings)} total embeddings")
        
        # Also save a metadata-only index for quick lookup
        index_file = self.embeddings_dir / "embedding_index.json"
        index_data = {
            key: {
                'case_id': val['case_id'],
                'evaluator': val['evaluator'],
                'comments_preview': val['comments'][:100] + '...' if len(val['comments']) > 100 else val['comments'],
                'decision': val['decision'],
                'problem_axes': val['problem_axes'],
                'evaluated_at': val['evaluated_at'],
                'embedding_model': val['embedding_model'],
                'generated_at': val['generated_at']
            }
            for key, val in existing_embeddings.items()
        }
        
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved embedding index to {index_file}")
        
        # Print summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total evaluations with comments: {len(evaluations)}")
        print(f"New embeddings generated: {generated_count}")
        print(f"Failed: {failed_count}")
        print(f"Total embeddings stored: {len(existing_embeddings)}")
        print(f"Embedding dimension: {output_data['metadata']['embedding_dimension']}")
        print("=" * 80)
        
        return {
            'total_evaluations': len(evaluations),
            'embeddings_generated': generated_count,
            'embeddings_failed': failed_count,
            'total_stored': len(existing_embeddings)
        }
    
    def get_embedding(self, case_id: str, evaluator: str) -> Optional[List[float]]:
        """
        Retrieve stored embedding for a specific case and evaluator.
        
        Args:
            case_id: Case ID
            evaluator: Evaluator username
            
        Returns:
            Embedding vector or None if not found
        """
        embeddings_file = self.embeddings_dir / "comment_embeddings.json"
        
        if not embeddings_file.exists():
            return None
        
        try:
            with open(embeddings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            key = f"{case_id}_{evaluator}"
            embedding_data = data.get('embeddings', {}).get(key)
            
            return embedding_data['embedding'] if embedding_data else None
        
        except Exception as e:
            print(f"Error loading embedding: {e}")
            return None
    
    def find_similar_comments(
        self,
        query_case_id: str,
        query_evaluator: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find similar comments using cosine similarity.
        
        Args:
            query_case_id: Case ID to find similar comments for
            query_evaluator: Evaluator of the query comment
            top_k: Number of similar comments to return
            
        Returns:
            List of similar comment dictionaries with similarity scores
        """
        embeddings_file = self.embeddings_dir / "comment_embeddings.json"
        
        if not embeddings_file.exists():
            print("❌ No embeddings found. Run generate_all_embeddings first.")
            return []
        
        try:
            with open(embeddings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            embeddings = data.get('embeddings', {})
            query_key = f"{query_case_id}_{query_evaluator}"
            
            if query_key not in embeddings:
                print(f"❌ No embedding found for {query_key}")
                return []
            
            query_embedding = embeddings[query_key]['embedding']
            
            # Calculate cosine similarity with all other embeddings
            similarities = []
            
            for key, val in embeddings.items():
                if key == query_key:
                    continue
                
                # Cosine similarity
                embedding = val['embedding']
                dot_product = sum(a * b for a, b in zip(query_embedding, embedding))
                norm_query = sum(a * a for a in query_embedding) ** 0.5
                norm_embedding = sum(b * b for b in embedding) ** 0.5
                
                # Prevent division by zero for zero vectors
                if norm_query == 0.0 or norm_embedding == 0.0:
                    similarity = 0.0
                else:
                    similarity = dot_product / (norm_query * norm_embedding)
                
                similarities.append({
                    'case_id': val['case_id'],
                    'evaluator': val['evaluator'],
                    'comments': val['comments'],
                    'decision': val['decision'],
                    'problem_axes': val['problem_axes'],
                    'similarity': similarity
                })
            
            # Sort by similarity and return top k
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:top_k]
        
        except Exception as e:
            print(f"Error finding similar comments: {e}")
            return []


def main():
    """CLI for generating embeddings."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate and store LLM embeddings for evaluator comments using OpenRouter"
    )
    parser.add_argument(
        '--model-size',
        choices=['small', 'large'],
        default='small',
        help='Embedding model size (default: small)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of comments to process per API call (default: 100)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force regenerate all embeddings even if they exist'
    )
    parser.add_argument(
        '--find-similar',
        nargs=2,
        metavar=('CASE_ID', 'EVALUATOR'),
        help='Find similar comments to a specific evaluation'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=5,
        help='Number of similar comments to return (default: 5)'
    )
    
    args = parser.parse_args()
    
    try:
        generator = EmbeddingGenerator(
            model_size=args.model_size,
            batch_size=args.batch_size
        )
        
        if args.find_similar:
            case_id, evaluator = args.find_similar
            print(f"\n🔍 Finding comments similar to {case_id} by {evaluator}...\n")
            
            similar = generator.find_similar_comments(case_id, evaluator, args.top_k)
            
            if similar:
                for i, item in enumerate(similar, 1):
                    print(f"{i}. [{item['evaluator']}] {item['case_id'][:12]}... (similarity: {item['similarity']:.3f})")
                    print(f"   Decision: {item['decision']}")
                    if item['problem_axes']:
                        print(f"   Problem axes: {', '.join(item['problem_axes'])}")
                    print(f"   Comment: {item['comments']}")
                    print()
        else:
            generator.generate_all_embeddings(force_regenerate=args.force)
    
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Tip: Set your OpenRouter API key:")
        print("   export OPENROUTER_API_KEY='your-api-key-here'")
        return 1
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

