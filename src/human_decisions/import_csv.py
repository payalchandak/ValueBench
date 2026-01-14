#!/usr/bin/env python3
"""CLI script for importing human decisions from Qualtrics CSV exports.

This script imports participant responses from Qualtrics survey exports into
the human decisions format, compatible with the DecisionRecord structure used
for LLM decisions.

Usage:
    # Import a CSV file with strict validation (atomic - fails if any response doesn't match)
    uv run python -m src.human_decisions.import_csv survey_responses.csv
    
    # Dry run to preview what would be imported
    uv run python -m src.human_decisions.import_csv survey_responses.csv --dry-run
    
    # Non-strict mode: skip unmatched responses instead of failing
    uv run python -m src.human_decisions.import_csv survey_responses.csv --no-strict
    
    # Custom column names
    uv run python -m src.human_decisions.import_csv survey.csv --name-column "Full Name" --email-column "Email Address"

The script performs atomic imports - if strict mode is enabled (default), the entire
import fails if any response cannot be matched to a valid choice, ensuring data integrity.

Human participants appear in decision files with the key format: human/{participant_id}
"""

import argparse
import sys
from pathlib import Path

from src.human_decisions.importer import (
    parse_qualtrics_csv,
    save_human_decisions,
    HumanResponseValidationError,
)
from src.human_decisions.models import ParticipantRegistry


def print_header():
    """Print the script header."""
    print("=" * 70)
    print("ValueBench Human Decisions Import")
    print("=" * 70)
    print()


def print_parse_result(result, verbose: bool = False):
    """Print a summary of the parse result."""
    print(f"\nParsing Summary:")
    print(f"  Cases found in CSV: {len(result.case_ids_found)}")
    print(f"  Participants: {len(result.participants)}")
    print(f"  Total responses: {len(result.responses)}")
    
    if result.unmatched_responses:
        print(f"\n  ⚠️  Unmatched responses: {len(result.unmatched_responses)}")
        if verbose:
            for case_id, participant_id, response_text in result.unmatched_responses[:5]:
                preview = response_text[:50] + "..." if len(response_text) > 50 else response_text
                print(f"      Case {case_id}: {preview}")
            if len(result.unmatched_responses) > 5:
                print(f"      ... and {len(result.unmatched_responses) - 5} more")
    
    if verbose and result.participants:
        print(f"\n  Participants:")
        for pid, info in list(result.participants.items())[:10]:
            expertise_preview = info.expertise[:30] + "..." if len(info.expertise) > 30 else info.expertise
            print(f"    • {pid}: {info.name} ({expertise_preview or 'no expertise listed'})")
        if len(result.participants) > 10:
            print(f"    ... and {len(result.participants) - 10} more")


def print_save_stats(stats: dict):
    """Print statistics from save operation."""
    print(f"\n✅ Import Complete:")
    print(f"   Cases updated: {stats['cases_updated']}")
    print(f"   Responses saved: {stats['responses_saved']}")
    print(f"   New participants added to registry: {stats['participants_added']}")


def print_registry_info():
    """Print current state of the participant registry."""
    registry = ParticipantRegistry.load()
    
    if len(registry) == 0:
        return
    
    print(f"\n  Participant Registry:")
    print(f"    Total registered participants: {len(registry)}")


def import_csv(
    csv_path: str,
    name_column: str = "Name",
    email_column: str = "Email",
    expertise_column: str = "Expertise",
    timestamp_column: str = "EndDate",
    strict: bool = True,
    dry_run: bool = False,
    verbose: bool = False,
    output_dir: str | None = None,
) -> int:
    """Import human decisions from a Qualtrics CSV file.
    
    Args:
        csv_path: Path to the Qualtrics CSV export file
        name_column: Column header for participant names
        email_column: Column header for participant emails
        expertise_column: Column header for participant expertise/specialty
        timestamp_column: Column header for response timestamp
        strict: If True, fail on any unmatched response (atomic import)
        dry_run: If True, parse and validate without saving
        verbose: If True, print detailed progress information
        output_dir: Custom output directory (default: data/human_decisions/)
        
    Returns:
        Exit code: 0 for success, 1 for error
    """
    print_header()
    
    csv_path = Path(csv_path)
    
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        return 1
    
    print(f"CSV file: {csv_path}")
    print(f"Mode: {'Strict (atomic)' if strict else 'Non-strict (skip unmatched)'}")
    if dry_run:
        print(f"[DRY RUN] No files will be modified")
    print()
    
    # Parse the CSV
    print("Parsing CSV file...")
    try:
        result = parse_qualtrics_csv(
            csv_path=csv_path,
            name_column=name_column,
            email_column=email_column,
            expertise_column=expertise_column,
            timestamp_column=timestamp_column,
            strict=strict,
        )
    except HumanResponseValidationError as e:
        print(f"\n❌ Validation Error:")
        print(f"   {e}")
        print(f"\n   Import aborted (no files were modified).")
        print(f"   Fix the issues above or use --no-strict to skip unmatched responses.")
        return 1
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error during parsing: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return 1
    
    # Print parse results
    print_parse_result(result, verbose=verbose)
    
    if len(result.responses) == 0:
        print(f"\n⚠️  No valid responses found to import.")
        if result.unmatched_responses:
            print(f"   {len(result.unmatched_responses)} responses could not be matched.")
            print(f"   Use --verbose to see details, or check that the CSV columns are correct.")
        return 1
    
    # Dry run: stop here
    if dry_run:
        print(f"\n[DRY RUN] Would import:")
        print(f"   {len(result.responses)} responses")
        print(f"   {len(result.participants)} participants")
        print(f"   Across {len(result.case_ids_found)} cases")
        print(f"\nNo files were modified.")
        return 0
    
    # Save the decisions
    print(f"\nSaving decisions...")
    try:
        stats = save_human_decisions(
            parse_result=result,
            output_dir=output_dir,
        )
    except Exception as e:
        print(f"❌ Error saving decisions: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return 1
    
    print_save_stats(stats)
    print_registry_info()
    
    # Final output directory info
    data_root = Path(__file__).parent.parent.parent / "data"
    actual_output_dir = output_dir if output_dir else data_root / "human_decisions"
    
    print(f"\n   Output directory: {actual_output_dir}")
    print("=" * 70)
    
    return 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Import human decisions from Qualtrics CSV exports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard import with strict validation
  uv run python -m src.human_decisions.import_csv responses.csv

  # Preview what would be imported without making changes
  uv run python -m src.human_decisions.import_csv responses.csv --dry-run

  # Skip unmatched responses instead of failing
  uv run python -m src.human_decisions.import_csv responses.csv --no-strict

  # Verbose output with custom column names
  uv run python -m src.human_decisions.import_csv responses.csv \\
      --name-column "Participant Name" \\
      --email-column "Email Address" \\
      --verbose

Column Mapping:
  The CSV is expected to have columns for participant info and case responses.
  Case response columns should have headers in format: "{uuid} - {vignette_text}"
  Response values must exactly match choice_1.choice or choice_2.choice from cases.

Atomic Import (Strict Mode):
  By default, the import is atomic - if ANY response cannot be matched to a valid
  choice, the entire import fails and no files are modified. This ensures data
  integrity. Use --no-strict to skip unmatched responses and import what's valid.
        """
    )
    
    # Required argument
    parser.add_argument(
        "csv_file",
        help="Path to the Qualtrics CSV export file"
    )
    
    # Column name options
    parser.add_argument(
        "--name-column",
        default="Name",
        help="Column header for participant names (default: 'Name')"
    )
    parser.add_argument(
        "--email-column",
        default="Email",
        help="Column header for participant emails (default: 'Email')"
    )
    parser.add_argument(
        "--expertise-column",
        default="Expertise",
        help="Column header for participant expertise/specialty (default: 'Expertise')"
    )
    parser.add_argument(
        "--timestamp-column",
        default="EndDate",
        help="Column header for response timestamp (default: 'EndDate')"
    )
    
    # Mode options
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Skip unmatched responses instead of failing (non-atomic import)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without saving any files"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed progress information"
    )
    
    # Output options
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Custom output directory (default: data/human_decisions/)"
    )
    
    args = parser.parse_args()
    
    try:
        exit_code = import_csv(
            csv_path=args.csv_file,
            name_column=args.name_column,
            email_column=args.email_column,
            expertise_column=args.expertise_column,
            timestamp_column=args.timestamp_column,
            strict=not args.no_strict,
            dry_run=args.dry_run,
            verbose=args.verbose,
            output_dir=args.output_dir,
        )
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nImport cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
