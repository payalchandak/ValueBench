#!/usr/bin/env python3
"""
Phase 2: Deprecate Rejected Cases

Updates rejected cases by setting status to 'deprecated'.
A case is rejected if:
  - rejects >= approves (majority/unanimous/tie rejection), OR
  - approves < 2 (insufficient approvals)

This keeps the case files for reference but marks them as not suitable for the benchmark.

Usage:
    uv run python -m src.manage_cases.deprecate_rejected --dry-run   # Preview changes
    uv run python -m src.manage_cases.deprecate_rejected             # Execute deprecation
"""

import argparse
import json
import sys
from pathlib import Path

from src.manage_cases.utils import (
    load_all_case_ids,
    load_all_evaluations,
    aggregate_decisions,
    get_rejected_case_ids,
)


def deprecate_case(case_file: Path, dry_run: bool) -> bool:
    """
    Update a case file's status to 'deprecated'.
    
    Args:
        case_file: Path to the case JSON file
        dry_run: If True, only report what would be done
        
    Returns:
        True if status was changed, False if already deprecated or error
    """
    try:
        with open(case_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        current_status = data.get('status', 'unknown')
        
        if current_status == 'deprecated':
            return False  # Already deprecated
        
        if dry_run:
            return True  # Would change
        
        # Update status to deprecated
        data['status'] = 'deprecated'
        
        with open(case_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
        
    except (json.JSONDecodeError, OSError) as e:
        print(f"         [Error] Failed to process {case_file.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Deprecate rejected case files by updating their status"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making them"
    )
    parser.add_argument(
        "--cases-dir",
        type=str,
        default="data/cases",
        help="Path to cases directory (default: data/cases)"
    )
    parser.add_argument(
        "--evaluations-dir",
        type=str,
        default="data/evaluations/case_evaluations",
        help="Path to case evaluations directory (default: data/evaluations/case_evaluations)"
    )
    
    args = parser.parse_args()
    
    cases_dir = Path(args.cases_dir)
    evaluations_dir = Path(args.evaluations_dir)
    
    # Validate paths
    if not cases_dir.exists():
        print(f"[Error] Cases directory not found: {cases_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not evaluations_dir.exists():
        print(f"[Error] Evaluations directory not found: {evaluations_dir}", file=sys.stderr)
        sys.exit(1)
    
    print("=" * 60)
    print("Phase 2: Deprecate Rejected Cases")
    print("=" * 60)
    
    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")
    
    # Step 1: Load all case IDs and their file paths
    print("\n[Step 1] Loading case IDs from cases directory...")
    case_id_to_path = load_all_case_ids(cases_dir)
    print(f"         Found {len(case_id_to_path)} cases in {cases_dir}")
    
    # Step 2: Load all evaluations
    print("\n[Step 2] Loading evaluations...")
    evaluations_by_case = load_all_evaluations(evaluations_dir)
    print(f"         Found evaluations for {len(evaluations_by_case)} cases")
    
    # Step 3: Identify rejected cases
    print("\n[Step 3] Identifying rejected cases (rejects >= approves OR <2 approvals)...")
    rejected_case_ids = get_rejected_case_ids(evaluations_by_case)
    print(f"         Found {len(rejected_case_ids)} rejected cases")
    
    if not rejected_case_ids:
        print("\n[Done] No rejected cases to deprecate.")
        return
    
    # Step 4: Show evaluation breakdown for rejected cases
    print(f"\n[Step 4] Rejected cases breakdown:")
    
    unanimous_rejects = []
    majority_rejects = []
    tie_rejects = []
    insufficient_approvals = []
    
    for case_id in sorted(rejected_case_ids):
        evals = evaluations_by_case.get(case_id, [])
        approves, rejects = aggregate_decisions(evals)
        
        if case_id not in case_id_to_path:
            print(f"         [Warning] Case {case_id} not found in cases directory (may have been deleted)")
            continue
        
        if approves == 0 and rejects > 0:
            unanimous_rejects.append(case_id)
            category = "unanimous"
        elif rejects > approves:
            majority_rejects.append(case_id)
            category = "majority"
        elif rejects == approves:  # tie goes to rejection
            tie_rejects.append(case_id)
            category = "tie"
        else:  # approves > rejects but < 2 approvals
            insufficient_approvals.append(case_id)
            category = "insufficient (<2 approvals)"
        
        print(f"         - {case_id[:8]}... ({approves} approve / {rejects} reject) [{category}]")
    
    print(f"\n         Summary: {len(unanimous_rejects)} unanimous, {len(majority_rejects)} majority, {len(tie_rejects)} tie, {len(insufficient_approvals)} insufficient approvals")
    
    # Step 5: Deprecate the rejected cases
    print(f"\n[Step 5] {'Would deprecate' if args.dry_run else 'Deprecating'} {len(rejected_case_ids)} cases...")
    
    deprecated_count = 0
    skipped_count = 0
    not_found_count = 0
    error_count = 0
    
    for case_id in rejected_case_ids:
        if case_id not in case_id_to_path:
            not_found_count += 1
            continue
        
        case_file = case_id_to_path[case_id]
        
        result = deprecate_case(case_file, args.dry_run)
        
        if result:
            deprecated_count += 1
            if not args.dry_run:
                print(f"         [Updated] {case_file.name}")
        else:
            # Check if it was already deprecated or an error
            try:
                with open(case_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('status') == 'deprecated':
                    skipped_count += 1
                    print(f"         [Skipped] {case_file.name} (already deprecated)")
                else:
                    error_count += 1
            except Exception:
                error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total cases in directory:   {len(case_id_to_path)}")
    print(f"  Cases with evaluations:     {len(evaluations_by_case)}")
    print(f"  Rejected cases:             {len(rejected_case_ids)}")
    print(f"    - Unanimous rejects:      {len(unanimous_rejects)}")
    print(f"    - Majority rejects:       {len(majority_rejects)}")
    print(f"    - Tie (→ reject):         {len(tie_rejects)}")
    print(f"    - Insufficient approvals: {len(insufficient_approvals)}")
    print(f"  Cases {'to deprecate' if args.dry_run else 'deprecated'}:       {deprecated_count}")
    
    if skipped_count > 0:
        print(f"  Already deprecated:         {skipped_count}")
    if not_found_count > 0:
        print(f"  Not found (deleted?):       {not_found_count}")
    if error_count > 0:
        print(f"  Errors:                     {error_count}")
    
    if args.dry_run:
        print("\n[Note] This was a dry run. Run without --dry-run to execute.")
    else:
        print("\n[Done] Deprecation complete!")


if __name__ == "__main__":
    main()

