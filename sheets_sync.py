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
            # Try robust parsing of the credentials JSON. Some users put unquoted keys
            # or single quotes in their .env; try json.loads first, then fallback to
            # ast.literal_eval after simple replacements.
            creds_dict = None
            try:
                creds_dict = json.loads(credentials_json)
            except Exception:
                try:
                    import ast
                    # Replace smart single quotes with plain ones and attempt literal_eval
                    cleaned = credentials_json.replace("\n", "\\n")
                    creds_dict = ast.literal_eval(cleaned)
                except Exception as e:
                    # Re-raise with a clearer message
                    raise ValueError(f"Invalid GOOGLE_CREDENTIALS_JSON: {e}")
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            self.client = gspread.authorize(creds)
            
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Setup worksheets with PROPER headers
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
        """Get or create worksheet with PROPER headers for job tracking"""
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=15)
            
            # PROPER HEADERS for job application tracking
            headers = [
                'Job ID',           # Unique job identifier
                'Company Name',     # Company/Organization
                'Job Role',         # Position/Title
                'Location',         # Job location
                'Eligibility',      # Year/requirements
                'Contact Email',    # Email address
                'Contact Phone',    # Phone number  
                'Recruiter Name',   # HR/Recruiter name
                'Application Link', # External application URL
                'Application Method', # How to apply (email/link/phone)
                'Job Description',  # Full job posting text
                'Email Subject',    # Generated email subject
                'Email Body',       # Generated personalized email
                'Status',           # pending/applied/rejected
                'Created At'        # When job was added
            ]
            worksheet.append_row(headers)
        return worksheet
    
    def sync_job(self, job_data: Dict) -> bool:
        """Sync job to appropriate Google Sheet with PROPER data mapping"""
        if not self.client:
            return False
            
        try:
            # Use the 'email' sheet if an email is present, otherwise use 'non-email'
            worksheet = self.sheet_email if job_data.get('email') else self.sheet_other
            
            if not worksheet:
                return False
            
            # PROPER DATA MAPPING - all fields from LLM extraction
            row = [
                job_data.get('job_id'),           # Job ID
                job_data.get('company_name'),     # Company Name
                job_data.get('job_role'),         # Job Role
                job_data.get('location'),         # Location
                job_data.get('eligibility'),      # Eligibility
                job_data.get('email'),           # Contact Email
                job_data.get('phone'),           # Contact Phone
                job_data.get('recruiter_name'),   # Recruiter Name (not split)
                job_data.get('application_link'), # Application Link
                job_data.get('application_method'), # Application Method
                job_data.get('jd_text'),         # Job Description
                job_data.get('email_subject'),   # Email Subject
                job_data.get('email_body'),      # Email Body
                job_data.get('status', 'pending'), # Status
                job_data.get('created_at')       # Created At
            ]
            
            # Find the next empty row and update it to prevent column shifting issues
            next_row = len(worksheet.get_all_values()) + 1
            worksheet.update(f'A{next_row}', [row])
            return True
            
        except Exception as e:
            print(f"  ✗ Google Sheets sync error: {str(e)}")
            return False