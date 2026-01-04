#!/usr/bin/env python3
"""
Shared Utilities for Case Management

Provides common functions for:
- Loading and managing case files
- Loading and aggregating evaluation data
- Formatting human feedback for regeneration workflows

Usage:
    from src.manage_cases import (
        get_case_id_from_filename,
        load_all_case_ids,
        load_all_evaluations,
        aggregate_decisions,
        format_human_feedback,
        is_approved,
    )
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


# Default paths relative to project root
DEFAULT_CASES_DIR = Path("data/cases")
DEFAULT_EVALUATIONS_DIR = Path("data/evaluations/case_evaluations")


def get_case_id_from_filename(filename: str) -> str | None:
    """
    Extract UUID from case filename.
    
    Case files are named: case_{uuid}_{hash}.json
    
    Args:
        filename: The filename (can include path) to extract UUID from
        
    Returns:
        The UUID string, or None if filename doesn't match expected pattern
        
    Examples:
        >>> get_case_id_from_filename("case_026cd494-f2d2-45b9-a486-a9da7efed755_ca106b3bc125.json")
        '026cd494-f2d2-45b9-a486-a9da7efed755'
        >>> get_case_id_from_filename("case_026cd494-f2d2-45b9-a486-a9da7efed755.json")
        '026cd494-f2d2-45b9-a486-a9da7efed755'
    """
    # Get just the filename if a full path was provided
    name = Path(filename).stem
    
    # Pattern: case_{uuid}_{hash} or case_{uuid}
    # UUID format: 8-4-4-4-12 hex characters
    uuid_pattern = r"case_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    match = re.match(uuid_pattern, name, re.IGNORECASE)
    
    if match:
        return match.group(1)
    return None


def load_all_case_ids(cases_dir: Path | str = DEFAULT_CASES_DIR) -> dict[str, Path]:
    """
    Load all case IDs from case files.
    
    Args:
        cases_dir: Path to the cases directory (default: data/cases)
        
    Returns:
        Dictionary mapping case_id -> file_path
        
    Example:
        >>> case_ids = load_all_case_ids()
        >>> case_ids["026cd494-f2d2-45b9-a486-a9da7efed755"]
        PosixPath('data/cases/case_026cd494-f2d2-45b9-a486-a9da7efed755_ca106b3bc125.json')
    """
    cases_path = Path(cases_dir)
    case_id_to_path: dict[str, Path] = {}
    
    if not cases_path.exists():
        return case_id_to_path
    
    for case_file in cases_path.glob("case_*.json"):
        try:
            with open(case_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            case_id = data.get('case_id')
            if case_id:
                case_id_to_path[case_id] = case_file
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"[Warning] Could not read {case_file.name}: {e}")
    
    return case_id_to_path


def load_all_evaluations(
    evaluations_dir: Path | str = DEFAULT_EVALUATIONS_DIR
) -> dict[str, list[dict[str, Any]]]:
    """
    Load all evaluations grouped by case ID.
    
    Scans all evaluator subdirectories and collects evaluation data.
    
    Args:
        evaluations_dir: Path to evaluations directory (default: data/evaluations/case_evaluations)
        
    Returns:
        Dictionary mapping case_id -> list of evaluation dicts.
        Each evaluation dict contains:
        - evaluator: str (reviewer name)
        - decision: str ("approve" or "reject")
        - comments: str (may be empty)
        - problem_axes: list[str]
        - file_path: str (path to the evaluation file)
        
    Example:
        >>> evals = load_all_evaluations()
        >>> evals["026cd494-f2d2-45b9-a486-a9da7efed755"]
        [{'evaluator': 'becca', 'decision': 'approve', 'comments': '...', ...}, ...]
    """
    evaluations_path = Path(evaluations_dir)
    evaluations_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    
    if not evaluations_path.exists():
        return dict(evaluations_by_case)
    
    # Scan all evaluator directories
    for evaluator_dir in evaluations_path.iterdir():
        if not evaluator_dir.is_dir():
            continue
        
        evaluator_name = evaluator_dir.name
        
        # Load each evaluation file (case_{uuid}.json)
        for eval_file in evaluator_dir.glob("case_*.json"):
            try:
                with open(eval_file, 'r', encoding='utf-8') as f:
                    eval_data = json.load(f)
                
                case_id = eval_data.get("case_id")
                if not case_id:
                    continue
                
                evaluations_by_case[case_id].append({
                    "evaluator": evaluator_name,
                    "decision": eval_data.get("decision", ""),
                    "comments": eval_data.get("comments", ""),
                    "problem_axes": eval_data.get("problem_axes", []),
                    "file_path": str(eval_file),
                })
                
            except (json.JSONDecodeError, KeyError, OSError) as e:
                print(f"[Warning] Error loading {eval_file}: {e}")
    
    return dict(evaluations_by_case)


def aggregate_decisions(evaluations: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Count approve and reject decisions from a list of evaluations.
    
    Args:
        evaluations: List of evaluation dicts (each must have 'decision' key)
        
    Returns:
        Tuple of (approve_count, reject_count)
        
    Example:
        >>> evals = [{"decision": "approve"}, {"decision": "reject"}, {"decision": "approve"}]
        >>> aggregate_decisions(evals)
        (2, 1)
    """
    approve_count = sum(1 for e in evaluations if e.get("decision") == "approve")
    reject_count = sum(1 for e in evaluations if e.get("decision") == "reject")
    return (approve_count, reject_count)


def format_human_feedback(evaluations: list[dict[str, Any]]) -> str:
    """
    Format evaluations into a human feedback string for the refine workflow.
    
    Includes ALL reviewer comments (both approvers and rejecters) with metadata.
    Empty comments are skipped.
    
    Args:
        evaluations: List of evaluation dicts containing evaluator, decision,
                    comments, and problem_axes fields
        
    Returns:
        Formatted feedback string with reviewer labels, or empty string if
        no non-empty comments exist
        
    Example output:
        [REVIEWER: becca] Decision: approve | Issues: clinical, ethical
        Comments: what is the best / standard recommended treatment...
        
        [REVIEWER: davidwu] Decision: reject | Issues: other
        Comments: I'm not sure the scenario makes sense...
    """
    feedback_parts = []
    
    for eval_data in evaluations:
        comments = eval_data.get("comments", "")
        if not comments or not comments.strip():
            continue
        
        evaluator = eval_data.get("evaluator", "unknown")
        decision = eval_data.get("decision", "unknown")
        problem_axes = eval_data.get("problem_axes", [])
        
        # Format issues list
        issues_str = ", ".join(problem_axes) if problem_axes else "none specified"
        
        # Build formatted feedback block
        block = f"[REVIEWER: {evaluator}] Decision: {decision} | Issues: {issues_str}\nComments: {comments.strip()}"
        feedback_parts.append(block)
    
    return "\n\n".join(feedback_parts)


def is_approved(
    case_id: str, 
    evaluations_by_case: dict[str, list[dict[str, Any]]],
    min_approvals: int = 2
) -> bool:
    """
    Determine if a case is approved based on evaluation decisions.
    
    A case is approved if:
    1. approve_count > reject_count
    2. approve_count >= min_approvals (default: 2)
    
    Ties (approve_count == reject_count) are considered rejected per pipeline spec.
    
    Args:
        case_id: The UUID of the case to check
        evaluations_by_case: Dictionary mapping case_id -> list of evaluations
        min_approvals: Minimum number of approvals required (default: 2)
        
    Returns:
        True if the case has more approvals than rejections AND meets minimum,
        False otherwise. Returns False if the case has no evaluations.
        
    Example:
        >>> evals = {"case-123": [{"decision": "approve"}, {"decision": "approve"}, {"decision": "reject"}]}
        >>> is_approved("case-123", evals)
        True
        >>> is_approved("case-456", evals)  # Case not in dict
        False
        >>> evals2 = {"case-789": [{"decision": "approve"}]}  # Only 1 approval
        >>> is_approved("case-789", evals2)  # Below minimum
        False
    """
    evals = evaluations_by_case.get(case_id, [])
    if not evals:
        return False
    
    approve_count, reject_count = aggregate_decisions(evals)
    return approve_count > reject_count and approve_count >= min_approvals


def get_evaluated_case_ids(
    evaluations_dir: Path | str = DEFAULT_EVALUATIONS_DIR
) -> set[str]:
    """
    Get set of case IDs that have at least one evaluation.
    
    More efficient than load_all_evaluations when you only need
    to know which cases have been evaluated.
    
    Args:
        evaluations_dir: Path to evaluations directory
        
    Returns:
        Set of case IDs that have at least one evaluation file
    """
    evaluations_path = Path(evaluations_dir)
    evaluated_ids: set[str] = set()
    
    if not evaluations_path.exists():
        return evaluated_ids
    
    # Scan all evaluator directories
    for evaluator_dir in evaluations_path.iterdir():
        if not evaluator_dir.is_dir():
            continue
        
        # Each file is named case_{uuid}.json
        for eval_file in evaluator_dir.glob("case_*.json"):
            # Extract case_id from filename: case_{uuid}.json -> {uuid}
            case_id = eval_file.stem.replace("case_", "")
            evaluated_ids.add(case_id)
    
    return evaluated_ids


def find_case_file(cases_dir: Path | str, case_id: str) -> Path | None:
    """
    Find the case file for a given case ID.
    
    Case files are named: case_{uuid}_{hash}.json
    
    Args:
        cases_dir: Path to cases directory
        case_id: The case UUID to find
        
    Returns:
        Path to the case file, or None if not found
    """
    cases_path = Path(cases_dir)
    
    if not cases_path.exists():
        return None
    
    # Search for case file matching the case_id
    for case_file in cases_path.glob(f"case_{case_id}_*.json"):
        return case_file
    
    return None


def load_case_data(cases_dir: Path | str, case_id: str) -> dict[str, Any] | None:
    """
    Load case data from JSON file.
    
    Args:
        cases_dir: Path to cases directory
        case_id: The case UUID to load
        
    Returns:
        Dictionary with case data (including '_filepath' key), or None if not found
    """
    case_file = find_case_file(cases_dir, case_id)
    
    if not case_file:
        return None
    
    try:
        with open(case_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Add filepath for reference
        data['_filepath'] = str(case_file)
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Warning] Could not load case {case_id}: {e}")
        return None


def get_final_case_content(case_data: dict[str, Any]) -> dict[str, str] | None:
    """
    Extract the final vignette and choices from case data.
    
    Args:
        case_data: Raw case data dictionary
        
    Returns:
        Dictionary with vignette, choice_1, choice_2 or None if not found
    """
    refinement_history = case_data.get('refinement_history', [])
    if not refinement_history:
        return None
    
    # Get the last iteration's data
    final_data = refinement_history[-1].get('data', {})
    
    vignette = final_data.get('vignette', '')
    if not vignette:
        return None
    
    # Extract choice_1 (handle both string and dict formats)
    choice_1 = final_data.get('choice_1', '')
    if isinstance(choice_1, dict):
        choice_1 = choice_1.get('choice', '')
    
    # Extract choice_2 (handle both string and dict formats)
    choice_2 = final_data.get('choice_2', '')
    if isinstance(choice_2, dict):
        choice_2 = choice_2.get('choice', '')
    
    return {
        'vignette': vignette,
        'choice_1': choice_1,
        'choice_2': choice_2
    }


def get_approved_case_ids(
    evaluations_by_case: dict[str, list[dict[str, Any]]]
) -> list[str]:
    """
    Get list of case IDs that were approved (approves > rejects).
    
    Args:
        evaluations_by_case: Dictionary mapping case_id -> list of evaluations
        
    Returns:
        List of case IDs that have more approvals than rejections
    """
    return [
        case_id for case_id in evaluations_by_case
        if is_approved(case_id, evaluations_by_case)
    ]


def get_rejected_case_ids(
    evaluations_by_case: dict[str, list[dict[str, Any]]]
) -> list[str]:
    """
    Get list of case IDs that were rejected (rejects >= approves).
    
    Includes both majority rejects and tie cases.
    
    Args:
        evaluations_by_case: Dictionary mapping case_id -> list of evaluations
        
    Returns:
        List of case IDs that have rejections >= approvals
    """
    return [
        case_id for case_id in evaluations_by_case
        if not is_approved(case_id, evaluations_by_case)
    ]


if __name__ == "__main__":
    # Simple smoke test when run directly
    print("Testing utils.py...")
    
    # Test filename parsing
    test_filename = "case_026cd494-f2d2-45b9-a486-a9da7efed755_ca106b3bc125.json"
    case_id = get_case_id_from_filename(test_filename)
    print(f"  get_case_id_from_filename: {case_id}")
    assert case_id == "026cd494-f2d2-45b9-a486-a9da7efed755"
    
    # Test aggregate_decisions
    test_evals = [
        {"decision": "approve"},
        {"decision": "reject"},
        {"decision": "approve"},
    ]
    approves, rejects = aggregate_decisions(test_evals)
    print(f"  aggregate_decisions: approves={approves}, rejects={rejects}")
    assert (approves, rejects) == (2, 1)
    
    # Test format_human_feedback
    test_evals_with_comments = [
        {
            "evaluator": "alice",
            "decision": "approve",
            "comments": "Looks good",
            "problem_axes": ["clinical"],
        },
        {
            "evaluator": "bob",
            "decision": "reject",
            "comments": "",  # Empty comment - should be skipped
            "problem_axes": [],
        },
        {
            "evaluator": "carol",
            "decision": "reject",
            "comments": "Needs work on ethical framing",
            "problem_axes": ["ethical", "other"],
        },
    ]
    feedback = format_human_feedback(test_evals_with_comments)
    print(f"  format_human_feedback: {len(feedback)} chars")
    assert "[REVIEWER: alice]" in feedback
    assert "[REVIEWER: bob]" not in feedback  # Empty comment skipped
    assert "[REVIEWER: carol]" in feedback
    
    # Test is_approved (requires min 2 approvals by default)
    test_evals_by_case = {
        "case-approved": [{"decision": "approve"}, {"decision": "approve"}, {"decision": "reject"}],
        "case-rejected": [{"decision": "reject"}, {"decision": "reject"}],
        "case-tie": [{"decision": "approve"}, {"decision": "reject"}],
        "case-insufficient": [{"decision": "approve"}],  # Only 1 approval - below minimum
    }
    print(f"  is_approved('case-approved'): {is_approved('case-approved', test_evals_by_case)}")
    print(f"  is_approved('case-rejected'): {is_approved('case-rejected', test_evals_by_case)}")
    print(f"  is_approved('case-tie'): {is_approved('case-tie', test_evals_by_case)}")
    print(f"  is_approved('case-insufficient'): {is_approved('case-insufficient', test_evals_by_case)}")
    assert is_approved("case-approved", test_evals_by_case) is True
    assert is_approved("case-rejected", test_evals_by_case) is False
    assert is_approved("case-tie", test_evals_by_case) is False  # Ties go to rejection
    assert is_approved("case-insufficient", test_evals_by_case) is False  # Below min approvals
    
    print("\n✓ All tests passed!")

