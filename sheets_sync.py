import gspread
from google.oauth2.service_account import Credentials
import json
import logging
from typing import Dict
import time

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
            
            self.logger.info("Google Sheets connected: " + spreadsheet.url)
            
        except gspread.exceptions.SpreadsheetNotFound:
            self.logger.error("Google Sheets setup failed: Spreadsheet not found. Check the SPREADSHEET_ID.")
            self.client = None
        except Exception as e:
            self.logger.error("Google Sheets setup failed: " + str(e), exc_info=True)
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
            self.logger.error("Google Sheets client not initialized")
            return False
            
        try:
            self.logger.info(f"Syncing job {job_data.get('job_id', 'unknown')}")
            
            # COMPATIBILITY FIX: Handle missing fields gracefully
            # Extract available fields with fallbacks
            job_relevance = job_data.get('job_relevance', 'relevant')  # Default to relevant
            experience_required = job_data.get('experience_required', 'Not specified')
            phone = job_data.get('phone') or ''
            recruiter_name = job_data.get('recruiter_name') or ''
            application_link = job_data.get('application_link') or ''
            
            # Route to appropriate worksheet based on sheet_name
            sheet_name = job_data.get('sheet_name')
            
            # Fallback: If sheet_name is missing, determine based on email presence only
            if not sheet_name:
                has_email = bool(job_data.get('email'))
                sheet_name = 'email' if has_email else 'non-email'
                self.logger.warning(f"Job {job_data.get('job_id')} missing sheet_name. Inferred: {sheet_name}")

            worksheet = None
            if sheet_name == 'email':
                worksheet = self.sheet_email
            elif sheet_name == 'non-email':
                worksheet = self.sheet_other
            else:
                # Fallback for legacy sheet names (email-exp, non-email-exp)
                if 'email' in sheet_name:
                    worksheet = self.sheet_email
                    self.logger.info(f"Routing legacy '{sheet_name}' to 'email' sheet")
                else:
                    worksheet = self.sheet_other
                    self.logger.info(f"Routing legacy '{sheet_name}' to 'non-email' sheet")
            
            if not worksheet:
                self.logger.error(f"Target worksheet not available for sheet_name='{sheet_name}'. Job ID: {job_data.get('job_id')}")
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
                str(job_data.get('created_at', '')),      # Created At (converted to string)
                experience_required,                 # NEW: Experience requirements (with fallback)
                job_relevance                        # NEW: Job relevance (with fallback)
            ]
            
            # SAFETY: Truncate fields that might exceed Google Sheets cell limit (50k chars)
            # Index 10 is jd_text, Index 12 is email_body
            if len(str(row[10])) > 45000:
                row[10] = str(row[10])[:45000] + "...(truncated)"
            if len(str(row[12])) > 45000:
                row[12] = str(row[12])[:45000] + "...(truncated)"
            
            self.logger.info(f"Prepared row data: {len(row)} columns")
            
            try:
                # ROBUST SYNC FIX:
                # Instead of append_row (which can be confused by ragged columns like Email Body),
                # we find the next empty row based specifically on Column A (Job ID).
                col_a_values = worksheet.col_values(1)
                
                # Check for existing job ID to prevent duplicates (Idempotency)
                if str(job_data.get('job_id')) in col_a_values:
                    self.logger.debug(f"Job {job_data.get('job_id')} already in sheet '{sheet_name}', skipping append.")
                    return True

                next_row = len(col_a_values) + 1
                
                # Ensure sheet has enough rows
                if next_row > worksheet.row_count:
                    worksheet.add_rows(100)
                
                # Update the specific range A{row}:Q{row} (17 columns)
                cell_range = f"A{next_row}:Q{next_row}"
                worksheet.update(range_name=cell_range, values=[row])
                
                # RATE LIMITING: Sleep briefly to avoid hitting Google API quotas (60 req/min)
                time.sleep(1.0)
                
                self.logger.info(f"Successfully synced job {job_data.get('job_id', 'unknown')} to Google Sheets")
                return True
            except Exception as e:
                self.logger.warning(f"Sync failed for '{sheet_name}', attempting refresh and retry. Error: {e}")
                
                # RETRY LOGIC: Refresh the worksheet object and try again
                # This handles cases where the sheet was modified (rows added) and the old object is stale
                try:
                    spreadsheet = self.client.open_by_key(self.spreadsheet_id)
                    worksheet = self._get_or_create_worksheet(spreadsheet, sheet_name)
                    
                    # Update the cached reference
                    if sheet_name == 'email': self.sheet_email = worksheet
                    elif sheet_name == 'non-email': self.sheet_other = worksheet
                    elif sheet_name == 'email-exp': self.sheet_email_exp = worksheet
                    elif sheet_name == 'non-email-exp': self.sheet_other_exp = worksheet
                    
                    # Retry with robust logic
                    col_a_values = worksheet.col_values(1)
                    next_row = len(col_a_values) + 1
                    if next_row > worksheet.row_count:
                        worksheet.add_rows(100)
                    cell_range = f"A{next_row}:Q{next_row}"
                    worksheet.update(range_name=cell_range, values=[row])
                    
                    self.logger.info(f"Retry successful for job {job_data.get('job_id', 'unknown')}")
                    return True
                except Exception as retry_e:
                    self.logger.error(f"Retry failed for job {job_data.get('job_id')}: {retry_e}")
                    raise retry_e # Re-raise to be caught by outer block
            
        except Exception as e:
            self.logger.error(f"Google Sheets sync error for job {job_data.get('job_id', 'unknown')}: {str(e)}")
            self.logger.error(f"Job data keys: {list(job_data.keys())}")
            return False

    def get_jobs_needing_email_generation(self, sheet_name: str) -> list[Dict]:
        """
        Retrieves jobs from the specified sheet that need email body generation.
        A job needs email generation if its 'Email Body' column is empty.
        """
        if not self.client:
            self.logger.error("Google Sheets client not initialized.")
            return []

        worksheet = None
        if sheet_name == "email":
            worksheet = self.sheet_email
        elif sheet_name == "email-exp":
            worksheet = self.sheet_email_exp
        else:
            self.logger.warning(f"Invalid sheet name '{sheet_name}' for email generation.")
            return []

        if not worksheet:
            self.logger.error(f"Worksheet '{sheet_name}' not available.")
            return []

        try:
            records = worksheet.get_all_records()
            jobs_needing_generation = []
            for record in records:
                # Assuming 'Email Body' is the header for the email body column
                if not record.get('Email Body'):
                    jobs_needing_generation.append(record)
            self.logger.info(f"Found {len(jobs_needing_generation)} jobs needing email generation in sheet '{sheet_name}'.")
            return jobs_needing_generation
        except Exception as e:
            self.logger.error(f"Error retrieving jobs from sheet '{sheet_name}': {e}")
            return []

    def update_job_email_body_in_sheet(self, job_id: str, email_body: str, sheet_name: str) -> bool:
        """
        Updates the 'Email Body' for a specific job in the specified Google Sheet.
        """
        if not self.client:
            self.logger.error("Google Sheets client not initialized.")
            return False

        worksheet = None
        if sheet_name == "email":
            worksheet = self.sheet_email
        elif sheet_name == "email-exp":
            worksheet = self.sheet_email_exp
        else:
            self.logger.warning(f"Invalid sheet name '{sheet_name}' for email body update.")
            return False

        if not worksheet:
            self.logger.error(f"Worksheet '{sheet_name}' not available.")
            return False

        try:
            # Find the row with the matching job_id
            cell = worksheet.find(job_id, in_column=1)  # Assuming 'Job ID' is in the first column
            if cell:
                # Update the 'Email Body' column (assuming it's the 13th column, index 12)
                worksheet.update_cell(cell.row, 13, email_body)
                self.logger.info(f"Successfully updated email body for job {job_id} in sheet '{sheet_name}'.")
                return True
            else:
                self.logger.warning(f"Job ID '{job_id}' not found in sheet '{sheet_name}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error updating email body for job {job_id} in sheet '{sheet_name}': {e}")
            return False

    def get_all_job_ids(self, sheet_name: str) -> set:
        """Get all Job IDs present in a specific sheet to prevent duplicates"""
        if not self.client:
            return set()
            
        worksheet = None
        if sheet_name == 'email': worksheet = self.sheet_email
        elif sheet_name == 'non-email': worksheet = self.sheet_other
        elif sheet_name == 'email-exp': worksheet = self.sheet_email_exp
        elif sheet_name == 'non-email-exp': worksheet = self.sheet_other_exp
        
        if not worksheet:
            return set()
            
        try:
            # Assuming Job ID is in column 1. col_values(1) returns the list of values.
            ids = worksheet.col_values(1)
            # Remove header if present
            if ids and ids[0] == 'Job ID':
                ids = ids[1:]
            return set(ids)
        except Exception as e:
            self.logger.error(f"Failed to fetch Job IDs from {sheet_name}: {e}")
            return set()

class MultiSheetSync:
    """
    Wrapper to sync jobs to multiple Google Strings.
    Writes are broadcast to ALL sheets.
    Reads are performed ONLY on the PRIMARY sheet.
    """
    def __init__(self, credentials_json: str, primary_spreadsheet_id: str, additional_spreadsheet_ids: list[str] = None):
        self.logger = logging.getLogger(__name__)
        self.primary_sync = GoogleSheetsSync(credentials_json, primary_spreadsheet_id)
        self.additional_syncs = []
        
        if additional_spreadsheet_ids:
            for sheet_id in additional_spreadsheet_ids:
                if sheet_id and sheet_id != primary_spreadsheet_id:
                    try:
                        self.logger.info(f"Initializing additional sync for sheet ID: {sheet_id}")
                        sync = GoogleSheetsSync(credentials_json, sheet_id)
                        if sync.client:
                            self.additional_syncs.append(sync)
                    except Exception as e:
                        self.logger.error(f"Failed to initialize additional sheet {sheet_id}: {e}")
        
        self.client = self.primary_sync.client # Expose client for checks

    def sync_job(self, job_data: Dict) -> bool:
        """Sync job to ALL configured sheets"""
        # Always sync to primary
        primary_success = self.primary_sync.sync_job(job_data)
        
        # Broadcast to others (best effort)
        for sync in self.additional_syncs:
            try:
                sync.sync_job(job_data)
            except Exception as e:
                self.logger.error(f"Failed to sync to additional sheet {sync.spreadsheet_id}: {e}")
                
        return primary_success

    # --- Read-only methods delegate to PRIMARY only ---
    
    def get_jobs_needing_email_generation(self, sheet_name: str) -> list[Dict]:
        return self.primary_sync.get_jobs_needing_email_generation(sheet_name)

    def update_job_email_body_in_sheet(self, job_id: str, email_body: str, sheet_name: str) -> bool:
        # We only update email body in the primary sheet for now, as that's where the app manages state
        # If users are running their own scripts, they'll generate their own emails
        return self.primary_sync.update_job_email_body_in_sheet(job_id, email_body, sheet_name)

    def get_all_job_ids(self, sheet_name: str) -> set:
        """Get all job IDs from ALL configured sheets (primary + additional)"""
        all_ids = set()
        
        # Get IDs from primary sheet
        try:
            all_ids.update(self.primary_sync.get_all_job_ids(sheet_name))
        except Exception as e:
            self.logger.error(f"Failed to get IDs from primary sheet: {e}")
        
        # Get IDs from additional sheets
        for sync in self.additional_syncs:
            try:
                all_ids.update(sync.get_all_job_ids(sheet_name))
            except Exception as e:
                self.logger.error(f"Failed to get IDs from additional sheet {sync.spreadsheet_id}: {e}")
        
        return all_ids