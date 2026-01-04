"""
Verify Google Sheets API setup and credentials.

Run with: uv run python -m src.sheets.verify_setup
"""

import sys
from pathlib import Path

import yaml


def load_config() -> dict:
    """Load sheets configuration."""
    config_path = Path(__file__).parent / "sheets_config.yaml"
    if not config_path.exists():
        print("❌ sheets_config.yaml not found")
        sys.exit(1)
    
    with open(config_path) as f:
        return yaml.safe_load(f)


def verify_credentials(credentials_path: str) -> bool:
    """Verify that credentials file exists and is valid."""
    creds_path = Path(__file__).parent.parent.parent / credentials_path
    
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


def verify_gspread_auth(credentials_path: str) -> bool:
    """Test authentication with Google Sheets API."""
    creds_path = Path(__file__).parent.parent.parent / credentials_path
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = Credentials.from_service_account_file(
            str(creds_path),
            scopes=scopes
        )
        
        gc = gspread.authorize(credentials)
        print("✅ Successfully authenticated with Google Sheets API")
        return True
        
    except Exception as e:
        print(f"❌ Failed to authenticate with Google Sheets API: {e}")
        return False


def verify_spreadsheet_access(credentials_path: str, spreadsheet_id: str) -> bool:
    """Test access to the configured spreadsheet."""
    if not spreadsheet_id:
        print("⚠️  No spreadsheet_id configured in sheets_config.yaml")
        print("   Once you create/share a spreadsheet, add its ID to the config")
        return True  # Not a failure, just not configured yet
    
    creds_path = Path(__file__).parent.parent.parent / credentials_path
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = Credentials.from_service_account_file(
            str(creds_path),
            scopes=scopes
        )
        
        gc = gspread.authorize(credentials)
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
    config = load_config()
    credentials_path = config.get("credentials_path", "credentials/service_account.json")
    spreadsheet_id = config.get("spreadsheet_id", "")
    
    # Run checks
    checks_passed = 0
    total_checks = 3
    
    print("1. Checking credentials file...")
    if verify_credentials(credentials_path):
        checks_passed += 1
    print()
    
    print("2. Testing Google Sheets API authentication...")
    if verify_gspread_auth(credentials_path):
        checks_passed += 1
    print()
    
    print("3. Testing spreadsheet access...")
    if verify_spreadsheet_access(credentials_path, spreadsheet_id):
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

