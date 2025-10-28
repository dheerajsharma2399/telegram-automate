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
            
            # Setup worksheets
            self.sheet_email = self._get_or_create_worksheet(spreadsheet, "email")
            self.sheet_other = self._get_or_create_worksheet(spreadsheet, "non-email")
            
            print(f"V Google Sheets connected: {spreadsheet.url}")
            
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"X Google Sheets setup failed: Spreadsheet not found. Check the SPREADSHEET_ID.")
            self.client = None
        except Exception as e:
            print(f"X Google Sheets setup failed: {str(e)}")
            self.client = None
    
    def _get_or_create_worksheet(self, spreadsheet, sheet_name: str):
        """Get or create worksheet"""
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
            headers = ['ID', 'First Name', 'Last Name', 'Email', 'Company', 
                      'Status', 'Updated At', 'JD Text', 'Email Subject', 'Email Body']
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
                job_data.get('email_subject'),
                job_data.get('email_body')
            ]
            
            # Find the next empty row and update it to prevent column shifting issues
            next_row = len(worksheet.get_all_values()) + 1
            worksheet.update(f'A{next_row}', [row])
            return True
            
        except Exception as e:
            print(f"  ✗ Google Sheets sync error: {str(e)}")
            return False

    def generate_email_bodies_from_sheet(self, llm_processor, db=None, sheet_name='email', limit=None):
        """Read JD Text from the sheet and generate email_body for rows missing it.

        - llm_processor: instance of LLMProcessor with generate_email_body(job, jd_text)
        - db: optional Database instance to persist generated email_body back to DB rows (by job_id)
        - sheet_name: worksheet name to operate on (default 'email')
        - limit: optional max number of rows to generate in one run
        Returns: dict summary {generated: int, errors: int}
        """
        if not self.client:
            print("GoogleSheetsSync: client not configured")
            return {'generated': 0, 'errors': 0}

        try:
            worksheet = None
            try:
                worksheet = self.client.open_by_key(self.spreadsheet_id).worksheet(sheet_name)
            except Exception:
                # fallback to stored worksheet object
                worksheet = self.sheet_email if sheet_name == 'email' else self.sheet_other

            if not worksheet:
                print(f"Worksheet {sheet_name} not available")
                return {'generated': 0, 'errors': 0}

            vals = worksheet.get_all_values()
            if not vals or len(vals) < 2:
                return {'generated': 0, 'errors': 0}

            header = [h.strip().lower() for h in vals[0]]
            # find indices
            def idx_of(name_list):
                for name in name_list:
                    if name in header:
                        return header.index(name)
                return None

            idx_id = idx_of(['id', 'job id', 'job_id'])
            idx_company = idx_of(['company', 'company name', 'company_name'])
            idx_role = idx_of(['role', 'job_role', 'job role'])
            idx_jd = idx_of(['jd text', 'jd_text', 'job description', 'description'])
            idx_body = idx_of(['email body', 'email_body', 'email_body'])

            if idx_jd is None or idx_body is None:
                print('Could not find JD Text or Email Body columns in sheet')
                return {'generated': 0, 'errors': 0}

            generated = 0
            errors = 0
            rows = vals[1:]
            for i, row in enumerate(rows, start=2):
                if limit and generated >= limit:
                    break
                try:
                    jd_text = (row[idx_jd] if idx_jd < len(row) else '').strip()
                    current_body = (row[idx_body] if idx_body < len(row) else '').strip()
                    if not jd_text or current_body:
                        continue

                    # Build a minimal job dict for the generator
                    job = {}
                    if idx_id is not None and idx_id < len(row):
                        job['job_id'] = row[idx_id]
                    if idx_company is not None and idx_company < len(row):
                        job['company_name'] = row[idx_company]
                    if idx_role is not None and idx_role < len(row):
                        job['job_role'] = row[idx_role]

                    # Generate email body using provided processor
                    try:
                        email_body = llm_processor.generate_email_body(job, jd_text)
                    except Exception as e:
                        print(f"Failed to generate email body for row {i}: {e}")
                        errors += 1
                        continue

                    # Write back to sheet
                    try:
                        # worksheet.update_cell(row, col, value)
                        worksheet.update_cell(i, idx_body + 1, email_body)
                    except Exception as e:
                        print(f"Failed to write email body to sheet for row {i}: {e}")
                        errors += 1
                        continue

                    # Optionally update DB
                    try:
                        if db and idx_id is not None:
                            job_id_val = row[idx_id]
                            if job_id_val:
                                try:
                                    db.update_job_email_body(job_id_val, email_body)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    generated += 1
                except Exception as e:
                    print(f"Unexpected error processing sheet row {i}: {e}")
                    errors += 1

            return {'generated': generated, 'errors': errors}

        except Exception as e:
            print(f"generate_email_bodies_from_sheet failed: {e}")
            return {'generated': 0, 'errors': 1}
