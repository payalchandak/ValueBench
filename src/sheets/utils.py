"""
Shared utilities for Google Sheets integration.

This module provides common functionality used by export, import, and sync operations:
- Configuration loading
- Authentication and gspread client creation
- Path resolution helpers
"""

from pathlib import Path
from typing import Optional

import yaml
import gspread
from google.oauth2.service_account import Credentials


# Google API scopes required for sheets operations
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Module paths
SHEETS_DIR = Path(__file__).parent
CONFIG_PATH = SHEETS_DIR / "sheets_config.yaml"
PROJECT_ROOT = SHEETS_DIR.parent.parent


def load_config() -> dict:
    """
    Load sheets configuration from sheets_config.yaml.
    
    Returns:
        Dictionary containing the configuration
        
    Raises:
        FileNotFoundError: If the config file doesn't exist
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_credentials_path(config: Optional[dict] = None) -> Path:
    """
    Get the absolute path to the credentials file.
    
    Args:
        config: Optional config dict. If not provided, loads from file.
        
    Returns:
        Path object pointing to the credentials file
    """
    if config is None:
        config = load_config()
    
    credentials_path = config.get("credentials_path", "credentials/service_account.json")
    return PROJECT_ROOT / credentials_path


def get_gspread_client(config: Optional[dict] = None) -> gspread.Client:
    """
    Create an authenticated gspread client.
    
    Args:
        config: Optional config dict. If not provided, loads from file.
        
    Returns:
        Authenticated gspread Client object
        
    Raises:
        FileNotFoundError: If credentials file doesn't exist
    """
    creds_path = get_credentials_path(config)
    
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_path}\n"
            "Run 'uv run python -m src.sheets.verify_setup' for setup instructions."
        )
    
    credentials = Credentials.from_service_account_file(
        str(creds_path),
        scopes=SCOPES
    )
    
    return gspread.authorize(credentials)


def open_spreadsheet(
    config: Optional[dict] = None,
    client: Optional[gspread.Client] = None
) -> gspread.Spreadsheet:
    """
    Open the configured spreadsheet.
    
    Args:
        config: Optional config dict. If not provided, loads from file.
        client: Optional gspread client. If not provided, creates one.
        
    Returns:
        gspread Spreadsheet object
        
    Raises:
        ValueError: If no spreadsheet_id is configured
        gspread.exceptions.SpreadsheetNotFound: If spreadsheet not found or not shared
    """
    if config is None:
        config = load_config()
    
    spreadsheet_id = config.get("spreadsheet_id")
    if not spreadsheet_id:
        raise ValueError(
            "No spreadsheet_id configured in sheets_config.yaml\n"
            "Create a Google Sheet and add its ID to the config file."
        )
    
    if client is None:
        client = get_gspread_client(config)
    
    return client.open_by_key(spreadsheet_id)


def get_worksheet(
    spreadsheet: gspread.Spreadsheet,
    sheet_name: Optional[str] = None,
    config: Optional[dict] = None,
    create_if_missing: bool = False,
    rows: int = 100,
    cols: int = 20
) -> gspread.Worksheet:
    """
    Get a worksheet from the spreadsheet.
    
    Args:
        spreadsheet: The gspread Spreadsheet object
        sheet_name: Name of the worksheet. If not provided, uses config.
        config: Optional config dict for getting default sheet name.
        create_if_missing: If True, create the worksheet if it doesn't exist.
        rows: Number of rows if creating new worksheet.
        cols: Number of columns if creating new worksheet.
        
    Returns:
        gspread Worksheet object
        
    Raises:
        gspread.exceptions.WorksheetNotFound: If worksheet not found and create_if_missing is False
    """
    if sheet_name is None:
        if config is None:
            config = load_config()
        sheet_name = config.get("sheet_name", "Cases")
    
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        if create_if_missing:
            return spreadsheet.add_worksheet(title=sheet_name, rows=rows, cols=cols)
        raise

