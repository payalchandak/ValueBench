"""
Export ValueBench cases to Google Sheets for collaborative editing.

Run with: uv run python -m src.sheets.export_to_sheets

Options:
    --append     Add only new cases (default: replace all)
    --dry-run    Show what would be exported without writing to Sheets

This module also exposes reusable functions for the sync module:
    - load_cases_raw(): Load all case JSON files from a directory
    - extract_case_row(): Convert a case dict to a spreadsheet row
    - get_header_row(): Get the standard header row
    - get_sheet_case_ids(): Fetch all case IDs currently in the sheet
    - push_rows_to_sheet(): Append rows to the sheet
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import gspread

from src.sheets.utils import load_config, get_gspread_client, open_spreadsheet, get_worksheet


def load_cases_raw(cases_dir: str) -> list[dict]:
    """
    Load all case JSON files directly without strict Pydantic validation.
    
    This is more lenient with schema variations that may exist in older files.
    
    Args:
        cases_dir: Path to the cases directory
        
    Returns:
        List of raw case dictionaries
    """
    cases_path = Path(cases_dir)
    if not cases_path.exists():
        raise FileNotFoundError(f"Cases directory not found: {cases_path}")
    
    cases = []
    json_files = sorted(cases_path.glob("case_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                case_data = json.load(f)
                case_data['_file_path'] = str(file_path)  # Keep track of source file
                cases.append(case_data)
        except json.JSONDecodeError as e:
            print(f"  [Warning] Invalid JSON in {file_path.name}: {e}")
        except Exception as e:
            print(f"  [Warning] Error loading {file_path.name}: {e}")
    
    return cases


def extract_case_row(case_data: dict, config: dict) -> Optional[list]:
    """
    Extract a single row of data from a raw case dictionary.
    
    Looks through refinement_history to find the last iteration with
    value-tagged choices (BenchmarkCandidate format).
    
    Returns:
        List of values matching the column order in the config, or None if
        the case doesn't have valid final data with value tags.
    """
    case_id = case_data.get("case_id", "unknown")
    refinement_history = case_data.get("refinement_history", [])
    
    if not refinement_history:
        return None
    
    # Find the last iteration with value-tagged choices
    # Look for iterations where choice_1/choice_2 are objects with value tags
    final_data = None
    final_human_evaluation = None
    for iteration in reversed(refinement_history):
        data = iteration.get("data", {})
        choice_1 = data.get("choice_1")
        choice_2 = data.get("choice_2")
        
        # Check if this has value tags (BenchmarkCandidate format)
        if isinstance(choice_1, dict) and "autonomy" in choice_1:
            final_data = data
            # Get the human_evaluation from this or the most recent iteration that has it
            final_human_evaluation = iteration.get("human_evaluation")
            break
    
    # If no human_evaluation found in the final data iteration, look for the most recent one
    if not final_human_evaluation:
        for iteration in reversed(refinement_history):
            if iteration.get("human_evaluation"):
                final_human_evaluation = iteration.get("human_evaluation")
                break
    
    if not final_data:
        return None
    
    # Extract data
    vignette = final_data.get("vignette", "")
    choice_1 = final_data.get("choice_1", {})
    choice_2 = final_data.get("choice_2", {})
    
    # Extract choice text and value tags
    c1_text = choice_1.get("choice", "") if isinstance(choice_1, dict) else str(choice_1)
    c1_autonomy = choice_1.get("autonomy", "neutral") if isinstance(choice_1, dict) else "neutral"
    c1_beneficence = choice_1.get("beneficence", "neutral") if isinstance(choice_1, dict) else "neutral"
    c1_nonmaleficence = choice_1.get("nonmaleficence", "neutral") if isinstance(choice_1, dict) else "neutral"
    c1_justice = choice_1.get("justice", "neutral") if isinstance(choice_1, dict) else "neutral"
    
    c2_text = choice_2.get("choice", "") if isinstance(choice_2, dict) else str(choice_2)
    c2_autonomy = choice_2.get("autonomy", "neutral") if isinstance(choice_2, dict) else "neutral"
    c2_beneficence = choice_2.get("beneficence", "neutral") if isinstance(choice_2, dict) else "neutral"
    c2_nonmaleficence = choice_2.get("nonmaleficence", "neutral") if isinstance(choice_2, dict) else "neutral"
    c2_justice = choice_2.get("justice", "neutral") if isinstance(choice_2, dict) else "neutral"
    
    # Extract reviewer feedback from human_evaluation if present
    r1_name = ""
    r1_decision = ""
    r2_name = ""
    r2_decision = ""
    r3_name = ""
    r3_decision = ""
    reviewer_comments = ""
    
    if final_human_evaluation:
        reviewers = final_human_evaluation.get("reviewers", {})
        
        r1_info = reviewers.get("r1", {})
        r1_name = r1_info.get("name", "") if isinstance(r1_info, dict) else ""
        r1_decision = r1_info.get("decision", "") if isinstance(r1_info, dict) else ""
        
        r2_info = reviewers.get("r2", {})
        r2_name = r2_info.get("name", "") if isinstance(r2_info, dict) else ""
        r2_decision = r2_info.get("decision", "") if isinstance(r2_info, dict) else ""
        
        r3_info = reviewers.get("r3", {})
        r3_name = r3_info.get("name", "") if isinstance(r3_info, dict) else ""
        r3_decision = r3_info.get("decision", "") if isinstance(r3_info, dict) else ""
        
        reviewer_comments = final_human_evaluation.get("comments", "")
    
    # Get case status from the case data
    case_status = case_data.get("status", "draft")
    
    # Build row in column order: case_id, R1, R1 Decision?, R2, R2 Decision?, R3, R3 Decision?, Status, vignette, choice_1, c1_values..., choice_2, c2_values..., reviewer comments
    row = [
        case_id,
        r1_name,
        r1_decision,
        r2_name,
        r2_decision,
        r3_name,
        r3_decision,
        case_status,
        vignette,
        c1_text,
        c1_autonomy,
        c1_beneficence,
        c1_nonmaleficence,
        c1_justice,
        c2_text,
        c2_autonomy,
        c2_beneficence,
        c2_nonmaleficence,
        c2_justice,
        reviewer_comments,
    ]
    
    return row


def get_header_row() -> list:
    """Return the header row for the spreadsheet."""
    return [
        "Case ID",
        "R1",
        "R1 Decision?",
        "R2",
        "R2 Decision?",
        "R3",
        "R3 Decision?",
        "Status",
        "Vignette",
        "Choice 1",
        "Autonomy C1",
        "Beneficence C1",
        "Nonmaleficence C1",
        "Justice C1",
        "Choice 2",
        "Autonomy C2",
        "Beneficence C2",
        "Nonmaleficence C2",
        "Justice C2",
        "Reviewer Comments",
    ]


def setup_data_validation(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet, num_rows: int, config: dict):
    """
    Set up dropdown validation for value tag columns.
    
    Uses the Google Sheets API batch update for data validation rules.
    
    Note: Status column does NOT get a dropdown because it's computed from reviewer
    decisions during import/sync, not user-editable.
    
    Args:
        spreadsheet: The gspread Spreadsheet object
        worksheet: The gspread Worksheet object
        num_rows: Total number of data rows (excluding header)
        config: Configuration dictionary with value_options
    """
    value_options = config.get("value_options", ["promotes", "violates", "neutral"])
    
    # Column layout (0-indexed):
    # 0=Case ID, 1=R1, 2=R1 Decision?, 3=R2, 4=R2 Decision?, 5=R3, 6=R3 Decision?, 
    # 7=Status, 8=Vignette, 9=Choice 1, 10-13=C1 values, 14=Choice 2, 15-18=C2 values, 19=Comments
    # Value tag columns: K, L, M, N for choice_1 (indices 10-13) and P, Q, R, S for choice_2 (indices 15-18)
    # Note: These indices must match the header order from get_header_row()
    value_columns = [10, 11, 12, 13, 15, 16, 17, 18]  # 0-indexed
    
    if num_rows == 0:
        return
    
    # Build requests for batch update
    # Row indices are 0-based, and we start from row 1 (after header at row 0)
    start_row_idx = 1  # 0-indexed (row 2 in spreadsheet)
    end_row_idx = start_row_idx + num_rows  # Exclusive end
    
    sheet_id = worksheet.id
    requests = []
    
    # Create data validation rule for value tag columns
    print("  Setting up value tag dropdowns...")
    for col_idx in value_columns:
        rule = {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row_idx,
                    "endRowIndex": end_row_idx,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in value_options]
                    },
                    "showCustomUi": True,
                    "strict": True
                }
            }
        }
        requests.append(rule)
    
    # Execute batch update
    if requests:
        spreadsheet.batch_update({"requests": requests})


def format_header(worksheet: gspread.Worksheet):
    """Apply formatting to the header row."""
    # Bold the header row and freeze it (20 columns: A through T)
    worksheet.format("A1:T1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
    })
    worksheet.freeze(rows=1)


def format_columns(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet, num_rows: int):
    """
    Apply column formatting for readability:
    - Set appropriate column widths
    - Enable text wrapping for vignette and choice columns
    
    Args:
        spreadsheet: The gspread Spreadsheet object
        worksheet: The gspread Worksheet object
        num_rows: Total number of data rows (excluding header)
    """
    sheet_id = worksheet.id
    
    # Column layout (0-indexed):
    # A(0)=Case ID, B(1)=R1, C(2)=R1 Decision?, D(3)=R2, E(4)=R2 Decision?, 
    # F(5)=R3, G(6)=R3 Decision?, H(7)=Status, I(8)=Vignette, J(9)=Choice 1,
    # K-N(10-13)=C1 values, O(14)=Choice 2, P-S(15-18)=C2 values, T(19)=Comments
    column_widths = [
        (0, 150),   # A: case_id
        (1, 80),    # B: R1
        (2, 100),   # C: R1 Decision?
        (3, 80),    # D: R2
        (4, 100),   # E: R2 Decision?
        (5, 80),    # F: R3
        (6, 100),   # G: R3 Decision?
        (7, 90),    # H: Status
        (8, 500),   # I: Vignette
        (9, 300),   # J: Choice 1
        (10, 100),  # K: c1_autonomy
        (11, 100),  # L: c1_beneficence
        (12, 120),  # M: c1_nonmaleficence
        (13, 100),  # N: c1_justice
        (14, 300),  # O: Choice 2
        (15, 100),  # P: c2_autonomy
        (16, 100),  # Q: c2_beneficence
        (17, 120),  # R: c2_nonmaleficence
        (18, 100),  # S: c2_justice
        (19, 200),  # T: Reviewer Comments
    ]
    
    requests = []
    
    # Set column widths
    for col_idx, width in column_widths:
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": col_idx,
                    "endIndex": col_idx + 1
                },
                "properties": {
                    "pixelSize": width
                },
                "fields": "pixelSize"
            }
        })
    
    # Enable text wrapping for vignette (I=8), choice_1 (J=9), choice_2 (O=14), comments (T=19)
    text_wrap_columns = [8, 9, 14, 19]  # 0-indexed
    for col_idx in text_wrap_columns:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,  # Skip header
                    "endRowIndex": num_rows + 1,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat.wrapStrategy"
            }
        })
    
    # Execute batch update
    if requests:
        spreadsheet.batch_update({"requests": requests})


# =============================================================================
# Reusable functions for sync module
# =============================================================================

def get_sheet_case_ids(
    config: Optional[dict] = None,
    spreadsheet: Optional[gspread.Spreadsheet] = None,
    worksheet: Optional[gspread.Worksheet] = None
) -> set[str]:
    """
    Fetch all case IDs currently in the Google Sheet.
    
    This function is used by the sync module to determine which cases
    already exist in the sheet vs which are local-only.
    
    Args:
        config: Optional config dict. If not provided, loads from file.
        spreadsheet: Optional spreadsheet object. If not provided, opens from config.
        worksheet: Optional worksheet object. If not provided, gets from spreadsheet.
        
    Returns:
        Set of case IDs (strings) found in the sheet.
    """
    if config is None:
        config = load_config()
    
    if spreadsheet is None:
        spreadsheet = open_spreadsheet(config)
    
    if worksheet is None:
        try:
            worksheet = get_worksheet(spreadsheet, config=config)
        except gspread.exceptions.WorksheetNotFound:
            # Sheet doesn't exist yet, no cases
            return set()
    
    # Get all values from the sheet
    all_values = worksheet.get_all_values()
    
    if len(all_values) < 2:
        # Only header or empty
        return set()
    
    # Case ID is in the first column (index 0)
    # Skip header row (index 0)
    case_ids = {row[0].strip() for row in all_values[1:] if row and row[0].strip()}
    
    return case_ids


def push_rows_to_sheet(
    rows: list[list],
    config: Optional[dict] = None,
    spreadsheet: Optional[gspread.Spreadsheet] = None,
    worksheet: Optional[gspread.Worksheet] = None,
    include_header: bool = False
) -> int:
    """
    Append rows to the Google Sheet.
    
    This function is used by the sync module to push new local cases to the sheet.
    It appends rows to the existing data rather than replacing.
    
    Args:
        rows: List of row data to append (each row is a list of cell values).
        config: Optional config dict. If not provided, loads from file.
        spreadsheet: Optional spreadsheet object. If not provided, opens from config.
        worksheet: Optional worksheet object. If not provided, gets from spreadsheet.
        include_header: If True and worksheet is empty, prepend header row.
        
    Returns:
        Number of rows successfully appended.
    """
    if not rows:
        return 0
    
    if config is None:
        config = load_config()
    
    if spreadsheet is None:
        spreadsheet = open_spreadsheet(config)
    
    if worksheet is None:
        worksheet = get_worksheet(spreadsheet, config=config, create_if_missing=True)
    
    # Check if worksheet is empty (needs header)
    existing_data = worksheet.get_all_values()
    
    if include_header and len(existing_data) == 0:
        # Worksheet is empty, add header first
        all_data = [get_header_row()] + rows
        worksheet.update(values=all_data, range_name="A1", value_input_option="RAW")
    else:
        # Append to existing data
        worksheet.append_rows(rows, value_input_option="RAW")
    
    return len(rows)


def prepare_cases_for_export(
    cases_dir: str = "data/cases",
    config: Optional[dict] = None
) -> tuple[list[list], list[str]]:
    """
    Load local cases and prepare them as rows for export.
    
    This function is used by both the export command and the sync module.
    
    Args:
        cases_dir: Path to the cases directory.
        config: Optional config dict for extraction settings.
        
    Returns:
        Tuple of (rows, skipped_case_ids):
        - rows: List of exportable rows (each row is a list of cell values)
        - skipped_case_ids: List of case IDs that were skipped (no finalized data)
    """
    if config is None:
        config = load_config()
    
    all_cases = load_cases_raw(cases_dir)
    
    rows = []
    skipped = []
    
    for case_data in all_cases:
        row = extract_case_row(case_data, config)
        if row:
            rows.append(row)
        else:
            skipped.append(case_data.get("case_id", "unknown"))
    
    return rows, skipped


def export_cases(
    append: bool = False,
    dry_run: bool = False,
    cases_dir: str = "data/cases"
) -> int:
    """
    Export cases from local JSON files to Google Sheets.
    
    Args:
        append: If True, only add new cases. If False, replace all data.
        dry_run: If True, show what would be exported without writing.
        cases_dir: Path to the cases directory.
        
    Returns:
        Number of cases exported.
    """
    print("=" * 60)
    print("ValueBench Case Export to Google Sheets")
    print("=" * 60)
    print()
    
    # Load configuration
    print("Loading configuration...")
    config = load_config()
    spreadsheet_id = config.get("spreadsheet_id")
    sheet_name = config.get("sheet_name", "Cases")
    
    if not spreadsheet_id:
        print("❌ No spreadsheet_id configured in sheets_config.yaml")
        print("   Create a Google Sheet and add its ID to the config file.")
        return 0
    
    # Load cases directly from JSON (bypasses strict Pydantic validation)
    print(f"Loading cases from {cases_dir}...")
    all_cases = load_cases_raw(cases_dir)
    print(f"  Found {len(all_cases)} total case files")
    
    # Extract exportable rows
    rows = []
    skipped = []
    for case_data in all_cases:
        row = extract_case_row(case_data, config)
        if row:
            rows.append(row)
        else:
            skipped.append(case_data.get("case_id", "unknown"))
    
    print(f"  {len(rows)} cases ready for export")
    if skipped:
        print(f"  {len(skipped)} cases skipped (no finalized data)")
    
    if not rows:
        print("\n❌ No cases to export.")
        return 0
    
    # Dry run - just show what would be exported
    if dry_run:
        print("\n[DRY RUN] Would export the following cases:")
        print("-" * 60)
        for row in rows[:10]:  # Show first 10
            print(f"  • {row[0]}: {row[1][:50]}...")
        if len(rows) > 10:
            print(f"  ... and {len(rows) - 10} more cases")
        print("-" * 60)
        print(f"\nTotal: {len(rows)} cases would be exported to:")
        print(f"  https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        return len(rows)
    
    # Connect to Google Sheets
    print("\nConnecting to Google Sheets...")
    gc = get_gspread_client(config)
    
    try:
        spreadsheet = gc.open_by_key(spreadsheet_id)
        print(f"  Connected to: {spreadsheet.title}")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ Spreadsheet not found. Make sure:")
        print(f"   1. The spreadsheet ID is correct: {spreadsheet_id}")
        print(f"   2. The spreadsheet is shared with the service account")
        return 0
    
    # Get or create the worksheet
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        print(f"  Using existing worksheet: {sheet_name}")
    except gspread.exceptions.WorksheetNotFound:
        print(f"  Creating new worksheet: {sheet_name}")
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(rows) + 100, cols=20)
    
    # Remove default "Sheet1" if it exists and we have our Cases sheet
    try:
        sheet1 = spreadsheet.worksheet("Sheet1")
        # Only delete if there's more than one worksheet
        if len(spreadsheet.worksheets()) > 1:
            print("  Removing default 'Sheet1' tab...")
            spreadsheet.del_worksheet(sheet1)
    except gspread.exceptions.WorksheetNotFound:
        pass  # Sheet1 doesn't exist, nothing to do
    
    # Handle append mode
    existing_ids = set()
    if append:
        print("\nChecking for existing cases...")
        existing_data = worksheet.get_all_values()
        if len(existing_data) > 1:  # Has header + data
            existing_ids = {row[0] for row in existing_data[1:] if row}
            print(f"  Found {len(existing_ids)} existing cases")
            # Filter to only new cases
            rows = [row for row in rows if row[0] not in existing_ids]
            print(f"  {len(rows)} new cases to add")
            
            if not rows:
                print("\n✅ No new cases to add. Sheet is up to date.")
                return 0
    
    # Prepare data for upload
    include_header = config.get("export", {}).get("include_header", True)
    
    if append and existing_ids:
        # Append mode with existing data - just add new rows
        print(f"\nAppending {len(rows)} new cases...")
        worksheet.append_rows(rows, value_input_option="RAW")
    else:
        # Full replace mode
        print(f"\nWriting {len(rows)} cases to sheet...")
        
        # Clear existing data and formatting
        worksheet.clear()
        
        # Clear all data validation rules
        print("  Clearing any existing dropdowns...")
        sheet_id = worksheet.id
        clear_validation_request = {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id
                },
                "rule": None
            }
        }
        spreadsheet.batch_update({"requests": [clear_validation_request]})
        
        # Prepare all data including header
        all_data = []
        if include_header:
            all_data.append(get_header_row())
        all_data.extend(rows)
        
        # Resize worksheet if needed
        worksheet.resize(rows=len(all_data) + 50, cols=20)
        
        # Write all data at once (using correct argument order for newer gspread)
        worksheet.update(values=all_data, range_name="A1", value_input_option="RAW")
        
        # Set case_id column (column A, index 0) to clip text
        print("  Setting case_id column to clip text...")
        clip_text_request = {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,  # Skip header
                    "endRowIndex": len(all_data),
                    "startColumnIndex": 0,  # Column A (0-indexed)
                    "endColumnIndex": 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "CLIP"
                    }
                },
                "fields": "userEnteredFormat.wrapStrategy"
            }
        }
        
        all_requests = [clip_text_request]
        spreadsheet.batch_update({"requests": all_requests})
    
    # Done!
    print("\n" + "=" * 60)
    print(f"✅ Successfully exported {len(rows)} cases!")
    print(f"   View at: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
    print("=" * 60)
    
    return len(rows)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Export ValueBench cases to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python -m src.sheets.export_to_sheets              # Replace all data
  uv run python -m src.sheets.export_to_sheets --append     # Add only new cases
  uv run python -m src.sheets.export_to_sheets --dry-run    # Preview without writing
        """
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Add only new cases (skip existing ones)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without writing to Sheets"
    )
    parser.add_argument(
        "--cases-dir",
        default="data/cases",
        help="Path to the cases directory (default: data/cases)"
    )
    
    args = parser.parse_args()
    
    try:
        count = export_cases(
            append=args.append,
            dry_run=args.dry_run,
            cases_dir=args.cases_dir
        )
        # Exit 0 for success (including "up to date" which returns 0)
        # Only exit 1 if there was a real problem (count will be -1 or error thrown)
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

