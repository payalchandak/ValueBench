"""
Export ValueBench cases to Google Sheets for collaborative editing.

Run with: uv run python -m src.sheets.export_to_sheets

Options:
    --append     Add only new cases (default: replace all)
    --dry-run    Show what would be exported without writing to Sheets
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
import gspread
from google.oauth2.service_account import Credentials


def load_config() -> dict:
    """Load sheets configuration."""
    config_path = Path(__file__).parent / "sheets_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_gspread_client(credentials_path: str) -> gspread.Client:
    """Create an authenticated gspread client."""
    creds_path = Path(__file__).parent.parent.parent / credentials_path
    
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_path}\n"
            "Run 'uv run python -m src.sheets.verify_setup' for setup instructions."
        )
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    credentials = Credentials.from_service_account_file(
        str(creds_path),
        scopes=scopes
    )
    
    return gspread.authorize(credentials)


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
    for iteration in reversed(refinement_history):
        data = iteration.get("data", {})
        choice_1 = data.get("choice_1")
        choice_2 = data.get("choice_2")
        
        # Check if this has value tags (BenchmarkCandidate format)
        if isinstance(choice_1, dict) and "autonomy" in choice_1:
            final_data = data
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
    
    # Build row in column order: case_id, R1, R1 Decision?, R2, R2 Decision?, vignette, choice_1, c1_values..., choice_2, c2_values..., reviewer comments
    row = [
        case_id,
        "",  # R1 - to be filled in manually
        "",  # R1 Decision? - text field
        "",  # R2 - to be filled in manually
        "",  # R2 Decision? - text field
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
        "",  # Reviewer Comments - to be filled in manually
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
    Set up dropdown validation for value tag columns and status column.
    
    Uses the Google Sheets API batch update for data validation rules.
    
    Args:
        spreadsheet: The gspread Spreadsheet object
        worksheet: The gspread Worksheet object
        num_rows: Total number of data rows (excluding header)
        config: Configuration dictionary with value_options and status_options
    """
    value_options = config.get("value_options", ["promotes", "violates", "neutral"])
    status_options = config.get("status_options", ["draft", "review", "finalized"])
    
    # Value tag columns (D, E, F, G for choice_1 and I, J, K, L for choice_2)
    # Using 0-based column indices: D=3, E=4, F=5, G=6, I=8, J=9, K=10, L=11
    value_columns = [3, 4, 5, 6, 8, 9, 10, 11]  # 0-indexed
    
    # Status column (M = index 12)
    status_column = 12  # 0-indexed
    
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
    
    # Create data validation rule for status column
    print("  Setting up status dropdown...")
    status_rule = {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row_idx,
                "endRowIndex": end_row_idx,
                "startColumnIndex": status_column,
                "endColumnIndex": status_column + 1
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": opt} for opt in status_options]
                },
                "showCustomUi": True,
                "strict": True
            }
        }
    }
    requests.append(status_rule)
    
    # Execute batch update
    if requests:
        spreadsheet.batch_update({"requests": requests})


def format_header(worksheet: gspread.Worksheet):
    """Apply formatting to the header row."""
    # Bold the header row and freeze it
    worksheet.format("A1:N1", {
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
    
    # Column widths (in pixels):
    # A (case_id): 120, B (vignette): 500, C (choice_1): 300, 
    # D-G (c1 values): 100 each, H (choice_2): 300,
    # I-L (c2 values): 100 each, M (status): 80, N (last_edited): 100
    column_widths = [
        (0, 150),   # A: case_id
        (1, 500),   # B: vignette
        (2, 300),   # C: choice_1
        (3, 100),   # D: c1_autonomy
        (4, 100),   # E: c1_beneficence
        (5, 120),   # F: c1_nonmaleficence
        (6, 100),   # G: c1_justice
        (7, 300),   # H: choice_2
        (8, 100),   # I: c2_autonomy
        (9, 100),   # J: c2_beneficence
        (10, 120),  # K: c2_nonmaleficence
        (11, 100),  # L: c2_justice
        (12, 80),   # M: status
        (13, 100),  # N: last_edited
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
    
    # Enable text wrapping for vignette (B), choice_1 (C), choice_2 (H)
    text_wrap_columns = [1, 2, 7]  # B, C, H (0-indexed)
    for col_idx in text_wrap_columns:
        col_letter = chr(ord('A') + col_idx)
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
    credentials_path = config.get("credentials_path", "credentials/service_account.json")
    gc = get_gspread_client(credentials_path)
    
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

