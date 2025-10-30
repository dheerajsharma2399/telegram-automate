import gspread
from google.oauth2.service_account import Credentials
import json
import logging
from typing import Dict

class GoogleSheetsSync:
    def __init__(self, credentials_json: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.sheet_email = None
        self.sheet_other = None
        self.sheet_email_exp = None  # NEW: Irrelevant jobs with email
        self.sheet_other_exp = None  # NEW: Irrelevant jobs with link/phone
        self.client = None
        self.logger = logging.getLogger(__name__)
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
            
            # Setup worksheets with PROPER headers for job relevance filtering
            self.sheet_email = self._get_or_create_worksheet(spreadsheet, "email")        # Relevant jobs with email
            self.sheet_other = self._get_or_create_worksheet(spreadsheet, "non-email")    # Relevant jobs with link/phone
            self.sheet_email_exp = self._get_or_create_worksheet(spreadsheet, "email-exp")    # Irrelevant jobs with email
            self.sheet_other_exp = self._get_or_create_worksheet(spreadsheet, "non-email-exp")  # Irrelevant jobs with link/phone
            
            print("Google Sheets connected: " + spreadsheet.url)
            
        except gspread.exceptions.SpreadsheetNotFound:
            print("Google Sheets setup failed: Spreadsheet not found. Check the SPREADSHEET_ID.")
            self.client = None
        except Exception as e:
            print("Google Sheets setup failed: " + str(e))
            self.client = None
    
    def _get_or_create_worksheet(self, spreadsheet, sheet_name: str):
        """Get or create worksheet with PROPER headers for job tracking"""
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=17)  # Updated for new relevance fields
            
            # ENHANCED HEADERS for job relevance filtering
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
                'Created At',       # When job was added
                'Experience Required', # NEW: Experience requirements
                'Job Relevance'     # NEW: relevant/irrelevant for freshers
            ]
            worksheet.append_row(headers)
        return worksheet
    
    def sync_job(self, job_data: Dict) -> bool:
        """Sync job to appropriate Google Sheet with robust field mapping"""
        if not self.client:
            logger = logging.getLogger(__name__)
            logger.error("Google Sheets client not initialized")
            return False
            
        try:
            logger = logging.getLogger(__name__)
            logger.info(f"Syncing job {job_data.get('job_id', 'unknown')}")
            
            # COMPATIBILITY FIX: Handle missing fields gracefully
            # Extract available fields with fallbacks
            job_relevance = job_data.get('job_relevance', 'relevant')  # Default to relevant
            experience_required = job_data.get('experience_required', 'Not specified')
            phone = job_data.get('phone') or ''
            recruiter_name = job_data.get('recruiter_name') or ''
            application_link = job_data.get('application_link') or ''
            
            # Route to appropriate worksheet based on relevance and contact method
            has_email = bool(job_data.get('email'))
            
            if job_relevance == 'relevant':
                if has_email:
                    worksheet = self.sheet_email        # Relevant + Email
                    logger.info("Routing to 'email' sheet (relevant with email)")
                else:
                    worksheet = self.sheet_other        # Relevant + Link/Phone
                    logger.info("Routing to 'non-email' sheet (relevant without email)")
            else:  # irrelevant
                if has_email:
                    worksheet = self.sheet_email_exp    # Irrelevant + Email
                    logger.info("Routing to 'email-exp' sheet (irrelevant with email)")
                else:
                    worksheet = self.sheet_other_exp    # Irrelevant + Link/Phone
                    logger.info("Routing to 'non-email-exp' sheet (irrelevant without email)")
            
            if not worksheet:
                logger.error(f"Target worksheet not available for relevance={job_relevance}, has_email={has_email}")
                return False
            
            # ROBUST DATA MAPPING with missing field handling
            row = [
                job_data.get('job_id', ''),           # Job ID
                job_data.get('company_name', ''),     # Company Name
                job_data.get('job_role', ''),         # Job Role
                job_data.get('location', ''),         # Location
                job_data.get('eligibility', ''),      # Eligibility
                job_data.get('email', ''),           # Contact Email
                phone,                               # Contact Phone (with fallback)
                recruiter_name,                      # Recruiter Name (with fallback)
                application_link,                    # Application Link (with fallback)
                job_data.get('application_method', ''), # Application Method
                job_data.get('jd_text', ''),         # Job Description
                job_data.get('email_subject', ''),   # Email Subject
                job_data.get('email_body', ''),      # Email Body
                job_data.get('status', 'pending'),   # Status
                job_data.get('created_at', ''),      # Created At
                experience_required,                 # NEW: Experience requirements (with fallback)
                job_relevance                        # NEW: Job relevance (with fallback)
            ]
            
            logger.info(f"Prepared row data: {len(row)} columns")
            logger.debug(f"Row content: {row[:5]}...")  # Log first 5 columns for debugging
            
            # Find the next empty row
            all_values = worksheet.get_all_values()
            next_row = len(all_values) + 1
            
            logger.info(f"Writing to row {next_row} in worksheet")
            
            # Update the worksheet
            worksheet.update(f'A{next_row}', [row])
            
            logger.info(f"Successfully synced job {job_data.get('job_id', 'unknown')} to Google Sheets")
            return True
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Google Sheets sync error for job {job_data.get('job_id', 'unknown')}: {str(e)}")
            logger.error(f"Job data keys: {list(job_data.keys())}")
            return False