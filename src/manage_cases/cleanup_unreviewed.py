#!/usr/bin/env python3
"""
Phase 1: Cleanup Unreviewed Cases

Deletes case files that have no human evaluations and removes them from embeddings.

This script:
1. Loads all case IDs from data/cases/*.json
2. Loads evaluated case IDs from data/evaluations/case_evaluations/*/*.json
3. Finds unreviewed cases (cases with no evaluations)
4. Deletes the unreviewed case files
5. Updates data/embeddings/case_embeddings.json to remove deleted case IDs

Usage:
    # Preview what would be deleted (recommended first)
    uv run python -m src.manage_cases.cleanup_unreviewed --dry-run
    
    # Actually delete files
    uv run python -m src.manage_cases.cleanup_unreviewed
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.manage_cases.utils import (
    load_all_case_ids,
    get_evaluated_case_ids,
    DEFAULT_CASES_DIR,
    DEFAULT_EVALUATIONS_DIR,
)


DEFAULT_EMBEDDINGS_FILE = Path("data/embeddings/case_embeddings.json")


def find_unreviewed_cases(
    cases_dir: Path = DEFAULT_CASES_DIR,
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
) -> dict[str, Path]:
    """
    Find cases that have no human evaluations.
    
    Args:
        cases_dir: Path to cases directory
        evaluations_dir: Path to evaluations directory
        
    Returns:
        Dictionary mapping unreviewed case_id -> file_path
    """
    # Get all case IDs and their file paths
    all_cases = load_all_case_ids(cases_dir)
    all_case_ids = set(all_cases.keys())
    
    # Get case IDs that have at least one evaluation
    evaluated_case_ids = get_evaluated_case_ids(evaluations_dir)
    
    # Find unreviewed cases
    unreviewed_ids = all_case_ids - evaluated_case_ids
    
    # Return mapping of unreviewed case_id -> file_path
    return {case_id: all_cases[case_id] for case_id in unreviewed_ids}


def delete_case_files(
    unreviewed_cases: dict[str, Path],
    dry_run: bool = True,
) -> list[str]:
    """
    Delete unreviewed case files.
    
    Args:
        unreviewed_cases: Dictionary mapping case_id -> file_path
        dry_run: If True, only print what would be deleted
        
    Returns:
        List of deleted case IDs
    """
    deleted_ids = []
    
    for case_id, file_path in sorted(unreviewed_cases.items()):
        if dry_run:
            print(f"  [DRY RUN] Would delete: {file_path.name}")
        else:
            try:
                file_path.unlink()
                print(f"  Deleted: {file_path.name}")
                deleted_ids.append(case_id)
            except OSError as e:
                print(f"  [ERROR] Could not delete {file_path.name}: {e}")
    
    return deleted_ids


def update_embeddings(
    deleted_case_ids: list[str],
    embeddings_file: Path = DEFAULT_EMBEDDINGS_FILE,
    dry_run: bool = True,
) -> int:
    """
    Remove deleted case IDs from the embeddings file.
    
    Args:
        deleted_case_ids: List of case IDs to remove
        embeddings_file: Path to the embeddings JSON file
        dry_run: If True, only print what would be removed
        
    Returns:
        Number of embeddings removed
    """
    if not embeddings_file.exists():
        print(f"  [WARNING] Embeddings file not found: {embeddings_file}")
        return 0
    
    # Load embeddings
    with open(embeddings_file, 'r', encoding='utf-8') as f:
        embeddings_data = json.load(f)
    
    # Get current embeddings dict
    embeddings = embeddings_data.get("embeddings", {})
    
    # Find which deleted case IDs are in embeddings
    deleted_set = set(deleted_case_ids)
    to_remove = [case_id for case_id in embeddings.keys() if case_id in deleted_set]
    
    if dry_run:
        for case_id in to_remove:
            print(f"  [DRY RUN] Would remove embedding for: {case_id}")
        return len(to_remove)
    
    # Remove embeddings
    removed_count = 0
    for case_id in to_remove:
        del embeddings[case_id]
        print(f"  Removed embedding for: {case_id}")
        removed_count += 1
    
    if removed_count > 0:
        # Update metadata
        embeddings_data["embeddings"] = embeddings
        embeddings_data["metadata"]["total_embeddings"] = len(embeddings)
        embeddings_data["metadata"]["last_updated"] = datetime.now().isoformat()
        
        # Write back
        with open(embeddings_file, 'w', encoding='utf-8') as f:
            json.dump(embeddings_data, f, indent=2)
        print(f"  Updated embeddings file with {len(embeddings)} remaining embeddings")
    
    return removed_count


def main():
    parser = argparse.ArgumentParser(
        description="Delete unreviewed cases and update embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making them (recommended first)",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help=f"Path to cases directory (default: {DEFAULT_CASES_DIR})",
    )
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=DEFAULT_EVALUATIONS_DIR,
        help=f"Path to evaluations directory (default: {DEFAULT_EVALUATIONS_DIR})",
    )
    parser.add_argument(
        "--embeddings-file",
        type=Path,
        default=DEFAULT_EMBEDDINGS_FILE,
        help=f"Path to embeddings file (default: {DEFAULT_EMBEDDINGS_FILE})",
    )
    
    args = parser.parse_args()
    
    # Header
    mode = "DRY RUN" if args.dry_run else "EXECUTING"
    print(f"\n{'='*60}")
    print(f"Phase 1: Cleanup Unreviewed Cases [{mode}]")
    print(f"{'='*60}\n")
    
    # Step 1: Find unreviewed cases
    print("Step 1: Finding unreviewed cases...")
    all_cases = load_all_case_ids(args.cases_dir)
    evaluated_ids = get_evaluated_case_ids(args.evaluations_dir)
    unreviewed_cases = find_unreviewed_cases(args.cases_dir, args.evaluations_dir)
    
    print(f"  Total cases: {len(all_cases)}")
    print(f"  Evaluated cases: {len(evaluated_ids)}")
    print(f"  Unreviewed cases: {len(unreviewed_cases)}")
    print()
    
    if not unreviewed_cases:
        print("No unreviewed cases found. Nothing to do.")
        return 0
    
    # Step 2: Delete case files
    print("Step 2: Deleting unreviewed case files...")
    if args.dry_run:
        deleted_ids = list(unreviewed_cases.keys())
        delete_case_files(unreviewed_cases, dry_run=True)
    else:
        deleted_ids = delete_case_files(unreviewed_cases, dry_run=False)
    print()
    
    # Step 3: Update embeddings
    print("Step 3: Updating embeddings...")
    removed_count = update_embeddings(
        deleted_ids,
        embeddings_file=args.embeddings_file,
        dry_run=args.dry_run,
    )
    print()
    
    # Summary
    print(f"{'='*60}")
    print("Summary:")
    if args.dry_run:
        print(f"  Would delete {len(unreviewed_cases)} case files")
        print(f"  Would remove {removed_count} embeddings")
        print("\nRun without --dry-run to execute these changes.")
    else:
        print(f"  Deleted {len(deleted_ids)} case files")
        print(f"  Removed {removed_count} embeddings")
    print(f"{'='*60}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

