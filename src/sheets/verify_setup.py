"""
Verify Google Sheets API setup and credentials.

Run with: uv run python -m src.sheets.verify_setup
"""

import sys
from pathlib import Path

from src.sheets.utils import load_config, get_credentials_path, get_gspread_client, SCOPES


def verify_credentials(config: dict) -> bool:
    """Verify that credentials file exists and is valid."""
    creds_path = get_credentials_path(config)
    
    if not creds_path.exists():
        print(f"❌ Credentials file not found at: {creds_path}")
        print("\n   To fix this:")
        print("   1. Go to Google Cloud Console (https://console.cloud.google.com)")
        print("   2. Create or select a project")
        print("   3. Enable the Google Sheets API")
        print("   4. Create a Service Account and download the JSON key")
        print(f"   5. Save the JSON file to: {creds_path}")
        return False
    
    # Try to load and validate the JSON structure
    import json
    try:
        with open(creds_path) as f:
            creds_data = json.load(f)
        
        required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
        missing = [f for f in required_fields if f not in creds_data]
        
        if missing:
            print(f"❌ Credentials file is missing required fields: {missing}")
            return False
        
        if creds_data.get("type") != "service_account":
            print(f"❌ Credentials must be for a service account, got: {creds_data.get('type')}")
            return False
        
        print(f"✅ Credentials file found and valid")
        print(f"   Project ID: {creds_data.get('project_id')}")
        print(f"   Service Account: {creds_data.get('client_email')}")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Credentials file is not valid JSON: {e}")
        return False


def verify_gspread_auth(config: dict) -> bool:
    """Test authentication with Google Sheets API."""
    try:
        gc = get_gspread_client(config)
        print("✅ Successfully authenticated with Google Sheets API")
        return True
        
    except Exception as e:
        print(f"❌ Failed to authenticate with Google Sheets API: {e}")
        return False


def verify_spreadsheet_access(config: dict) -> bool:
    """Test access to the configured spreadsheet."""
    import gspread
    
    spreadsheet_id = config.get("spreadsheet_id")
    if not spreadsheet_id:
        print("⚠️  No spreadsheet_id configured in sheets_config.yaml")
        print("   Once you create/share a spreadsheet, add its ID to the config")
        return True  # Not a failure, just not configured yet
    
    try:
        gc = get_gspread_client(config)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        
        print(f"✅ Successfully accessed spreadsheet: {spreadsheet.title}")
        print(f"   URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        return True
        
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ Spreadsheet not found or not shared with service account")
        print("   Make sure to share the spreadsheet with the service account email")
        return False
    except Exception as e:
        print(f"❌ Failed to access spreadsheet: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Google Sheets Integration - Setup Verification")
    print("=" * 60)
    print()
    
    # Load config
    try:
        config = load_config()
    except FileNotFoundError:
        print("❌ sheets_config.yaml not found")
        return 1
    
    # Run checks
    checks_passed = 0
    total_checks = 3
    
    print("1. Checking credentials file...")
    if verify_credentials(config):
        checks_passed += 1
    print()
    
    print("2. Testing Google Sheets API authentication...")
    if verify_gspread_auth(config):
        checks_passed += 1
    print()
    
    print("3. Testing spreadsheet access...")
    if verify_spreadsheet_access(config):
        checks_passed += 1
    print()
    
    # Summary
    print("=" * 60)
    if checks_passed == total_checks:
        print(f"✅ All {total_checks} checks passed! Setup is complete.")
    else:
        print(f"⚠️  {checks_passed}/{total_checks} checks passed. See above for details.")
    print("=" * 60)
    
    return 0 if checks_passed == total_checks else 1


if __name__ == "__main__":
    sys.exit(main())

