#!/usr/bin/env python3
"""
Example: Building a simple CLI on top of case_loader and evaluation_store

This demonstrates how to use the modular components to build
your rich/prompt_toolkit-based evaluator.
"""

from src.case_loader import CaseLoader
from src.evaluation_store import EvaluationStore


def simple_cli_demo():
    """
    Minimal CLI demonstration showing the basic workflow.
    
    In a full implementation, you would replace the print statements
    with rich panels/tables and the input() calls with prompt_toolkit
    widgets for a beautiful, interactive UI.
    """
    
    print("=" * 70)
    print("CASE EVALUATOR - Simple CLI Demo")
    print("=" * 70)
    
    # Step 1: Initialize modules
    loader = CaseLoader("data/cases")
    store = EvaluationStore("data/evaluations")
    
    # Step 2: User identification
    email = input("\nEnter your email: ").strip()
    if not email:
        print("Error: Email required")
        return
    
    session = store.load_or_create_session(email)
    
    # Step 3: Get unreviewed cases
    all_cases = loader.get_all_cases()
    all_case_ids = [c.case_id for c in all_cases]
    unreviewed_ids = store.get_unreviewed_cases(all_case_ids)
    
    print(f"\n📊 Progress: {len(all_cases) - len(unreviewed_ids)}/{len(all_cases)} cases reviewed")
    
    if not unreviewed_ids:
        print("\n✓ All cases have been reviewed!")
        show_statistics(store)
        return
    
    # Step 4: Review loop
    print(f"\n{len(unreviewed_ids)} case(s) remaining to review")
    print("\nStarting review session...")
    print("(In a full UI, you'd see rich panels with syntax highlighting)")
    
    for case_id in unreviewed_ids[:1]:  # Just show first case in demo
        case = loader.get_case_by_id(case_id)
        
        if not case or not case.final_case:
            continue
            
        final = case.final_case
        
        # Display case (in rich, this would be a beautiful panel)
        print("\n" + "─" * 70)
        print(f"CASE: {case_id[:12]}...")
        print("─" * 70)
        print(f"\nVIGNETTE:\n{final.vignette}\n")
        print(f"CHOICE 1:\n{final.choice_1.choice}\n")
        print(f"CHOICE 2:\n{final.choice_2.choice}\n")
        print("─" * 70)
        
        # Review options (in prompt_toolkit, this would be an interactive menu)
        print("\nOptions:")
        print("  [a] Approve as-is")
        print("  [e] Edit then approve")
        print("  [r] Reject")
        print("  [s] Skip for now")
        print("  [q] Quit")
        
        decision = input("\nYour choice: ").strip().lower()
        
        if decision == 'a':
            store.add_evaluation(
                case_id=case_id,
                decision="approve",
                original_vignette=final.vignette,
                original_choice_1=final.choice_1.choice,
                original_choice_2=final.choice_2.choice
            )
            print("✓ Approved")
        
        elif decision == 'e':
            print("\n(In full UI, you'd get a text editor with prompt_toolkit)")
            edited = input("Enter edited vignette (or press Enter to skip): ").strip()
            
            store.add_evaluation(
                case_id=case_id,
                decision="approve",
                original_vignette=final.vignette,
                original_choice_1=final.choice_1.choice,
                original_choice_2=final.choice_2.choice,
                edited_vignette=edited if edited else None,
                notes="Manually edited"
            )
            print("✓ Approved with edits")
        
        elif decision == 'r':
            notes = input("Rejection reason: ").strip()
            store.add_evaluation(
                case_id=case_id,
                decision="reject",
                original_vignette=final.vignette,
                original_choice_1=final.choice_1.choice,
                original_choice_2=final.choice_2.choice,
                notes=notes
            )
            print("✓ Rejected")
        
        elif decision == 's':
            store.add_evaluation(
                case_id=case_id,
                decision="pending",
                original_vignette=final.vignette,
                original_choice_1=final.choice_1.choice,
                original_choice_2=final.choice_2.choice,
                notes="Skipped for later review"
            )
            print("⏭ Skipped")
        
        elif decision == 'q':
            print("\nQuitting...")
            break
        
        else:
            print("Invalid option")
    
    # Show statistics
    show_statistics(store)
    print("\n" + "=" * 70)
    print("Session saved. Run again to continue reviewing.")
    print("=" * 70)


def extract_choice_text(choice_data):
    """Extract choice text from either string or dict format."""
    if isinstance(choice_data, str):
        return choice_data
    elif isinstance(choice_data, dict):
        return choice_data.get('choice', '')
    return ''


def show_statistics(store):
    """Display evaluation statistics."""
    stats = store.get_statistics()
    print("\n📈 Statistics:")
    print(f"  Total reviewed: {stats['total_reviewed']}")
    print(f"  ✓ Approved:     {stats['approved']}")
    print(f"  ✗ Rejected:     {stats['rejected']}")
    print(f"  ⏸ Pending:      {stats['pending']}")
    print(f"  ✏ With edits:   {stats['with_edits']}")


if __name__ == "__main__":
    try:
        simple_cli_demo()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Session saved.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

