"""
Import finalized cases from Google Sheets back to local JSON files.

This script imports cases that have been reviewed and potentially edited in Google Sheets.
It captures and stores reviewer feedback within the case's refinement history, including:
- R1 and R2 reviewer names and decisions
- Reviewer comments

The reviewer feedback is stored in the 'human_evaluation' field of the new refinement
iteration, maintaining a complete history of reviews alongside the case content.

**Duplicate Detection:**
The script checks if the latest version in the local JSON matches what's being imported
from the sheet. If the vignette and choices (including value tags) are identical, the
import is skipped to avoid creating duplicate refinement iterations. Only cases with
actual changes will create new refinement iterations.

Run with: uv run python -m src.sheets.import_from_sheets

Options:
    --dry-run           Show what would be imported without writing to files
    --validate-only     Run validation and show report without importing
    --force             Import cases even if validation warnings exist (errors still block)
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass

import yaml
import gspread
from google.oauth2.service_account import Credentials
from pydantic import ValidationError

# Import validation models
from src.response_models.case import BenchmarkCandidate, ChoiceWithValues, ValueAlignmentStatus


@dataclass
class ValidationResult:
    """Result of validating a single case."""
    case_id: str
    row_number: int
    status: Literal['valid', 'warning', 'error']
    errors: list[str]
    warnings: list[str]
    data: Optional[dict] = None


@dataclass
class ImportReport:
    """Summary report of the import operation."""
    total_rows: int
    valid_cases: int
    warning_cases: int
    error_cases: int
    imported_cases: int
    skipped_cases: int
    unchanged_cases: int  # New field for cases with no changes
    validation_results: list[ValidationResult]
    
    def print_summary(self):
        """Print a human-readable summary."""
        print("\n" + "=" * 70)
        print("IMPORT VALIDATION REPORT")
        print("=" * 70)
        print(f"\nTotal rows processed: {self.total_rows}")
        print(f"✅ Valid cases: {self.valid_cases}")
        if self.warning_cases > 0:
            print(f"⚠️  Cases with warnings: {self.warning_cases}")
        if self.error_cases > 0:
            print(f"❌ Cases with errors: {self.error_cases}")
        
        if self.error_cases > 0:
            print("\n" + "-" * 70)
            print("ERRORS (will NOT be imported):")
            print("-" * 70)
            for result in self.validation_results:
                if result.status == 'error':
                    print(f"\n  Case {result.case_id} (Row {result.row_number}):")
                    for error in result.errors:
                        print(f"    ❌ {error}")
        
        if self.warning_cases > 0:
            print("\n" + "-" * 70)
            print("WARNINGS (can be imported with --force):")
            print("-" * 70)
            for result in self.validation_results:
                if result.status == 'warning':
                    print(f"\n  Case {result.case_id} (Row {result.row_number}):")
                    for warning in result.warnings:
                        print(f"    ⚠️  {warning}")
        
        if self.imported_cases > 0:
            print("\n" + "=" * 70)
            print(f"✅ Successfully imported {self.imported_cases} cases")
            print("=" * 70)
        
        if self.unchanged_cases > 0:
            print(f"\n⏭️  Skipped {self.unchanged_cases} cases (no changes detected)")
        
        if self.skipped_cases > 0:
            print(f"\n⏭️  Skipped {self.skipped_cases} cases due to errors")


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


def parse_sheet_row(row: list, headers: list, row_number: int) -> ValidationResult:
    """
    Parse and validate a single row from the sheet.
    
    Args:
        row: List of cell values from the sheet
        headers: List of column headers
        row_number: Row number in the sheet (for error reporting)
        
    Returns:
        ValidationResult with status, errors, warnings, and parsed data
    """
    errors = []
    warnings = []
    
    # Create a dictionary from the row
    if len(row) < len(headers):
        # Pad row with empty strings if needed
        row = row + [''] * (len(headers) - len(row))
    
    row_dict = dict(zip(headers, row))
    
    # Extract case_id
    case_id = row_dict.get('Case ID', '').strip()
    if not case_id:
        errors.append("Missing Case ID")
        return ValidationResult(
            case_id='UNKNOWN',
            row_number=row_number,
            status='error',
            errors=errors,
            warnings=warnings
        )
    
    # Extract reviewer information
    r1_name = row_dict.get('R1', '').strip()
    r1_decision = row_dict.get('R1 Decision?', '').strip()
    r2_name = row_dict.get('R2', '').strip()
    r2_decision = row_dict.get('R2 Decision?', '').strip()
    reviewer_comments = row_dict.get('Reviewer Comments', '').strip()
    
    # Extract vignette and choices
    vignette = row_dict.get('Vignette', '').strip()
    if not vignette:
        errors.append("Missing vignette")
    
    choice_1_text = row_dict.get('Choice 1', '').strip()
    if not choice_1_text:
        errors.append("Missing Choice 1 text")
    
    choice_2_text = row_dict.get('Choice 2', '').strip()
    if not choice_2_text:
        errors.append("Missing Choice 2 text")
    
    # Extract value tags for choice 1
    c1_autonomy = row_dict.get('Autonomy C1', '').strip().lower()
    c1_beneficence = row_dict.get('Beneficence C1', '').strip().lower()
    c1_nonmaleficence = row_dict.get('Nonmaleficence C1', '').strip().lower()
    c1_justice = row_dict.get('Justice C1', '').strip().lower()
    
    # Extract value tags for choice 2
    c2_autonomy = row_dict.get('Autonomy C2', '').strip().lower()
    c2_beneficence = row_dict.get('Beneficence C2', '').strip().lower()
    c2_nonmaleficence = row_dict.get('Nonmaleficence C2', '').strip().lower()
    c2_justice = row_dict.get('Justice C2', '').strip().lower()
    
    # Validate value tags are from allowed set
    valid_tags = {'promotes', 'violates', 'neutral'}
    value_tags = {
        'Autonomy C1': c1_autonomy,
        'Beneficence C1': c1_beneficence,
        'Nonmaleficence C1': c1_nonmaleficence,
        'Justice C1': c1_justice,
        'Autonomy C2': c2_autonomy,
        'Beneficence C2': c2_beneficence,
        'Nonmaleficence C2': c2_nonmaleficence,
        'Justice C2': c2_justice,
    }
    
    for field_name, tag_value in value_tags.items():
        if not tag_value:
            errors.append(f"Missing value tag: {field_name}")
        elif tag_value not in valid_tags:
            errors.append(f"Invalid value tag '{tag_value}' in {field_name} (must be promotes/violates/neutral)")
    
    # If we have errors so far, return early
    if errors:
        return ValidationResult(
            case_id=case_id,
            row_number=row_number,
            status='error',
            errors=errors,
            warnings=warnings
        )
    
    # Build the data structure for validation
    try:
        choice_1_data = {
            'choice': choice_1_text,
            'autonomy': c1_autonomy,
            'beneficence': c1_beneficence,
            'nonmaleficence': c1_nonmaleficence,
            'justice': c1_justice,
        }
        
        choice_2_data = {
            'choice': choice_2_text,
            'autonomy': c2_autonomy,
            'beneficence': c2_beneficence,
            'nonmaleficence': c2_nonmaleficence,
            'justice': c2_justice,
        }
        
        case_data = {
            'vignette': vignette,
            'choice_1': choice_1_data,
            'choice_2': choice_2_data,
        }
        
        # Add reviewer feedback metadata
        reviewer_feedback = {
            'r1_reviewer': r1_name,
            'r1_decision': r1_decision,
            'r2_reviewer': r2_name,
            'r2_decision': r2_decision,
            'comments': reviewer_comments
        }
        
        # Validate using BenchmarkCandidate model
        try:
            validated_case = BenchmarkCandidate(**case_data)
            
            # If validation passed, return success
            status = 'warning' if warnings else 'valid'
            return ValidationResult(
                case_id=case_id,
                row_number=row_number,
                status=status,
                errors=[],
                warnings=warnings,
                data={
                    'case_data': case_data,
                    'reviewer_feedback': reviewer_feedback
                }
            )
            
        except ValidationError as e:
            # Extract validation error messages
            for error in e.errors():
                error_msg = error.get('msg', str(error))
                # The custom validators in BenchmarkCandidate raise ValueError with detailed messages
                errors.append(error_msg)
            
            return ValidationResult(
                case_id=case_id,
                row_number=row_number,
                status='error',
                errors=errors,
                warnings=warnings
            )
    
    except Exception as e:
        errors.append(f"Unexpected error during validation: {str(e)}")
        return ValidationResult(
            case_id=case_id,
            row_number=row_number,
            status='error',
            errors=errors,
            warnings=warnings
        )


def fetch_finalized_cases(config: dict) -> tuple[list[list], list[str], gspread.Worksheet]:
    """
    Fetch rows marked as 'finalized' from Google Sheets.
    
    Returns:
        Tuple of (data_rows, headers, worksheet)
    """
    print("Connecting to Google Sheets...")
    spreadsheet_id = config.get("spreadsheet_id")
    sheet_name = config.get("sheet_name", "Cases")
    credentials_path = config.get("credentials_path", "credentials/service_account.json")
    
    gc = get_gspread_client(credentials_path)
    
    try:
        spreadsheet = gc.open_by_key(spreadsheet_id)
        print(f"  Connected to: {spreadsheet.title}")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ Spreadsheet not found. Check spreadsheet_id: {spreadsheet_id}")
        sys.exit(1)
    
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        print(f"  Reading worksheet: {sheet_name}")
    except gspread.exceptions.WorksheetNotFound:
        print(f"❌ Worksheet '{sheet_name}' not found")
        sys.exit(1)
    
    # Get all rows
    all_rows = worksheet.get_all_values()
    
    if len(all_rows) < 2:
        print("❌ No data found in sheet (need at least header + 1 row)")
        return [], [], worksheet
    
    headers = all_rows[0]
    data_rows = all_rows[1:]
    
    print(f"  Found {len(data_rows)} total rows")
    
    # Note: The current sheet structure doesn't have a status column
    # We'll import all non-empty rows
    # Filter out completely empty rows
    finalized_rows = [row for row in data_rows if any(cell.strip() for cell in row)]
    
    print(f"  {len(finalized_rows)} rows ready for validation")
    
    return finalized_rows, headers, worksheet


def validate_cases(rows: list[list], headers: list[str]) -> ImportReport:
    """
    Validate all rows and generate a report.
    
    Args:
        rows: List of row data from the sheet
        headers: Column headers
        
    Returns:
        ImportReport with validation results
    """
    print("\nValidating cases...")
    
    validation_results = []
    for i, row in enumerate(rows, start=2):  # Start at 2 (row 1 is header)
        result = parse_sheet_row(row, headers, i)
        validation_results.append(result)
    
    # Count results by status
    valid_count = sum(1 for r in validation_results if r.status == 'valid')
    warning_count = sum(1 for r in validation_results if r.status == 'warning')
    error_count = sum(1 for r in validation_results if r.status == 'error')
    
    report = ImportReport(
        total_rows=len(rows),
        valid_cases=valid_count,
        warning_cases=warning_count,
        error_cases=error_count,
        imported_cases=0,
        skipped_cases=0,
        unchanged_cases=0,
        validation_results=validation_results
    )
    
    return report


def write_validation_to_sheet(
    worksheet: gspread.Worksheet,
    validation_results: list[ValidationResult],
    headers: list[str]
) -> None:
    """
    Write validation results back to the Google Sheet.
    
    Adds/updates two columns:
    - Validation Status: "✅ Valid", "⚠️ Warning", or "❌ Error"
    - Validation Message: Error/warning messages or empty if valid
    
    Args:
        worksheet: The gspread worksheet object
        validation_results: List of validation results
        headers: Current column headers
    """
    print("\nWriting validation results to sheet...")
    
    # Check if validation columns exist
    status_col_name = "Validation Status"
    message_col_name = "Validation Message"
    
    # Find or add validation columns
    if status_col_name not in headers:
        headers.append(status_col_name)
    if message_col_name not in headers:
        headers.append(message_col_name)
    
    status_col_idx = headers.index(status_col_name) + 1  # 1-indexed for gspread
    message_col_idx = headers.index(message_col_name) + 1
    
    # Prepare batch updates
    updates = []
    
    # Update header row if needed
    header_range = f"{chr(64 + status_col_idx)}1:{chr(64 + message_col_idx)}1"
    updates.append({
        'range': header_range,
        'values': [[status_col_name, message_col_name]]
    })
    
    # Update each row with validation results
    for result in validation_results:
        row_num = result.row_number
        
        # Format status
        if result.status == 'valid':
            status = "✅ Valid"
            message = ""
        elif result.status == 'warning':
            status = "⚠️ Warning"
            message = " | ".join(result.warnings)
        else:  # error
            status = "❌ Error"
            message = " | ".join(result.errors)
        
        # Add to batch update
        status_cell = f"{chr(64 + status_col_idx)}{row_num}"
        message_cell = f"{chr(64 + message_col_idx)}{row_num}"
        
        updates.append({
            'range': status_cell,
            'values': [[status]]
        })
        updates.append({
            'range': message_cell,
            'values': [[message]]
        })
    
    # Execute batch update
    if updates:
        worksheet.batch_update(updates, value_input_option='RAW')
        print(f"  Updated validation results for {len(validation_results)} rows")
        print(f"  Columns: {status_col_name} ({chr(64 + status_col_idx)}), {message_col_name} ({chr(64 + message_col_idx)})")
    
    # Format the validation columns
    sheet_id = worksheet.id
    
    # Color-code the status column
    requests = []
    for result in validation_results:
        row_idx = result.row_number - 1  # 0-indexed for API
        
        if result.status == 'valid':
            bg_color = {"red": 0.85, "green": 0.95, "blue": 0.85}  # Light green
        elif result.status == 'warning':
            bg_color = {"red": 1.0, "green": 0.95, "blue": 0.8}  # Light yellow
        else:  # error
            bg_color = {"red": 1.0, "green": 0.85, "blue": 0.85}  # Light red
        
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_idx,
                    "endRowIndex": row_idx + 1,
                    "startColumnIndex": status_col_idx - 1,
                    "endColumnIndex": status_col_idx
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": bg_color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })
    
    # Execute formatting
    if requests:
        worksheet.spreadsheet.batch_update({"requests": requests})
        print("  Applied color coding to validation status column")


def _data_matches(data1: dict, data2: dict) -> bool:
    """
    Compare two case data dictionaries to check if they represent the same content.
    
    Args:
        data1: First data dictionary (from existing refinement)
        data2: Second data dictionary (from sheet import)
        
    Returns:
        True if the data is identical, False otherwise
    """
    # Extract the case content fields to compare
    def extract_case_content(data):
        """Extract comparable content from data dictionary."""
        vignette = data.get('vignette', '').strip()
        
        # Handle choice_1 - could be dict or string
        choice_1_data = data.get('choice_1', {})
        if isinstance(choice_1_data, dict):
            choice_1_text = choice_1_data.get('choice', '').strip()
            c1_autonomy = choice_1_data.get('autonomy', '').strip()
            c1_beneficence = choice_1_data.get('beneficence', '').strip()
            c1_nonmaleficence = choice_1_data.get('nonmaleficence', '').strip()
            c1_justice = choice_1_data.get('justice', '').strip()
        else:
            choice_1_text = str(choice_1_data).strip()
            c1_autonomy = c1_beneficence = c1_nonmaleficence = c1_justice = ''
        
        # Handle choice_2 - could be dict or string
        choice_2_data = data.get('choice_2', {})
        if isinstance(choice_2_data, dict):
            choice_2_text = choice_2_data.get('choice', '').strip()
            c2_autonomy = choice_2_data.get('autonomy', '').strip()
            c2_beneficence = choice_2_data.get('beneficence', '').strip()
            c2_nonmaleficence = choice_2_data.get('nonmaleficence', '').strip()
            c2_justice = choice_2_data.get('justice', '').strip()
        else:
            choice_2_text = str(choice_2_data).strip()
            c2_autonomy = c2_beneficence = c2_nonmaleficence = c2_justice = ''
        
        return (
            vignette,
            choice_1_text,
            c1_autonomy, c1_beneficence, c1_nonmaleficence, c1_justice,
            choice_2_text,
            c2_autonomy, c2_beneficence, c2_nonmaleficence, c2_justice
        )
    
    # Compare the extracted content
    return extract_case_content(data1) == extract_case_content(data2)


def update_case_json(
    case_id: str, 
    new_data: dict, 
    reviewer_feedback: dict,
    cases_dir: str = "data/cases"
) -> tuple[bool, bool]:
    """
    Update a case JSON file with new refinement iteration including reviewer feedback.
    
    Args:
        case_id: The case ID to update
        new_data: Dictionary with 'case_data' (vignette, choice_1, choice_2) 
        reviewer_feedback: Dictionary with reviewer information:
            - r1_reviewer: R1 name
            - r1_decision: R1's decision
            - r2_reviewer: R2 name
            - r2_decision: R2's decision
            - comments: Reviewer comments
        cases_dir: Path to the cases directory
        
    Returns:
        Tuple of (success: bool, unchanged: bool)
        - success: True if operation completed (file found), False otherwise
        - unchanged: True if data matched and no update was needed, False if updated
    """
    cases_path = Path(cases_dir)
    
    # Find the case file by case_id
    matching_files = list(cases_path.glob(f"case_{case_id}_*.json"))
    
    if not matching_files:
        print(f"  ⚠️  Case file not found for {case_id}")
        return False, False
    
    if len(matching_files) > 1:
        print(f"  ⚠️  Multiple files found for {case_id}, using most recent")
    
    # Use the most recently modified file
    case_file = max(matching_files, key=lambda p: p.stat().st_mtime)
    
    # Load the existing case data
    with open(case_file, 'r', encoding='utf-8') as f:
        case_data = json.load(f)
    
    # Get the last iteration number and refinement history
    refinement_history = case_data.get('refinement_history', [])
    
    # Check if the latest version matches what we're trying to import
    if refinement_history:
        latest_refinement = refinement_history[-1]
        latest_data = latest_refinement.get('data', {})
        
        # Compare the case data (vignette and choices) to see if there are actual changes
        if _data_matches(latest_data, new_data):
            print(f"  ⏭️  {case_id} - No changes detected, skipping duplicate import")
            return True, True  # Success=True, Unchanged=True
    
    last_iteration = max([h.get('iteration', -1) for h in refinement_history], default=-1)
    new_iteration = last_iteration + 1
    
    # Build human_evaluation structure with reviewer feedback
    human_evaluation = {
        'source': 'google_sheets',
        'import_timestamp': datetime.now().isoformat()
    }
    
    # Add reviewer information if provided
    reviewers = {}
    
    if reviewer_feedback.get('r1_reviewer'):
        reviewers['r1'] = {
            'name': reviewer_feedback['r1_reviewer'],
            'decision': reviewer_feedback.get('r1_decision', '')
        }
    
    if reviewer_feedback.get('r2_reviewer'):
        reviewers['r2'] = {
            'name': reviewer_feedback['r2_reviewer'],
            'decision': reviewer_feedback.get('r2_decision', '')
        }
    
    if reviewers:
        human_evaluation['reviewers'] = reviewers
    
    # Add comments if provided
    if reviewer_feedback.get('comments'):
        human_evaluation['comments'] = reviewer_feedback['comments']
    
    # Create new refinement iteration
    new_refinement = {
        'iteration': new_iteration,
        'step_description': 'sheets_edit',
        'timestamp': datetime.now().isoformat(),
        'data': new_data,
        'clinical_evaluation': None,
        'ethical_evaluation': None,
        'stylistic_evaluation': None,
        'value_validations': {},
        'feedback': {},
        'human_evaluation': human_evaluation
    }
    
    # Append to refinement history
    refinement_history.append(new_refinement)
    case_data['refinement_history'] = refinement_history
    
    # Write back to file
    with open(case_file, 'w', encoding='utf-8') as f:
        json.dump(case_data, f, indent=2, ensure_ascii=False)
    
    return True, False  # Success=True, Unchanged=False


def import_cases(
    validate_only: bool = False,
    dry_run: bool = False,
    force: bool = False,
    cases_dir: str = "data/cases",
    write_validation: bool = True
) -> ImportReport:
    """
    Import finalized cases from Google Sheets.
    
    Args:
        validate_only: Only validate, don't import
        dry_run: Show what would be imported without writing
        force: Import cases even if warnings exist
        cases_dir: Path to cases directory
        write_validation: Write validation results back to sheet
        
    Returns:
        ImportReport with results
    """
    print("=" * 70)
    print("ValueBench Case Import from Google Sheets")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Fetch finalized cases from sheets
    rows, headers, worksheet = fetch_finalized_cases(config)
    
    if not rows:
        print("\n✅ No cases to import")
        return ImportReport(
            total_rows=0,
            valid_cases=0,
            warning_cases=0,
            error_cases=0,
            imported_cases=0,
            skipped_cases=0,
            unchanged_cases=0,
            validation_results=[]
        )
    
    # Validate all cases
    report = validate_cases(rows, headers)
    
    # Write validation results back to sheet
    if write_validation:
        try:
            write_validation_to_sheet(worksheet, report.validation_results, headers)
        except Exception as e:
            print(f"  ⚠️  Could not write validation to sheet: {e}")
    
    # Print validation report
    report.print_summary()
    
    # If validate-only mode, stop here
    if validate_only:
        print("\n[VALIDATE-ONLY MODE] No files were modified")
        return report
    
    # Check if we can proceed with import
    if report.error_cases > 0:
        print(f"\n❌ Cannot import: {report.error_cases} cases have validation errors")
        print("   Fix errors in the spreadsheet and try again")
        print("   Check the 'Validation Message' column in the sheet for details")
        return report
    
    if report.warning_cases > 0 and not force:
        print(f"\n⚠️  {report.warning_cases} cases have warnings")
        print("   Use --force to import them anyway, or fix warnings in the spreadsheet")
        return report
    
    # Proceed with import
    if dry_run:
        print("\n[DRY RUN] Would import the following cases:")
        for result in report.validation_results:
            if result.status in ['valid', 'warning'] and result.data:
                reviewer_feedback = result.data.get('reviewer_feedback', {})
                
                # Build feedback summary
                feedback_parts = []
                if reviewer_feedback.get('r1_reviewer'):
                    r1_str = f"R1: {reviewer_feedback['r1_reviewer']}"
                    if reviewer_feedback.get('r1_decision'):
                        r1_str += f" ({reviewer_feedback['r1_decision']})"
                    feedback_parts.append(r1_str)
                
                if reviewer_feedback.get('r2_reviewer'):
                    r2_str = f"R2: {reviewer_feedback['r2_reviewer']}"
                    if reviewer_feedback.get('r2_decision'):
                        r2_str += f" ({reviewer_feedback['r2_decision']})"
                    feedback_parts.append(r2_str)
                
                feedback_summary = ", ".join(feedback_parts) if feedback_parts else "No reviewer info"
                
                print(f"  • {result.case_id} (Row {result.row_number})")
                print(f"    Reviewers: {feedback_summary}")
                if reviewer_feedback.get('comments'):
                    comment_preview = reviewer_feedback['comments'][:80]
                    if len(reviewer_feedback['comments']) > 80:
                        comment_preview += "..."
                    print(f"    Comments: {comment_preview}")
        
        print(f"\nTotal: {report.valid_cases + report.warning_cases} cases would be imported")
        return report
    
    # Actually import the cases
    print(f"\nImporting {report.valid_cases + report.warning_cases} cases...")
    imported = 0
    skipped = 0
    unchanged = 0
    
    for result in report.validation_results:
        if result.status in ['valid', 'warning'] and result.data:
            case_data = result.data.get('case_data', {})
            reviewer_feedback = result.data.get('reviewer_feedback', {})
            success, is_unchanged = update_case_json(
                result.case_id, 
                case_data, 
                reviewer_feedback,
                cases_dir
            )
            if success:
                if is_unchanged:
                    unchanged += 1
                else:
                    imported += 1
                    print(f"  ✅ {result.case_id}")
            else:
                skipped += 1
        else:
            skipped += 1
    
    report.imported_cases = imported
    report.skipped_cases = skipped
    report.unchanged_cases = unchanged
    
    print("\n" + "=" * 70)
    print(f"✅ Import complete: {imported} cases updated")
    if unchanged > 0:
        print(f"⏭️  Skipped: {unchanged} cases (no changes)")
    if skipped > 0:
        print(f"⏭️  Skipped: {skipped} cases (errors)")
    print("=" * 70)
    
    return report


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Import finalized cases from Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python -m src.sheets.import_from_sheets                    # Import all valid cases
  uv run python -m src.sheets.import_from_sheets --validate-only    # Just validate, don't import
  uv run python -m src.sheets.import_from_sheets --dry-run          # Preview what would be imported
  uv run python -m src.sheets.import_from_sheets --force            # Import even with warnings
        """
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate cases without importing"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing to files"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Import cases even if validation warnings exist"
    )
    parser.add_argument(
        "--cases-dir",
        default="data/cases",
        help="Path to the cases directory (default: data/cases)"
    )
    parser.add_argument(
        "--no-write-validation",
        action="store_true",
        help="Don't write validation results back to the sheet"
    )
    
    args = parser.parse_args()
    
    try:
        report = import_cases(
            validate_only=args.validate_only,
            dry_run=args.dry_run,
            force=args.force,
            cases_dir=args.cases_dir,
            write_validation=not args.no_write_validation
        )
        
        # Exit with appropriate code
        if report.error_cases > 0:
            sys.exit(1)
        else:
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

