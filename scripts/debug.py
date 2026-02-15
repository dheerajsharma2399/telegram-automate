# e:\Assignment_data\telegram automate\debug_sheets.py
import os
import logging
from dotenv import load_dotenv
from sheets_sync import GoogleSheetsSync

# Setup logging to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sheets_connection():
    load_dotenv()
    
    creds = os.getenv('GOOGLE_CREDENTIALS_JSON')
    sheet_id = os.getenv('SPREADSHEET_ID')
    
    print(f"DEBUG: SPREADSHEET_ID: {sheet_id}")
    if not creds:
        print("ERROR: GOOGLE_CREDENTIALS_JSON is missing")
        return
    
    print(f"DEBUG: Creds length: {len(creds)}")
    
    try:
        print("Attempting to connect to Google Sheets...")
        sync = GoogleSheetsSync(creds, sheet_id)
        
        if sync.client:
            print("✅ Connection Successful!")
            try:
                sheet_title = sync.client.open_by_key(sheet_id).title
                print(f"📄 Spreadsheet Title: {sheet_title}")
                
                # Test worksheets existence
                sheets = ['email', 'non-email', 'email-exp', 'non-email-exp']
                print("\nChecking Worksheets:")
                for s in sheets:
                    try:
                        ws = sync.client.open_by_key(sheet_id).worksheet(s)
                        print(f"  ✅ Worksheet '{s}' found.")
                    except Exception as e:
                        print(f"  ❌ Worksheet '{s}' error: {e}")
                        print(f"     (The bot will attempt to create this sheet automatically on next run)")
            except Exception as e:
                print(f"❌ Error accessing spreadsheet: {e}")
        else:
            print("❌ Connection Failed (Client is None). Check app.log for detailed error messages.")
            
    except Exception as e:
        print(f"❌ Exception during init: {e}")

if __name__ == "__main__":
    test_sheets_connection()
