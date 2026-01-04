#!/usr/bin/env python3
"""
Interactive case viewer for ValueBench
Displays cases with all evaluator feedback in a web interface
"""

import json
import os
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from typing import Dict, List, Optional
import re
import requests
from dotenv import load_dotenv
from src.embeddings import CommentEmbeddingStore, CaseEmbeddingStore
import numpy as np

# Load environment variables
load_dotenv()

# Project root is parent of viewer directory
PROJECT_ROOT = Path(__file__).parent.parent

app = Flask(__name__, template_folder="templates")

# Initialize embedding stores
embedding_store = CommentEmbeddingStore()
case_embedding_store = CaseEmbeddingStore()

# Paths (relative to project root)
CASES_DIR = PROJECT_ROOT / "data/cases"
EVALUATIONS_DIR = PROJECT_ROOT / "data/evaluations/case_evaluations"

# UUID v4 pattern for case ID validation
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE)

def is_valid_case_id(case_id: str) -> bool:
    """Validate that case_id is a valid UUID v4."""
    return bool(UUID_PATTERN.match(case_id))

def get_case_id_from_filename(filename: str) -> str:
    """Extract case_id from case filename."""
    # Format: case_<uuid>_<hash>.json
    parts = filename.replace("case_", "").replace(".json", "").split("_")
    return parts[0]

def load_case(case_file: Path) -> Optional[Dict]:
    """Load a case file."""
    try:
        with open(case_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading case {case_file}: {e}")
        return None

def load_evaluations(case_id: str) -> Dict[str, Dict]:
    """Load all evaluations for a case from all evaluators."""
    # Validate case_id to prevent path traversal
    if not is_valid_case_id(case_id):
        print(f"Warning: Invalid case_id format: {case_id}")
        return {}
    
    evaluations = {}
    
    for evaluator_dir in EVALUATIONS_DIR.iterdir():
        if not evaluator_dir.is_dir():
            continue
            
        evaluator_name = evaluator_dir.name
        eval_file = evaluator_dir / f"case_{case_id}.json"
        
        if eval_file.exists():
            try:
                with open(eval_file) as f:
                    evaluations[evaluator_name] = json.load(f)
            except Exception as e:
                print(f"Error loading evaluation {eval_file}: {e}")
    
    return evaluations

def get_final_version(case: Dict) -> Dict:
    """Get the final version of a case from refinement history."""
    if case is None or "refinement_history" not in case:
        return {}
    
    # Get the last iteration with data
    for item in reversed(case["refinement_history"]):
        if "data" in item and item["data"]:
            return item["data"]
    
    return {}

def get_all_cases() -> List[Dict]:
    """Get all cases with their metadata."""
    cases = []
    
    for case_file in sorted(CASES_DIR.glob("case_*.json")):
        case_id = get_case_id_from_filename(case_file.name)
        case = load_case(case_file)
        
        if case is None:
            continue
        
        final = get_final_version(case)
        evaluations = load_evaluations(case_id)
        
        # Extract seed info
        seed_info = case.get("seed", {})
        seed_params = seed_info.get("parameters", {})
        
        # Count evaluations and get decision summary
        eval_decisions = {}
        approve_count = 0
        reject_count = 0
        skip_count = 0
        
        for evaluator, eval_data in evaluations.items():
            decision = eval_data.get("decision", "unknown")
            eval_decisions[evaluator] = decision
            if decision == "approve":
                approve_count += 1
            elif decision == "reject":
                reject_count += 1
            elif decision == "skip":
                skip_count += 1
        
        # Calculate controversy score (disagreement)
        # Higher score = more mixed opinions
        total = len(evaluations) if evaluations else 1
        controversy = 0
        if total > 1:
            # Controversy is high when there are both approvals and rejections
            # Normalized to 0-1 scale
            if approve_count > 0 and reject_count > 0:
                controversy = min(approve_count, reject_count) / total
        
        cases.append({
            "case_id": case_id,
            "filename": case_file.name,
            "created_at": case.get("created_at", ""),
            "vignette": final.get("vignette", "N/A")[:200] + "..." if len(final.get("vignette", "")) > 200 else final.get("vignette", "N/A"),
            "value_pair": f"{seed_params.get('value_a', 'N/A')} vs {seed_params.get('value_b', 'N/A')}",
            "seed_mode": seed_info.get("mode", "N/A"),
            "domain": seed_params.get("medical_domain", "N/A"),
            "setting": seed_params.get("medical_setting", "N/A"),
            "evaluations": eval_decisions,
            "num_evaluations": len(evaluations),
            "approve_count": approve_count,
            "reject_count": reject_count,
            "skip_count": skip_count,
            "controversy": controversy
        })
    
    # Sort by creation date (newest first) by default
    cases = sorted(cases, key=lambda x: x['created_at'], reverse=True)
    
    return cases

@app.route('/')
def index():
    """Main page listing all cases."""
    cases = get_all_cases()
    
    # Get sort parameter from query string (default to newest)
    sort_by = request.args.get('sort', 'newest')
    
    # Sort cases based on parameter
    if sort_by == 'newest':
        # Already sorted by creation date (newest first) from get_all_cases()
        pass
    elif sort_by == 'oldest':
        cases = sorted(cases, key=lambda x: x['created_at'], reverse=False)
    elif sort_by == 'most_approved':
        cases = sorted(cases, key=lambda x: x['approve_count'], reverse=True)
    elif sort_by == 'most_rejected':
        cases = sorted(cases, key=lambda x: x['reject_count'], reverse=True)
    elif sort_by == 'most_controversial':
        # Primary: controversy (how mixed the opinions are). Secondary: # reviewers.
        # Example: 2 approve / 2 reject should rank above 1 approve / 1 reject.
        cases = sorted(cases, key=lambda x: (x['controversy'], x['num_evaluations']), reverse=True)
    elif sort_by == 'most_reviewed':
        cases = sorted(cases, key=lambda x: x['num_evaluations'], reverse=True)
    
    evaluators = set()
    for case in cases:
        evaluators.update(case["evaluations"].keys())
    
    return render_template('index.html', cases=cases, evaluators=sorted(evaluators), current_sort=sort_by)

@app.route('/feedback')
def feedback_view():
    """View aggregated feedback and comments across all cases."""
    cases = get_all_cases()
    
    all_comments = []
    
    # Collect all human evaluation comments
    for case_data in cases:
        case_id = case_data["case_id"]
        evaluations = load_evaluations(case_id)
        
        for evaluator, eval_data in evaluations.items():
            if eval_data.get("comments"):
                all_comments.append({
                    "case_id": case_id,
                    "evaluator": evaluator,
                    "decision": eval_data.get("decision", "unknown"),
                    "problem_axes": eval_data.get("problem_axes") or [],
                    "comment": eval_data.get("comments", ""),
                    "seed_mode": case_data.get("seed_mode", "N/A"),
                    "value_pair": case_data.get("value_pair", "N/A")
                })
    
    # Statistics
    stats = {
        "total_comments": len(all_comments),
        "by_decision": {},
        "by_evaluator": {},
        "by_axes": {},
        "by_seed_mode": {}
    }
    
    # Calculate statistics
    for comment in all_comments:
        decision = comment["decision"]
        evaluator = comment["evaluator"]
        seed_mode = comment["seed_mode"]
        
        stats["by_decision"][decision] = stats["by_decision"].get(decision, 0) + 1
        stats["by_evaluator"][evaluator] = stats["by_evaluator"].get(evaluator, 0) + 1
        stats["by_seed_mode"][seed_mode] = stats["by_seed_mode"].get(seed_mode, 0) + 1
        
        for axis in (comment["problem_axes"] or []):
            stats["by_axes"][axis] = stats["by_axes"].get(axis, 0) + 1
    
    return render_template('feedback.html',
                         comments=all_comments,
                         stats=stats)

@app.route('/case/<case_id>')
def view_case(case_id: str):
    """View detailed case information."""
    # Validate case_id is a proper UUID to prevent path traversal
    if not is_valid_case_id(case_id):
        return "Invalid case ID format", 400
    
    # Find the case file
    case_files = list(CASES_DIR.glob(f"case_{case_id}_*.json"))
    if not case_files:
        return "Case not found", 404
    
    case = load_case(case_files[0])
    if case is None:
        return "Error loading case", 500
    
    final = get_final_version(case)
    evaluations = load_evaluations(case_id)
    
    # Get all iterations for version navigation
    iterations = case.get("refinement_history", [])
    
    # Get similar cases (try, but don't fail if embeddings unavailable)
    similar_cases = []
    try:
        similar_raw = case_embedding_store.find_similar_cases(
            case_id=case_id,
            top_k=5,
            exclude_self=True
        )
        
        for item in similar_raw:
            similar_case_id = item['case_id']
            similar_case_files = list(CASES_DIR.glob(f"case_{similar_case_id}_*.json"))
            
            if similar_case_files:
                similar_case = load_case(similar_case_files[0])
                if similar_case:
                    similar_final = get_final_version(similar_case)
                    similar_seed = similar_case.get("seed", {})
                    similar_params = similar_seed.get("parameters", {})
                    similar_evals = load_evaluations(similar_case_id)
                    
                    approve_count = sum(1 for e in similar_evals.values() if e.get("decision") == "approve")
                    reject_count = sum(1 for e in similar_evals.values() if e.get("decision") == "reject")
                    
                    similar_cases.append({
                        "case_id": similar_case_id,
                        "case_id_short": similar_case_id[:8],
                        "similarity": round(item['similarity'], 4),
                        "similarity_pct": int(item['similarity'] * 100),
                        "vignette_preview": (similar_final.get("vignette", "")[:150] + "...") if len(similar_final.get("vignette", "")) > 150 else similar_final.get("vignette", "N/A"),
                        "value_pair": f"{similar_params.get('value_a', 'N/A')} vs {similar_params.get('value_b', 'N/A')}",
                        "seed_mode": similar_seed.get("mode", "N/A"),
                        "approve_count": approve_count,
                        "reject_count": reject_count
                    })
    except Exception as e:
        print(f"Warning: Could not fetch similar cases: {e}")
        similar_cases = []
    
    return render_template('case_detail.html',
                         case=case,
                         final=final,
                         evaluations=evaluations,
                         iterations=iterations,
                         similar_cases=similar_cases)

@app.route('/api/cases')
def api_cases():
    """API endpoint for case list."""
    return jsonify(get_all_cases())

@app.route('/api/case/<case_id>')
def api_case(case_id: str):
    """API endpoint for single case."""
    # Validate case_id is a proper UUID to prevent path traversal
    if not is_valid_case_id(case_id):
        return jsonify({"error": "Invalid case ID format"}), 400
    
    case_files = list(CASES_DIR.glob(f"case_{case_id}_*.json"))
    if not case_files:
        return jsonify({"error": "Case not found"}), 404
    
    case = load_case(case_files[0])
    if case is None:
        return jsonify({"error": "Error loading case"}), 500
    
    final = get_final_version(case)
    evaluations = load_evaluations(case_id)
    
    return jsonify({
        "case": case,
        "final": final,
        "evaluations": evaluations
    })

@app.route('/api/similar_comments/<case_id>/<evaluator>')
def api_similar_comments(case_id: str, evaluator: str):
    """
    Find semantically similar comments using embeddings.
    
    Args:
        case_id: Case UUID
        evaluator: Evaluator username
    
    Query parameters:
        top_k: Number of results to return (default 8)
    
    Returns:
        JSON with similar comments, ranked by similarity with relevance badges
    """
    # Validate case_id
    if not is_valid_case_id(case_id):
        return jsonify({
            "success": False,
            "error": "Invalid case ID format"
        }), 400
    
    try:
        from src.embeddings import CommentEmbeddingStore
        
        top_k = request.args.get('top_k', 8, type=int)
        min_similarity = 0.30  # Minimum threshold for relevance
        
        # Initialize embedding store
        store = CommentEmbeddingStore()
        
        # Get more results than needed, then filter
        similar = store.find_similar_to_comment(case_id, evaluator, top_k * 2)
        
        # Filter by minimum similarity threshold
        filtered = [s for s in similar if s['similarity'] >= min_similarity]
        
        # Take top K after filtering
        results = filtered[:top_k]
        
        # Enrich results with relevance badges and metadata
        for item in results:
            item['case_link'] = f"/case/{item['case_id']}"
            item['case_id_short'] = item['case_id'][:8]
            item['similarity_pct'] = int(item['similarity'] * 100)
            
            # Apply threshold strategy for relevance badges
            if item['similarity'] >= 0.50:
                item['relevance'] = 'high'
                item['relevance_label'] = 'High Relevance'
                item['relevance_icon'] = '✓✓'
            elif item['similarity'] >= 0.40:
                item['relevance'] = 'good'
                item['relevance_label'] = 'Good Relevance'
                item['relevance_icon'] = '✓'
            else:  # 0.30-0.40
                item['relevance'] = 'moderate'
                item['relevance_label'] = 'Moderate Relevance'
                item['relevance_icon'] = '~'
        
        return jsonify({
            'success': True,
            'query': {
                'case_id': case_id,
                'evaluator': evaluator,
                'case_id_short': case_id[:8]
            },
            'results': results,
            'metadata': {
                'total_found': len(similar),
                'shown': len(results),
                'min_similarity': min_similarity,
                'avg_similarity': sum(r['similarity'] for r in results) / len(results) if results else 0
            }
        })
    
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'error': 'Embeddings not found. Please run: uv run python generate_embeddings.py'
        }), 404
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@app.route('/api/cluster-comments')
def api_cluster_comments():
    """
    API endpoint for live comment clustering.
    
    Query parameters:
    - n_clusters: int (3-10, default 5)
    - method: str ('kmeans' or 'hierarchical', default 'kmeans')
    - generate_descriptions: bool (default True)
    
    Returns:
        JSON with cluster data including theme descriptions
    """
    try:
        from src.embeddings import CommentEmbeddingStore
        
        # Parse query parameters
        n_clusters = request.args.get('n_clusters', default=5, type=int)
        method = request.args.get('method', default='kmeans', type=str)
        generate_descriptions = request.args.get('generate_descriptions', default='true', type=str).lower() == 'true'
        
        # Validate parameters
        if n_clusters < 3 or n_clusters > 10:
            return jsonify({"error": "n_clusters must be between 3 and 10"}), 400
        
        if method not in ['kmeans', 'hierarchical']:
            return jsonify({"error": "method must be 'kmeans' or 'hierarchical'"}), 400
        
        # Initialize embedding store
        store = CommentEmbeddingStore()
        
        # Perform clustering
        result = store.cluster_with_descriptions(
            n_clusters=n_clusters,
            method=method,
            generate_descriptions=generate_descriptions,
            max_samples_per_cluster=5
        )
        
        return jsonify(result)
    
    except FileNotFoundError as e:
        return jsonify({
            "error": "Embeddings not found",
            "message": "Please run 'uv run python generate_embeddings.py' first to generate embeddings."
        }), 404
    
    except ImportError as e:
        return jsonify({
            "error": "Required library not found",
            "message": str(e)
        }), 500
    
    except Exception as e:
        return jsonify({
            "error": "Clustering failed",
            "message": str(e)
        }), 500

def generate_query_embedding(query: str):
    """Generate embedding for a query string using OpenRouter."""
    api_key = os.getenv('OPENROUTER_API_KEY')
    
    if not api_key:
        print("Warning: OPENROUTER_API_KEY not found")
        return None
    
    api_url = "https://openrouter.ai/api/v1/embeddings"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://github.com/valuebench',
        'X-Title': 'ValueBench Case Viewer'
    }
    
    payload = {
        'model': 'openai/text-embedding-3-small',
        'input': [query]
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data['data'][0]['embedding']
        else:
            print(f"API Error {response.status_code}: {response.text}")
            return None
    
    except Exception as e:
        print(f"Request failed: {e}")
        return None

@app.route('/api/search_semantic', methods=['POST'])
def search_semantic():
    """API endpoint for semantic search of comments."""
    data = request.get_json()
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 50)  # Return more results for better filtering
    
    if not query:
        return jsonify({"error": "Query is required"}), 400
    
    try:
        # Generate embedding for the query using OpenRouter
        query_embedding = generate_query_embedding(query)
        
        if not query_embedding:
            return jsonify({"error": "Failed to generate embedding"}), 500
        
        # Find similar comments
        similar_comments = embedding_store.find_similar(
            query_embedding=query_embedding,
            top_k=top_k
        )
        
        # Enrich with case metadata
        results = []
        for item in similar_comments:
            case_id = item['case_id']
            
            # Get case metadata
            case_files = list(CASES_DIR.glob(f"case_{case_id}_*.json"))
            if case_files:
                case = load_case(case_files[0])
                if case:
                    seed_info = case.get("seed", {})
                    seed_params = seed_info.get("parameters", {})
                    
                    results.append({
                        "case_id": case_id,
                        "evaluator": item['evaluator'],
                        "comment": item['comments'],
                        "decision": item['decision'],
                        "problem_axes": item['problem_axes'] or [],
                        "similarity": item['similarity'],
                        "seed_mode": seed_info.get("mode", "N/A"),
                        "value_pair": f"{seed_params.get('value_a', 'N/A')} vs {seed_params.get('value_b', 'N/A')}"
                    })
        
        return jsonify({
            "query": query,
            "results": results,
            "count": len(results)
        })
    
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        print(f"Error in semantic search: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500


# ============================================================================
# Embedding Visualization Routes
# ============================================================================

@app.route('/embeddings')
def embeddings_view():
    """Embeddings visualization page with 2D scatter plot of all cases."""
    cases = get_all_cases()
    return render_template('embeddings.html', cases=cases)


@app.route('/api/similar_cases/<case_id>')
def api_similar_cases(case_id: str):
    """
    Find cases most similar to a given case based on embeddings.
    
    Args:
        case_id: Case UUID
    
    Query parameters:
        top_k: Number of results to return (default 10)
    
    Returns:
        JSON with similar cases and cosine similarity scores
    """
    # Validate case_id
    if not is_valid_case_id(case_id):
        return jsonify({
            "success": False,
            "error": "Invalid case ID format"
        }), 400
    
    try:
        top_k = request.args.get('top_k', 10, type=int)
        
        # Find similar cases
        similar = case_embedding_store.find_similar_cases(
            case_id=case_id,
            top_k=top_k,
            exclude_self=True
        )
        
        # Enrich results with case metadata
        results = []
        for item in similar:
            similar_case_id = item['case_id']
            case_files = list(CASES_DIR.glob(f"case_{similar_case_id}_*.json"))
            
            if case_files:
                case = load_case(case_files[0])
                if case:
                    final = get_final_version(case)
                    seed_info = case.get("seed", {})
                    seed_params = seed_info.get("parameters", {})
                    evaluations = load_evaluations(similar_case_id)
                    
                    # Count approvals/rejections
                    approve_count = sum(1 for e in evaluations.values() if e.get("decision") == "approve")
                    reject_count = sum(1 for e in evaluations.values() if e.get("decision") == "reject")
                    
                    results.append({
                        "case_id": similar_case_id,
                        "case_id_short": similar_case_id[:8],
                        "similarity": round(item['similarity'], 4),
                        "similarity_pct": int(item['similarity'] * 100),
                        "vignette_preview": (final.get("vignette", "")[:200] + "...") if len(final.get("vignette", "")) > 200 else final.get("vignette", "N/A"),
                        "value_pair": f"{seed_params.get('value_a', 'N/A')} vs {seed_params.get('value_b', 'N/A')}",
                        "seed_mode": seed_info.get("mode", "N/A"),
                        "approve_count": approve_count,
                        "reject_count": reject_count,
                        "num_evaluations": len(evaluations)
                    })
        
        return jsonify({
            "success": True,
            "query_case_id": case_id,
            "query_case_id_short": case_id[:8],
            "results": results,
            "count": len(results)
        })
    
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        print(f"Error finding similar cases: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Internal error: {str(e)}"
        }), 500


@app.route('/api/case_embeddings_2d')
def api_case_embeddings_2d():
    """
    Get 2D projections of all case embeddings for visualization.
    
    Uses t-SNE or PCA to project high-dimensional embeddings to 2D.
    
    Query parameters:
        method: 'tsne' or 'pca' (default: 'tsne')
        perplexity: t-SNE perplexity (default: 30, range 5-50)
    
    Returns:
        JSON with case points containing x, y coordinates and metadata
    """
    try:
        method = request.args.get('method', 'tsne', type=str).lower()
        perplexity = request.args.get('perplexity', 30, type=int)
        perplexity = max(5, min(50, perplexity))  # Clamp to valid range
        
        # Get all embeddings
        matrix, keys = case_embedding_store.get_all_embeddings_matrix()
        
        if matrix.size == 0 or len(keys) == 0:
            return jsonify({
                "success": False,
                "error": "No case embeddings found"
            }), 404
        
        # Project to 2D
        if method == 'pca':
            from sklearn.decomposition import PCA
            reducer = PCA(n_components=2, random_state=42)
            coords_2d = reducer.fit_transform(matrix)
        else:  # tsne
            from sklearn.manifold import TSNE
            # Adjust perplexity if we have too few samples
            actual_perplexity = min(perplexity, len(keys) - 1)
            actual_perplexity = max(5, actual_perplexity)
            reducer = TSNE(n_components=2, perplexity=actual_perplexity, random_state=42)
            coords_2d = reducer.fit_transform(matrix)
        
        # Build results with case metadata
        points = []
        for i, case_id in enumerate(keys):
            case_files = list(CASES_DIR.glob(f"case_{case_id}_*.json"))
            
            metadata = {
                "case_id": case_id,
                "case_id_short": case_id[:8],
                "x": float(coords_2d[i, 0]),
                "y": float(coords_2d[i, 1]),
                "seed_mode": "unknown",
                "value_a": "N/A",
                "value_b": "N/A",
                "vignette_preview": "Case not found",
                "approve_count": 0,
                "reject_count": 0,
                "num_evaluations": 0
            }
            
            if case_files:
                case = load_case(case_files[0])
                if case:
                    final = get_final_version(case)
                    seed_info = case.get("seed", {})
                    seed_params = seed_info.get("parameters", {})
                    evaluations = load_evaluations(case_id)
                    
                    approve_count = sum(1 for e in evaluations.values() if e.get("decision") == "approve")
                    reject_count = sum(1 for e in evaluations.values() if e.get("decision") == "reject")
                    
                    metadata.update({
                        "seed_mode": seed_info.get("mode", "unknown"),
                        "value_a": seed_params.get("value_a", "N/A"),
                        "value_b": seed_params.get("value_b", "N/A"),
                        "domain": seed_params.get("medical_domain", "N/A"),
                        "vignette_preview": (final.get("vignette", "")[:150] + "...") if len(final.get("vignette", "")) > 150 else final.get("vignette", "N/A"),
                        "approve_count": approve_count,
                        "reject_count": reject_count,
                        "num_evaluations": len(evaluations)
                    })
            
            points.append(metadata)
        
        return jsonify({
            "success": True,
            "method": method,
            "perplexity": perplexity if method == 'tsne' else None,
            "total_cases": len(points),
            "points": points
        })
    
    except ImportError as e:
        return jsonify({
            "success": False,
            "error": f"Required library not found: {e}. Install scikit-learn."
        }), 500
    except Exception as e:
        print(f"Error generating 2D embeddings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Internal error: {str(e)}"
        }), 500


@app.route('/api/case_similarity/<case_id_a>/<case_id_b>')
def api_case_similarity(case_id_a: str, case_id_b: str):
    """
    Get cosine similarity between two specific cases.
    
    Args:
        case_id_a: First case UUID
        case_id_b: Second case UUID
    
    Returns:
        JSON with similarity score
    """
    # Validate case IDs
    if not is_valid_case_id(case_id_a) or not is_valid_case_id(case_id_b):
        return jsonify({
            "success": False,
            "error": "Invalid case ID format"
        }), 400
    
    try:
        from src.embeddings.base import BaseEmbeddingStore
        
        # Get embeddings for both cases
        emb_a = case_embedding_store.get_embedding_by_key(case_id_a)
        emb_b = case_embedding_store.get_embedding_by_key(case_id_b)
        
        if emb_a is None:
            return jsonify({
                "success": False,
                "error": f"No embedding found for case {case_id_a[:8]}..."
            }), 404
        
        if emb_b is None:
            return jsonify({
                "success": False,
                "error": f"No embedding found for case {case_id_b[:8]}..."
            }), 404
        
        # Compute cosine similarity
        similarity = BaseEmbeddingStore.cosine_similarity(emb_a, emb_b)
        
        return jsonify({
            "success": True,
            "case_id_a": case_id_a,
            "case_id_b": case_id_b,
            "similarity": round(similarity, 6),
            "similarity_pct": int(similarity * 100)
        })
    
    except Exception as e:
        print(f"Error computing similarity: {e}")
        return jsonify({
            "success": False,
            "error": f"Internal error: {str(e)}"
        }), 500


if __name__ == '__main__':
    print("Starting ValueBench Case Viewer...")
    print("Open http://localhost:5001 in your browser")
    app.run(debug=True, port=5001)

