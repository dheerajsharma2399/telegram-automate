import gspread
from google.oauth2.service_account import Credentials
import json
from typing import Dict

class GoogleSheetsSync:
    def __init__(self, credentials_json: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.sheet_email = None
        self.sheet_other = None
        self.client = None
        if credentials_json and spreadsheet_id:
            self._setup_sheets(credentials_json)
    
    def _setup_sheets(self, credentials_json: str):
        """Setup Google Sheets connection"""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds_dict = json.loads(credentials_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            self.client = gspread.authorize(creds)
            
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Setup worksheets
            self.sheet_email = self._get_or_create_worksheet(spreadsheet, "email")
            self.sheet_other = self._get_or_create_worksheet(spreadsheet, "non-email")
            
            print(f"✓ Google Sheets connected: {spreadsheet.url}")
            
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"✗ Google Sheets setup failed: Spreadsheet not found. Check the SPREADSHEET_ID.")
            self.client = None
        except Exception as e:
            print(f"✗ Google Sheets setup failed: {str(e)}")
            self.client = None
    
    def _get_or_create_worksheet(self, spreadsheet, sheet_name: str):
        """Get or create worksheet"""
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=9)
            headers = ['ID', 'First Name', 'Last Name', 'Email', 'Company', 
                      'Status', 'Updated At', 'JD Text', 'Email Subject']
            worksheet.append_row(headers)
        return worksheet
    
    def sync_job(self, job_data: Dict) -> bool:
        """Sync job to appropriate Google Sheet"""
        if not self.client:
            return False
            
        try:
            # Use the 'email' sheet if an email is present, otherwise use 'non-email'
            worksheet = self.sheet_email if job_data.get('email') else self.sheet_other
            
            if not worksheet:
                return False
            
            row = [
                job_data.get('job_id'),
                job_data.get('first_name'),
                job_data.get('last_name'),
                job_data.get('email'),
                job_data.get('company_name'),
                job_data.get('status', ''),
                job_data.get('updated_at', ''),
                job_data.get('jd_text'),
                job_data.get('email_subject')
            ]
            
            # Find the next empty row and update it to prevent column shifting issues
            next_row = len(worksheet.get_all_values()) + 1
            worksheet.update(f'A{next_row}', [row])
            return True
            
        except Exception as e:
            print(f"  ✗ Google Sheets sync error: {str(e)}")
            return False
