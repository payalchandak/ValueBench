#!/usr/bin/env python3
"""
Example: Building a simple CLI on top of case_loader and evaluation_store

This demonstrates how to use the modular components to build
your rich/prompt_toolkit-based evaluator.
"""

import os
import random
from src.case_loader import CaseLoader
from src.evaluation_store import EvaluationStore
from src.response_models.case import BenchmarkCandidate, ChoiceWithValues
from src.response_models.status import GenerationStatus


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
    username = input("\nEnter your username (lowercase letters only): ").strip()
    if not username:
        print("Error: Username required")
        return
    
    session = store.load_or_create_session(username)
    
    # Step 3: Get unreviewed cases (only completed benchmark candidates with value tags)
    all_cases = loader.get_cases_by_status(GenerationStatus.COMPLETED)  # Only load completed cases
    # Filter to only include cases with complete value tagging (BenchmarkCandidate)
    benchmark_cases = [c for c in all_cases if c.final_case is not None]
    all_case_ids = [c.case_id for c in benchmark_cases]
    unreviewed_ids = store.get_unreviewed_cases(all_case_ids)
    
    # Randomize case order to avoid evaluation bias
    random.shuffle(unreviewed_ids)
    
    print(f"\n📊 Progress: {len(benchmark_cases) - len(unreviewed_ids)}/{len(benchmark_cases)} benchmark cases reviewed")
    if len(all_cases) > len(benchmark_cases):
        print(f"   (Note: {len(all_cases) - len(benchmark_cases)} draft cases without value tags are excluded)")
    
    if not unreviewed_ids:
        print("\n✓ All cases have been reviewed!")
        show_statistics(store, loader)
        return
    
    # Step 4: Review loop - Keep reviewing until user quits or all cases done
    print(f"\n{len(unreviewed_ids)} case(s) remaining to review")
    print("\nStarting review session...")
    print("(Press 'q' at any time to quit)")
    input("\nPress Enter to begin...")
    
    cases_reviewed_this_session = 0
    
    for idx, case_id in enumerate(unreviewed_ids):
        # Refresh unreviewed list dynamically
        all_case_ids = [c.case_id for c in benchmark_cases]
        current_unreviewed = store.get_unreviewed_cases(all_case_ids)
        
        # Skip if already reviewed
        if case_id not in current_unreviewed:
            continue
        
        case = loader.get_case_by_id(case_id)
        
        # Only evaluate benchmark candidates with value tags, not draft cases
        if not case or not case.final_case:
            print(f"\n⚠️  Skipping case {case_id[:12]}... - Not a complete benchmark candidate with value tags")
            continue
            
        final = case.final_case
        
        # Clear screen and show fresh case
        os.system('clear' if os.name != 'nt' else 'cls')
        
        # Show header with progress
        print("=" * 70)
        print("CASE EVALUATOR - Review Session")
        print("=" * 70)
        print(f"Progress: {len(benchmark_cases) - len(current_unreviewed)}/{len(benchmark_cases)} cases reviewed")
        print(f"This session: {cases_reviewed_this_session} cases reviewed")
        print(f"Remaining: {len(current_unreviewed)} cases")
        
        # Display case (in rich, this would be a beautiful panel)
        print("\n" + "─" * 70)
        print(f"CASE: {case_id[:12]}... ({idx + 1}/{len(unreviewed_ids)})")
        print("─" * 70)
        print(f"\nVIGNETTE:\n{final.vignette}\n")
        
        # Display Choice 1 with value tags
        print("CHOICE 1:")
        print(f"  {final.choice_1.choice}")
        print(f"  Value Alignments:")
        print(f"    • Autonomy:       {final.choice_1.autonomy}")
        print(f"    • Beneficence:    {final.choice_1.beneficence}")
        print(f"    • Nonmaleficence: {final.choice_1.nonmaleficence}")
        print(f"    • Justice:        {final.choice_1.justice}")
        print()
        
        # Display Choice 2 with value tags
        print("CHOICE 2:")
        print(f"  {final.choice_2.choice}")
        print(f"  Value Alignments:")
        print(f"    • Autonomy:       {final.choice_2.autonomy}")
        print(f"    • Beneficence:    {final.choice_2.beneficence}")
        print(f"    • Nonmaleficence: {final.choice_2.nonmaleficence}")
        print(f"    • Justice:        {final.choice_2.justice}")
        print()
        
        print("─" * 70)
        
        # Review options (in prompt_toolkit, this would be an interactive menu)
        print("\nOptions:")
        print("  [a] Approve")
        print("  [r] Reject")
        print("  [q] Quit (case will remain unreviewed)")
        
        decision = input("\nYour choice: ").strip().lower()
        
        if decision == 'q':
            print("\nQuitting...")
            break
            
        elif decision in ['a', 'r']:
            decision_text = "approve" if decision == 'a' else "reject"
            
            # Collect feedback (same for both approve and reject)
            print("\n" + "─" * 70)
            print(f"FEEDBACK - {decision_text.upper()}")
            print("─" * 70)
            
            # Problem axes (optional)
            print("\nProblem categories (select all that apply, or press Enter to skip):")
            print("  [c] Clinical - Medical accuracy, diagnosis, treatment")
            print("  [e] Ethical - Ethical principles, value conflicts")
            print("  [l] Legal - Legal compliance, regulations")
            print("  [s] Stylistic - Writing quality, tone, structure")
            print("  [o] Other - Other issues")
            
            axes_input = input("\nEnter letters (e.g., 'ce' for clinical+ethical): ").strip().lower()
            problem_axes = None
            
            if axes_input:
                axis_map = {
                    'c': 'clinical',
                    'e': 'ethical',
                    'l': 'legal',
                    's': 'stylistic',
                    'o': 'other'
                }
                
                # Collect valid axes, ignoring spaces and invalid characters
                problem_axes = []
                for char in axes_input:
                    if char in axis_map and axis_map[char] not in problem_axes:
                        problem_axes.append(axis_map[char])
                
                # If any valid categories selected, show confirmation
                if problem_axes:
                    print(f"  Selected: {', '.join(problem_axes)}")
                else:
                    problem_axes = None
            
            # Detailed comments (required for reject, optional for approve)
            if decision == 'r':
                print("\nDetailed comments (required):")
                comments = input("> ").strip()
                
                # Require comments for rejections
                while not comments:
                    print("⚠️  Comments are required for rejections")
                    comments = input("> ").strip()
            else:
                print("\nDetailed comments (optional, press Enter to skip):")
                comments = input("> ").strip() or None
            
            store.record_evaluation(
                case_id=case_id,
                decision=decision_text,
                case_loader=loader,
                problem_axes=problem_axes,
                comments=comments
            )
            cases_reviewed_this_session += 1
            
            # Format success message based on whether feedback was provided
            past_tense = "Approved" if decision == 'a' else "Rejected"
            has_feedback = bool(problem_axes or comments)
            feedback_msg = " with feedback" if has_feedback else ""
            print(f"✓ {past_tense}{feedback_msg}")
            input("\nPress Enter to continue to next case...")
        
        else:
            print("Invalid option - skipping case")
            input("\nPress Enter to continue...")
    
    # Clear screen and show final statistics
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 70)
    print("REVIEW SESSION COMPLETE")
    print("=" * 70)
    print(f"\n✓ Reviewed {cases_reviewed_this_session} case(s) this session")
    
    # Show overall statistics
    show_statistics(store, loader)
    
    # Check if there are more cases to review
    all_case_ids = [c.case_id for c in benchmark_cases]
    remaining = store.get_unreviewed_cases(all_case_ids)
    
    if remaining:
        print(f"\n📋 {len(remaining)} case(s) still pending review")
        print("   Run this script again to continue.")
    else:
        print("\n🎉 All cases have been reviewed!")
    
    print("\n" + "=" * 70)
    print("Session saved.")
    print("=" * 70)


def show_statistics(store, loader):
    """Display evaluation statistics."""
    stats = store.get_statistics(loader)
    print("\n📈 Statistics:")
    print(f"  Total reviewed: {stats['total_reviewed']}")
    print(f"  ✓ Approved:     {stats['approved']}")
    print(f"  ✗ Rejected:     {stats['rejected']}")
    
    # Show feedback summary
    if stats.get('with_feedback', 0) > 0:
        print(f"  💬 With feedback: {stats['with_feedback']}")
    
    if stats.get('problem_axes_summary'):
        print("\n  Problem categories identified:")
        for axis, count in stats['problem_axes_summary'].items():
            print(f"    • {axis.capitalize()}: {count}")


if __name__ == "__main__":
    try:
        simple_cli_demo()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Session saved.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

