"""Google Sheets integration for ValueBench case editing."""

from src.sheets.utils import (
    load_config,
    get_gspread_client,
    get_credentials_path,
    open_spreadsheet,
    get_worksheet,
    SCOPES,
    SHEETS_DIR,
    CONFIG_PATH,
    PROJECT_ROOT,
)

# Export functions for push operations
from src.sheets.export_to_sheets import (
    load_cases_raw,
    extract_case_row,
    get_header_row,
    get_sheet_case_ids,
    push_rows_to_sheet,
    prepare_cases_for_export,
)

# Export functions for pull operations
from src.sheets.import_from_sheets import (
    ValidationResult,
    ImportReport,
    fetch_all_sheet_rows,
    fetch_sheet_rows_by_ids,
    parse_sheet_row,
    validate_cases,
    update_case_json,
    pull_sheet_changes,
)

# Sync operations (bidirectional sync)
from src.sheets.case_sync import (
    CaseCategory,
    CaseInfo,
    SyncPlan,
    compare_cases,
    get_local_case_ids,
    get_comparison_summary,
    execute_sync,
    sync,
)

__all__ = [
    # Utils
    "load_config",
    "get_gspread_client",
    "get_credentials_path",
    "open_spreadsheet",
    "get_worksheet",
    "SCOPES",
    "SHEETS_DIR",
    "CONFIG_PATH",
    "PROJECT_ROOT",
    # Push functions (export)
    "load_cases_raw",
    "extract_case_row",
    "get_header_row",
    "get_sheet_case_ids",
    "push_rows_to_sheet",
    "prepare_cases_for_export",
    # Pull functions (import)
    "ValidationResult",
    "ImportReport",
    "fetch_all_sheet_rows",
    "fetch_sheet_rows_by_ids",
    "parse_sheet_row",
    "validate_cases",
    "update_case_json",
    "pull_sheet_changes",
    # Sync operations
    "CaseCategory",
    "CaseInfo",
    "SyncPlan",
    "compare_cases",
    "get_local_case_ids",
    "get_comparison_summary",
    "execute_sync",
    "sync",
]

