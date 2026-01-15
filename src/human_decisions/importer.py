"""CSV parser for importing Qualtrics survey responses into human decisions format.

This module parses Qualtrics CSV exports and converts responses into a format
compatible with the existing DecisionRecord structure used for LLM decisions.
"""

import csv
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.human_decisions.models import ParticipantInfo, ParticipantRegistry
from src.llm_decisions.models import DecisionRecord, ModelDecisionData, RunResult
from src.response_models.case import BenchmarkCandidate, ChoiceWithValues


class HumanResponseValidationError(Exception):
    """Raised when a human response cannot be matched to a valid choice."""
    pass


class ParsedResponse(BaseModel):
    """A single parsed response from a participant for one case."""
    
    case_id: str = Field(..., description="UUID of the case (without 'case_' prefix or hash suffix)")
    participant_id: str = Field(..., description="Anonymous participant ID (format: participant_{hash[:8]})")
    selected_choice: Literal["choice_1", "choice_2"] = Field(..., description="Which choice was selected")
    response_text: str = Field(..., description="Original response text from the CSV")
    timestamp: datetime = Field(..., description="When the response was recorded (from Qualtrics EndDate)")


class QualtricsParseResult(BaseModel):
    """Complete result of parsing a Qualtrics CSV file."""
    
    responses: list[ParsedResponse] = Field(default_factory=list, description="List of all parsed responses")
    participants: dict[str, ParticipantInfo] = Field(default_factory=dict, description="Participant ID -> info mapping")
    unmatched_responses: list[tuple[str, str, str]] = Field(
        default_factory=list,
        description="List of (case_id, participant_id, response_text) tuples that could not be matched"
    )
    case_ids_found: set[str] = Field(default_factory=set, description="All case UUIDs found in the CSV")
    warnings: list[str] = Field(
        default_factory=list,
        description="List of warning messages about data quality issues"
    )


def generate_participant_id(name: str, email: str) -> str:
    """Generate a stable anonymous participant ID from name and email.
    
    Creates a deterministic hash so the same person always gets the same ID,
    even across multiple CSV imports.
    
    Args:
        name: Participant's full name
        email: Participant's email address
        
    Returns:
        Anonymous ID in format: participant_{hash[:8]}
        
    Example:
        >>> generate_participant_id("John Doe", "jdoe@example.com")
        'participant_a3f8c2d1'
    """
    # Normalize inputs for consistent hashing
    normalized = f"{name.strip().lower()}|{email.strip().lower()}"
    hash_bytes = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"participant_{hash_bytes[:8]}"


def extract_case_uuid_from_column(column_header: str) -> str | None:
    """Extract the case UUID from a Qualtrics column header.
    
    Qualtrics exports use column headers in the format:
    "{uuid} - {vignette_text_truncated}"
    
    This function extracts just the UUID part.
    
    Args:
        column_header: The full column header from Qualtrics CSV
        
    Returns:
        The extracted UUID string, or None if no valid UUID found
        
    Example:
        >>> extract_case_uuid_from_column("0075b71f-ec8f-4884-8297-5119de2e4b0e - A 23-year-old...")
        '0075b71f-ec8f-4884-8297-5119de2e4b0e'
    """
    # UUID pattern: 8-4-4-4-12 hex chars
    uuid_pattern = r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    match = re.match(uuid_pattern, column_header.strip())
    if match:
        return match.group(1).lower()
    return None


def match_response_to_choice(
    response_text: str,
    case: BenchmarkCandidate,
) -> Literal["choice_1", "choice_2"]:
    """Match a survey response to the corresponding choice in a case.
    
    Performs exact matching between the response text and the choice text
    from the case definition.
    
    Args:
        response_text: The response text from the Qualtrics CSV
        case: The BenchmarkCandidate containing the two choices
        
    Returns:
        "choice_1" or "choice_2" depending on which choice was selected
        
    Raises:
        HumanResponseValidationError: If the response doesn't match either choice
    """
    # Normalize for comparison (strip whitespace, handle encoding)
    normalized_response = response_text.strip()
    choice_1_text = case.choice_1.choice.strip()
    choice_2_text = case.choice_2.choice.strip()
    
    if normalized_response == choice_1_text:
        return "choice_1"
    elif normalized_response == choice_2_text:
        return "choice_2"
    else:
        raise HumanResponseValidationError(
            f"Response does not match either choice.\n"
            f"Response: {normalized_response!r}\n"
            f"Choice 1: {choice_1_text!r}\n"
            f"Choice 2: {choice_2_text!r}"
        )


def _load_case_from_llm_decisions(case_id: str, llm_decisions_dir: Path) -> BenchmarkCandidate | None:
    """Try to load a case from an LLM decisions file.
    
    Args:
        case_id: The case UUID
        llm_decisions_dir: Path to the llm_decisions directory
        
    Returns:
        BenchmarkCandidate if found, None otherwise
    """
    decision_file = llm_decisions_dir / f"{case_id}.json"
    
    if not decision_file.exists():
        return None
    
    with open(decision_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # DecisionRecord has embedded case as BenchmarkCandidate
    case_data = data.get("case")
    if case_data is None:
        return None
    
    return BenchmarkCandidate(
        vignette=case_data["vignette"],
        choice_1=ChoiceWithValues(**case_data["choice_1"]),
        choice_2=ChoiceWithValues(**case_data["choice_2"]),
    )


def _load_case_from_cases_dir(case_id: str, cases_dir: Path) -> BenchmarkCandidate | None:
    """Load a case from the cases directory.
    
    Searches for a case file matching the pattern case_{uuid}_*.json
    and extracts the BenchmarkCandidate from the final refinement step.
    
    Args:
        case_id: The case UUID (without prefix or suffix)
        cases_dir: Path to the directory containing case JSON files
        
    Returns:
        BenchmarkCandidate if found, None otherwise
    """
    # Case files are named: case_{uuid}_{hash}.json
    pattern = f"case_{case_id}_*.json"
    matches = list(cases_dir.glob(pattern))
    
    if not matches:
        return None
    
    # Use the first match (there should only be one per UUID)
    case_file = matches[0]
    
    with open(case_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Extract the final case from refinement_history
    # The last item with data containing choice_1/choice_2 as dicts is the final version
    refinement_history = data.get("refinement_history", [])
    
    for iteration in reversed(refinement_history):
        iter_data = iteration.get("data", {})
        # Check if this iteration has the full tagged structure
        if isinstance(iter_data.get("choice_1"), dict) and isinstance(iter_data.get("choice_2"), dict):
            return BenchmarkCandidate(
                vignette=iter_data["vignette"],
                choice_1=ChoiceWithValues(**iter_data["choice_1"]),
                choice_2=ChoiceWithValues(**iter_data["choice_2"]),
            )
    
    return None


def load_case_by_uuid(
    case_id: str,
    llm_decisions_dir: Path | None = None,
    cases_dir: Path | None = None,
) -> BenchmarkCandidate | None:
    """Load a case by its UUID, checking llm_decisions first then cases directory.
    
    First attempts to load the case from an existing LLM decision file (which has
    the embedded BenchmarkCandidate). Falls back to the cases directory if not found.
    
    Args:
        case_id: The case UUID (without prefix or suffix)
        llm_decisions_dir: Path to the llm_decisions directory (default: data/llm_decisions/)
        cases_dir: Path to the cases directory (default: data/cases/)
        
    Returns:
        BenchmarkCandidate if found, None otherwise
    """
    # Set default paths
    data_root = Path(__file__).parent.parent.parent / "data"
    
    if llm_decisions_dir is None:
        llm_decisions_dir = data_root / "llm_decisions"
    
    if cases_dir is None:
        cases_dir = data_root / "cases"
    
    # Try llm_decisions first (faster, has embedded case)
    if llm_decisions_dir.exists():
        case = _load_case_from_llm_decisions(case_id, llm_decisions_dir)
        if case is not None:
            return case
    
    # Fall back to cases directory
    if cases_dir.exists():
        return _load_case_from_cases_dir(case_id, cases_dir)
    
    return None


def _parse_qualtrics_timestamp(timestamp_str: str) -> tuple[datetime, str | None]:
    """Parse a Qualtrics timestamp string into a datetime object.
    
    Handles common Qualtrics date formats.
    
    Args:
        timestamp_str: Timestamp string from Qualtrics (e.g., "2026-01-12 07:32:34")
        
    Returns:
        Tuple of (parsed datetime object, warning message or None)
    """
    if not timestamp_str or not timestamp_str.strip():
        return datetime.now(), "Empty timestamp field, using current time"
    
    # Try common Qualtrics formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str.strip(), fmt), None
        except ValueError:
            continue
    
    # Fall back to current time if parsing fails
    warning = f"Could not parse timestamp '{timestamp_str}', using current time"
    return datetime.now(), warning


def _detect_qualtrics_format(rows: list[list[str]]) -> tuple[list[str], int]:
    """Detect Qualtrics CSV format and return headers and data start row.
    
    Qualtrics exports can have multiple formats:
    1. Standard: Row 1 = headers, Row 2+ = data
    2. Two-header: Row 1 = short names (QID304), Row 2 = descriptions (with UUIDs), Row 3+ = data
    3. Two-header with metadata: Row 1 = short names, Row 2 = descriptions, Row 3 = JSON metadata, Row 4+ = data
    
    This function detects which format is used by checking if row 2 contains UUIDs
    that row 1 doesn't have, and whether row 3 looks like JSON metadata.
    
    Args:
        rows: First few rows of the CSV file
        
    Returns:
        Tuple of (headers_to_use, data_start_row_index)
    """
    if len(rows) < 2:
        return rows[0] if rows else [], 1
    
    row1, row2 = rows[0], rows[1]
    
    # Check if row 1 has any UUIDs (just UUIDs, no descriptive text)
    row1_has_uuids = any(extract_case_uuid_from_column(col) for col in row1)
    row1_has_only_uuids = row1_has_uuids and not any(" - " in col for col in row1 if extract_case_uuid_from_column(col))
    
    # Check if row 2 has descriptive headers (UUIDs followed by " - " and text)
    # This indicates row 2 is the descriptive header row
    row2_has_descriptive_headers = any(
        extract_case_uuid_from_column(col) and " - " in col 
        for col in row2
    )
    
    # Check if row 2 has long descriptive text (vignettes) in columns where row 1 has UUIDs
    # This is another two-header format: row 1 = UUIDs, row 2 = vignette text
    row2_has_vignettes = False
    if row1_has_uuids:
        # Check if columns with UUIDs in row 1 have long descriptive text in row 2
        uuid_cols_with_vignettes = sum(
            1 for i, col1 in enumerate(row1)
            if extract_case_uuid_from_column(col1) 
            and i < len(row2) 
            and len(row2[i]) > 50  # Long text suggests vignette
        )
        row2_has_vignettes = uuid_cols_with_vignettes > 0
    
    # Check if row 2 has UUIDs (and more than row 1)
    row2_uuid_count = sum(1 for col in row2 if extract_case_uuid_from_column(col))
    
    # If row 2 has descriptive headers (UUIDs with vignette text), use two-header format
    # OR if row 1 has only UUIDs and row 2 has vignettes (another two-header format)
    # OR if row 2 has UUIDs but row 1 doesn't
    if row2_has_descriptive_headers or (row1_has_only_uuids and row2_has_vignettes) or (row2_uuid_count > 0 and not row1_has_uuids):
        # Check if row 3 (index 2) looks like JSON metadata
        # JSON metadata rows typically start with {"ImportId":...}
        data_start = 2
        if len(rows) > 2:
            row3 = rows[2]
            # Check if first few columns look like JSON (contain "ImportId" or start with "{")
            if row3 and any(
                cell.strip().startswith("{") and "ImportId" in cell 
                for cell in row3[:5] if cell
            ):
                # Row 3 is metadata, data starts at row 4 (index 3)
                data_start = 3
        
        # Use row 2 as headers, data starts at determined index
        return row2, data_start
    
    # Standard format: row 1 is headers, data starts at row 2 (index 1)
    return row1, 1


def _build_column_mapping(short_headers: list[str], desc_headers: list[str]) -> dict[str, str]:
    """Build a mapping from short header names to descriptive headers.
    
    Args:
        short_headers: Row 1 headers (e.g., QID304)
        desc_headers: Row 2 headers (e.g., "7bd46c3e-... - A 34-year-old...")
        
    Returns:
        Dict mapping short names to descriptive names
    """
    return dict(zip(short_headers, desc_headers))


def parse_qualtrics_csv(
    csv_path: str | Path,
    llm_decisions_dir: str | Path | None = None,
    cases_dir: str | Path | None = None,
    name_column: str = "Name",
    email_column: str = "Email",
    expertise_column: str = "Expertise",
    timestamp_column: str = "EndDate",
    strict: bool = True,
) -> QualtricsParseResult:
    """Parse a Qualtrics CSV export file and extract human decisions.
    
    Reads a Qualtrics survey export and converts responses into a format
    compatible with the DecisionRecord structure used for LLM decisions.
    
    The CSV is expected to have:
    - Participant info columns (name, email, expertise)
    - Case response columns with headers in format: "{uuid} - {vignette_text}"
    - Response values that exactly match choice_1.choice or choice_2.choice
    
    Supports both standard CSV format and Qualtrics two-header format where:
    - Row 1 contains short column names (QID304, etc.)
    - Row 2 contains descriptive headers with UUIDs
    - Row 3+ contains actual data
    
    Args:
        csv_path: Path to the Qualtrics CSV export file
        llm_decisions_dir: Path to llm_decisions directory (default: data/llm_decisions/)
        cases_dir: Path to the cases directory (default: data/cases/)
        name_column: Column header for participant names
        email_column: Column header for participant emails  
        expertise_column: Column header for participant expertise/specialty
        timestamp_column: Column header for response timestamp (default: EndDate)
        strict: If True, raise HumanResponseValidationError on any unmatched response.
            If False, collect unmatched responses for later review.
            
    Returns:
        QualtricsParseResult containing all parsed responses and participant info
        
    Raises:
        FileNotFoundError: If the CSV file doesn't exist
        HumanResponseValidationError: If strict=True and any response cannot be matched
        
    Example:
        >>> result = parse_qualtrics_csv("survey_responses.csv")
        >>> len(result.responses)
        150
        >>> result.participants["participant_a3f8c2d1"].name
        'Dr. Jane Smith'
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    # Set default paths
    data_root = Path(__file__).parent.parent.parent / "data"
    
    if llm_decisions_dir is None:
        llm_decisions_dir = data_root / "llm_decisions"
    else:
        llm_decisions_dir = Path(llm_decisions_dir)
    
    if cases_dir is None:
        cases_dir = data_root / "cases"
    else:
        cases_dir = Path(cases_dir)
    
    result = QualtricsParseResult()
    
    # Cache loaded cases to avoid repeated file reads
    case_cache: dict[str, BenchmarkCandidate | None] = {}
    
    # Read the CSV to detect format
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        csv_reader = csv.reader(f)
        all_rows = list(csv_reader)
    
    if len(all_rows) < 2:
        raise ValueError("CSV file has insufficient data (need at least header + 1 row)")
    
    # Detect format and get headers
    headers, data_start_idx = _detect_qualtrics_format(all_rows)
    
    # Build column mapping for Qualtrics two-header format
    short_to_desc = {}
    if data_start_idx >= 2:
        # Two-header format: build mapping from short names to descriptive names
        short_to_desc = _build_column_mapping(all_rows[0], all_rows[1])
    
    # Identify case columns (those starting with a UUID)
    # In two-header format, UUIDs may be in row 1 while row 2 has vignette text
    case_columns: dict[str, str] = {}  # column_header -> case_id
    row1_headers = all_rows[0] if len(all_rows) > 0 else []
    
    for i, col in enumerate(headers):
        # First try to extract UUID from the header itself
        case_id = extract_case_uuid_from_column(col)
        
        # If not found and we're in two-header format, check row 1 for UUID
        if not case_id and data_start_idx >= 2 and i < len(row1_headers):
            case_id = extract_case_uuid_from_column(row1_headers[i])
        
        if case_id:
            case_columns[col] = case_id
            result.case_ids_found.add(case_id)
    
    # Pre-load all cases we'll need
    for case_id in result.case_ids_found:
        if case_id not in case_cache:
            case_cache[case_id] = load_case_by_uuid(case_id, llm_decisions_dir, cases_dir)
    
    # Track validation errors for strict mode
    validation_errors: list[str] = []
    
    # Find column indices for participant info
    # In two-header format, we need to look up by short name or description
    def find_column_index(column_name: str) -> int | None:
        """Find column index by name, checking both short and descriptive headers."""
        column_lower = column_name.lower()
        
        # First try exact match (case-insensitive)
        for i, h in enumerate(headers):
            if h.lower() == column_lower:
                return i
        
        # Then try partial match in headers
        for i, h in enumerate(headers):
            if column_lower in h.lower():
                return i
        
        # If two-header format, check short headers too
        if short_to_desc:
            # Exact match in short headers
            for i, short in enumerate(all_rows[0]):
                if short.lower() == column_lower:
                    return i
                # Also check if the descriptive header matches exactly
                desc = short_to_desc.get(short, "")
                if desc.lower() == column_lower:
                    return i
            
            # Partial match in short headers
            for i, short in enumerate(all_rows[0]):
                if column_lower in short.lower():
                    return i
                # Also check if the descriptive header matches
                desc = short_to_desc.get(short, "")
                if column_lower in desc.lower():
                    return i
        return None
    
    # Find key columns
    name_idx = find_column_index(name_column)
    email_idx = find_column_index(email_column)
    expertise_idx = find_column_index(expertise_column)
    timestamp_idx = find_column_index(timestamp_column)
    
    # Warn if required columns are missing
    if name_idx is None:
        result.warnings.append(f"Column '{name_column}' not found - participant names cannot be extracted")
    if email_idx is None:
        result.warnings.append(f"Column '{email_column}' not found - participant emails cannot be extracted")
    if timestamp_idx is None:
        result.warnings.append(f"Column '{timestamp_column}' not found - using current time for all timestamps")
    
    # Parse each data row (participant)
    for row_num, row in enumerate(all_rows[data_start_idx:], start=data_start_idx + 1):
        # Skip empty rows
        if not row or not any(cell.strip() for cell in row):
            continue
        
        # Get participant info by index
        name = row[name_idx].strip() if name_idx is not None and name_idx < len(row) else ""
        email = row[email_idx].strip() if email_idx is not None and email_idx < len(row) else ""
        
        # Check for email with spaces (before normalization)
        original_email = email
        # Normalize email by removing all spaces (common data entry error)
        email = email.replace(" ", "") if email else ""
        if original_email != email and original_email:
            result.warnings.append(f"Row {row_num}: Email had spaces removed: '{original_email}' -> '{email}'")
            
        # Skip rows without participant info
        if not name or not email:
            if name or email:  # Only warn if one field is present
                result.warnings.append(f"Row {row_num}: Skipped - missing name or email (name: {name!r}, email: {email!r})")
            continue
        
        expertise = row[expertise_idx].strip() if expertise_idx is not None and expertise_idx < len(row) else ""
        
        # Parse timestamp
        timestamp_str = row[timestamp_idx].strip() if timestamp_idx is not None and timestamp_idx < len(row) else ""
        if timestamp_str:
            timestamp, timestamp_warning = _parse_qualtrics_timestamp(timestamp_str)
            if timestamp_warning:
                result.warnings.append(f"Row {row_num}, Participant {name}: {timestamp_warning}")
        else:
            timestamp = datetime.now()
            result.warnings.append(f"Row {row_num}, Participant {name}: Empty timestamp field, using current time")
        
        # Generate participant ID
        participant_id = generate_participant_id(name, email)
        
        # Update or create participant info
        if participant_id in result.participants:
            # Update last_seen if this is a later response
            if timestamp > result.participants[participant_id].last_seen:
                result.participants[participant_id].last_seen = timestamp
            if timestamp < result.participants[participant_id].first_seen:
                result.participants[participant_id].first_seen = timestamp
        else:
            try:
                result.participants[participant_id] = ParticipantInfo(
                    participant_id=participant_id,
                    name=name,
                    email=email,
                    expertise=expertise,
                    first_seen=timestamp,
                    last_seen=timestamp,
                )
            except ValueError as e:
                # Invalid email format - skip this participant
                error_msg = f"Row {row_num}: Invalid participant data - {e}"
                warning_msg = f"Row {row_num}, Participant {name}: Invalid email format '{email}' - {e}"
                result.warnings.append(warning_msg)
                if strict:
                    validation_errors.append(error_msg)
                continue
        
        # Build a dict for this row using headers
        row_dict = dict(zip(headers, row))
        
        # Track empty responses for this participant
        empty_responses = []
        participant_has_responses = False
        
        # Parse responses for each case column
        for col_header, case_id in case_columns.items():
            response_text = row_dict.get(col_header, "").strip()
            
            # Track empty responses
            if not response_text:
                empty_responses.append(case_id)
                continue
            
            participant_has_responses = True
            
            # Load the case
            case = case_cache.get(case_id)
            if case is None:
                error_msg = f"Row {row_num}: Case {case_id} not found in llm_decisions or cases directory"
                warning_msg = f"Row {row_num}, Case {case_id}: Case file not found - response cannot be matched"
                result.warnings.append(warning_msg)
                if strict:
                    validation_errors.append(error_msg)
                else:
                    result.unmatched_responses.append((case_id, participant_id, response_text))
                continue
            
            # Match response to choice
            try:
                selected_choice = match_response_to_choice(response_text, case)
                result.responses.append(ParsedResponse(
                    case_id=case_id,
                    participant_id=participant_id,
                    selected_choice=selected_choice,
                    response_text=response_text,
                    timestamp=timestamp,
                ))
            except HumanResponseValidationError as e:
                warning_msg = f"Row {row_num}, Case {case_id}, Participant {participant_id}: Response text does not match either choice"
                result.warnings.append(warning_msg)
                if strict:
                    validation_errors.append(
                        f"Row {row_num}, Case {case_id}, Participant {participant_id}: {e}"
                    )
                else:
                    result.unmatched_responses.append((case_id, participant_id, response_text))
        
        # Warn about empty responses if participant has other valid responses
        if empty_responses and participant_has_responses:
            if len(empty_responses) == 1:
                result.warnings.append(f"Row {row_num}, Participant {name}: Empty response for case {empty_responses[0]}")
            else:
                result.warnings.append(f"Row {row_num}, Participant {name}: Empty responses for {len(empty_responses)} cases")
    
    # Raise collected errors if in strict mode
    if strict and validation_errors:
        error_summary = "\n\n".join(validation_errors)
        raise HumanResponseValidationError(
            f"Failed to parse {len(validation_errors)} response(s):\n\n{error_summary}"
        )
    
    return result


def _get_human_model_key(participant_id: str) -> str:
    """Generate the model key for a human participant.
    
    Human participants appear in the models dict with the key format:
    human/{participant_id}
    
    Args:
        participant_id: The anonymous participant ID (e.g., participant_a3f8c2d1)
        
    Returns:
        Model key string (e.g., human/participant_a3f8c2d1)
    """
    return f"human/{participant_id}"


def _create_human_run_result(response: ParsedResponse, participant: ParticipantInfo) -> RunResult:
    """Create a RunResult from a human response.
    
    Adapts human response data to the RunResult schema used for LLM decisions.
    The full_response dict contains human-specific metadata instead of LLM API response.
    
    Args:
        response: The parsed response from the survey
        participant: Participant metadata
        
    Returns:
        RunResult compatible with the LLM decision schema
    """
    # Create a human-specific response dict analogous to LLM API responses
    full_response = {
        "type": "human",
        "participant_id": response.participant_id,
        "participant_name": participant.name,
        "participant_expertise": participant.expertise,
        "response_text": response.response_text,
        "timestamp": response.timestamp.isoformat(),
        "created": int(response.timestamp.timestamp()),
    }
    
    return RunResult(
        full_response=full_response,
        parsed_choice=response.selected_choice,
    )


def _load_decision_record(
    case_id: str,
    output_dir: Path,
    llm_decisions_dir: Path | None = None,
    cases_dir: Path | None = None,
) -> DecisionRecord | None:
    """Load existing decision record or create a new one.
    
    First checks for an existing record in the output directory.
    If not found, creates a new record using the case data.
    
    Args:
        case_id: The case UUID
        output_dir: Directory where human decision records are saved
        llm_decisions_dir: Path to llm_decisions directory for loading case data
        cases_dir: Path to cases directory for loading case data
        
    Returns:
        DecisionRecord, or None if case cannot be loaded
    """
    record_path = output_dir / f"{case_id}.json"
    
    # Load existing record if present
    if record_path.exists():
        with open(record_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DecisionRecord(**data)
    
    # Create new record - need to load the case data
    case = load_case_by_uuid(case_id, llm_decisions_dir, cases_dir)
    if case is None:
        return None
    
    return DecisionRecord(case_id=case_id, case=case)


def _save_decision_record(record: DecisionRecord, output_dir: Path) -> None:
    """Save decision record to JSON with atomic write.
    
    Uses write-to-temp-then-move pattern for crash safety.
    
    Args:
        record: The DecisionRecord to save
        output_dir: Directory to save to
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    record_path = output_dir / f"{record.case_id}.json"
    
    # Atomic write: write to temp file, then move
    with tempfile.NamedTemporaryFile(
        mode="w", dir=output_dir, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp_file:
        tmp_file.write(record.model_dump_json(indent=2))
        tmp_file.flush()
        tmp_path = tmp_file.name
    
    shutil.move(tmp_path, record_path)


def save_human_decisions(
    parse_result: QualtricsParseResult,
    output_dir: str | Path | None = None,
    llm_decisions_dir: str | Path | None = None,
    cases_dir: str | Path | None = None,
) -> dict[str, int]:
    """Save parsed human decisions to per-case JSON files.
    
    Creates/updates DecisionRecord files at data/human_decisions/{case_id}.json
    using the same schema as LLM decisions. Human participants appear in the
    models dict with keys in the format: human/{participant_id}
    
    This function is idempotent - calling it multiple times with the same
    data will not create duplicate entries. Each participant can only have
    one response per case, and re-importing will update their existing entry.
    
    Args:
        parse_result: Result from parse_qualtrics_csv()
        output_dir: Directory to save decision records (default: data/human_decisions/)
        llm_decisions_dir: Directory containing LLM decisions for case loading
        cases_dir: Directory containing case files for case loading
        
    Returns:
        Dict with statistics:
        - cases_updated: Number of case files written
        - responses_saved: Total number of responses saved
        - participants_added: Number of participants added to registry
        
    Example:
        >>> result = parse_qualtrics_csv("survey.csv")
        >>> stats = save_human_decisions(result)
        >>> print(f"Saved {stats['responses_saved']} responses to {stats['cases_updated']} cases")
    """
    # Set default paths
    data_root = Path(__file__).parent.parent.parent / "data"
    
    if output_dir is None:
        output_dir = data_root / "human_decisions"
    else:
        output_dir = Path(output_dir)
    
    if llm_decisions_dir is None:
        llm_decisions_dir = data_root / "llm_decisions"
    else:
        llm_decisions_dir = Path(llm_decisions_dir)
    
    if cases_dir is None:
        cases_dir = data_root / "cases"
    else:
        cases_dir = Path(cases_dir)
    
    # Group responses by case_id
    responses_by_case: dict[str, list[ParsedResponse]] = {}
    for response in parse_result.responses:
        if response.case_id not in responses_by_case:
            responses_by_case[response.case_id] = []
        responses_by_case[response.case_id].append(response)
    
    # Track statistics
    stats = {
        "cases_updated": 0,
        "responses_saved": 0,
        "participants_added": 0,
    }
    
    # Process each case
    for case_id, responses in responses_by_case.items():
        # Load or create decision record
        record = _load_decision_record(case_id, output_dir, llm_decisions_dir, cases_dir)
        if record is None:
            # Skip cases we can't load
            continue
        
        # Add each human response to the models dict
        for response in responses:
            model_key = _get_human_model_key(response.participant_id)
            participant = parse_result.participants.get(response.participant_id)
            
            if participant is None:
                # This shouldn't happen, but skip if it does
                continue
            
            # Create the run result
            run_result = _create_human_run_result(response, participant)
            
            # Get or create model data for this human
            # For humans, temperature is not applicable, so we use 0.0
            if model_key not in record.models:
                record.models[model_key] = ModelDecisionData(temperature=0.0, runs=[])
            
            model_data = record.models[model_key]
            
            # Check if this participant already has a response for this case
            # (prevent duplicates on re-import)
            existing_response = False
            for i, existing_run in enumerate(model_data.runs):
                if existing_run.full_response.get("participant_id") == response.participant_id:
                    # Update existing response
                    model_data.runs[i] = run_result
                    existing_response = True
                    break
            
            if not existing_response:
                model_data.runs.append(run_result)
            
            stats["responses_saved"] += 1
        
        # Save the updated record
        _save_decision_record(record, output_dir)
        stats["cases_updated"] += 1
    
    # Save participant registry
    registry = ParticipantRegistry.load()
    initial_count = len(registry)
    
    for participant in parse_result.participants.values():
        registry.add_or_update(participant)
    
    registry.save()
    stats["participants_added"] = len(registry) - initial_count
    
    return stats
