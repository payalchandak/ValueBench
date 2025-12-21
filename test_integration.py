#!/usr/bin/env python3
"""
Integration test demonstrating case_loader and evaluation_store working together.
"""

from src.case_loader import CaseLoader, CaseLoadError
from src.evaluation_store import EvaluationStore


def main():
    print("=" * 80)
    print("Case Evaluator - Integration Test")
    print("=" * 80)
    
    # Step 1: Load cases
    print("\n[1] Loading cases...")
    try:
        loader = CaseLoader("data/cases")
        cases = loader.get_all_cases()
        print(f"✓ Found {len(cases)} cases")
        
        for i, case in enumerate(cases[:3], 1):
            print(f"  {i}. {case.case_id[:8]}...")
    
    except CaseLoadError as e:
        print(f"✗ Error loading cases: {e}")
        return
    
    # Step 2: Create evaluation session
    print("\n[2] Setting up evaluation session...")
    store = EvaluationStore("data/evaluations")
    
    email = input("Enter your email: ").strip()
    session = store.load_or_create_session(email)
    
    print(f"✓ Session loaded: {session.session_id}")
    
    # Step 3: Show unreviewed cases
    print("\n[3] Checking review status...")
    all_case_ids = [c.case_id for c in cases]
    unreviewed = store.get_unreviewed_cases(all_case_ids)
    
    print(f"✓ Total cases: {len(cases)}")
    print(f"  - Reviewed: {len(cases) - len(unreviewed)}")
    print(f"  - Unreviewed: {len(unreviewed)}")
    
    # Step 4: Simulate reviewing the first case (if any unreviewed)
    if unreviewed:
        print("\n[4] Simulating review of first unreviewed case...")
        first_case_id = unreviewed[0]
        
        # Load full case data as CaseRecord
        case = loader.get_case_by_id(first_case_id)
        if case and case.final_case:
            final = case.final_case
            
            print(f"  Case ID: {first_case_id}")
            print(f"  Vignette preview: {final.vignette[:100]}...")
            
            # Simulate approval with a minor edit
            store.add_evaluation(
                case_id=first_case_id,
                decision="approve",
                original_vignette=final.vignette,
                original_choice_1=final.choice_1.choice,
                original_choice_2=final.choice_2.choice,
                edited_vignette=final.vignette,  # No actual edit in this demo
                notes="Test evaluation - looks good!"
            )
            
            print(f"✓ Evaluation saved")
    else:
        print("\n[4] No unreviewed cases available")
    
    # Step 5: Show statistics
    print("\n[5] Evaluation statistics:")
    stats = store.get_statistics()
    print(f"  - Total reviewed: {stats['total_reviewed']}")
    print(f"  - Approved: {stats['approved']}")
    print(f"  - Rejected: {stats['rejected']}")
    print(f"  - Pending: {stats['pending']}")
    print(f"  - With edits: {stats['with_edits']}")
    
    # Step 6: List all sessions
    print("\n[6] All evaluation sessions:")
    all_sessions = store.list_all_sessions()
    if all_sessions:
        for s in all_sessions:
            print(f"  - {s['email']}: {s['num_evaluations']} evaluations")
            print(f"    Last updated: {s['last_updated'][:19]}")
    else:
        print("  (No sessions found)")
    
    print("\n" + "=" * 80)
    print("✓ Integration test complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()

