#!/usr/bin/env python3
"""
Script to check Google Sheets "email" tab for empty email_body cells.
Generates a detailed report and exports to CSV for analysis.

Usage:
    python check_empty_email_bodies.py
"""

import csv
import logging
import os
from datetime import datetime
from typing import Dict, List, Tuple

# Import existing project components
from config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID
from sheets_sync import GoogleSheetsSync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('empty_email_bodies_check.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EmptyEmailBodyChecker:
    """Check for empty email_body cells in Google Sheets and generate report"""
    
    def __init__(self):
        """Initialize the checker with Google Sheets connection"""
        self.sheets_sync = None
        self.empty_rows = []
        self.total_rows = 0
        self.valid_rows = 0
        
        self._initialize_sheets()
    
    def _initialize_sheets(self):
        """Initialize Google Sheets connection"""
        try:
            if GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
                self.sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
                if self.sheets_sync.client:
                    logger.info("Google Sheets connection established successfully")
                else:
                    logger.error("Google Sheets client not available")
            else:
                logger.error("Google Sheets credentials not configured in config.py")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
    
    def check_empty_email_bodies(self) -> List[Dict]:
        """Check for empty email_body cells in the email sheet"""
        if not self.sheets_sync or not self.sheets_sync.client:
            logger.error("Google Sheets connection not available")
            return []
        
        try:
            logger.info("Starting check for empty email_body cells...")
            
            # Get all data from the email sheet
            worksheet = self.sheets_sync.sheet_email
            if not worksheet:
                logger.error("Email sheet not found in spreadsheet")
                return []
            
            # Get all values
            all_values = worksheet.get_all_values()
            self.total_rows = len(all_values)
            
            if self.total_rows <= 1:  # Only header row
                logger.warning("No data rows found in email sheet (only header)")
                return []
            
            # Skip header row
            data_rows = all_values[1:]
            self.valid_rows = len(data_rows)
            
            # Column indices based on the headers in sheets_sync.py
            COLUMNS = {
                'job_id': 0,
                'company_name': 1,
                'job_role': 2,
                'location': 3,
                'eligibility': 4,
                'contact_email': 5,
                'contact_phone': 6,
                'recruiter_name': 7,
                'application_link': 8,
                'application_method': 9,
                'job_description': 10,
                'email_subject': 11,
                'email_body': 12,  # This is the column we need to check
                'status': 13,
                'created_at': 14,
                'experience_required': 15,
                'job_relevance': 16
            }
            
            empty_count = 0
            self.empty_rows = []
            
            logger.info(f"Analyzing {self.valid_rows} data rows...")
            
            for row_index, row in enumerate(data_rows, start=2):  # Start from row 2 (accounting for header)
                try:
                    # Check if email_body is empty, null, or only whitespace
                    email_body = row[COLUMNS['email_body']] if len(row) > COLUMNS['email_body'] else ''
                    
                    # Strip whitespace and check if empty
                    if not email_body or email_body.strip() == '' or email_body.strip().lower() in ['null', 'none', 'n/a', 'tbd', 'tba']:
                        empty_count += 1
                        
                        # Extract relevant information for the report
                        row_data = {
                            'row_number': row_index,
                            'job_id': row[COLUMNS['job_id']] if len(row) > COLUMNS['job_id'] else '',
                            'company_name': row[COLUMNS['company_name']] if len(row) > COLUMNS['company_name'] else '',
                            'job_role': row[COLUMNS['job_role']] if len(row) > COLUMNS['job_role'] else '',
                            'location': row[COLUMNS['location']] if len(row) > COLUMNS['location'] else '',
                            'contact_email': row[COLUMNS['contact_email']] if len(row) > COLUMNS['contact_email'] else '',
                            'recruiter_name': row[COLUMNS['recruiter_name']] if len(row) > COLUMNS['recruiter_name'] else '',
                            'application_link': row[COLUMNS['application_link']] if len(row) > COLUMNS['application_link'] else '',
                            'email_subject': row[COLUMNS['email_subject']] if len(row) > COLUMNS['email_subject'] else '',
                            'status': row[COLUMNS['status']] if len(row) > COLUMNS['status'] else '',
                            'created_at': row[COLUMNS['created_at']] if len(row) > COLUMNS['created_at'] else '',
                            'experience_required': row[COLUMNS['experience_required']] if len(row) > COLUMNS['experience_required'] else '',
                            'job_relevance': row[COLUMNS['job_relevance']] if len(row) > COLUMNS['job_relevance'] else '',
                            'job_description_preview': row[COLUMNS['job_description']][:100] + '...' if len(row) > COLUMNS['job_description'] and len(row[COLUMNS['job_description']]) > 100 else (row[COLUMNS['job_description']] if len(row) > COLUMNS['job_description'] else '')
                        }
                        
                        self.empty_rows.append(row_data)
                        
                        logger.debug(f"Found empty email_body at row {row_index}: {row_data['company_name']} - {row_data['job_role']}")
                
                except IndexError as e:
                    logger.warning(f"Row {row_index} has insufficient columns: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing row {row_index}: {e}")
                    continue
            
            logger.info(f"Analysis complete: {empty_count} empty email_body cells found out of {self.valid_rows} total rows")
            return self.empty_rows
            
        except Exception as e:
            logger.error(f"Error checking empty email bodies: {e}")
            return []
    
    def generate_report(self) -> str:
        """Generate a detailed text report of the findings"""
        if not self.empty_rows:
            if self.valid_rows > 0:
                return f"""
=== EMPTY EMAIL BODY CHECK REPORT ===
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ ALL EMAIL BODIES FILLED!
Total rows analyzed: {self.total_rows}
Data rows: {self.valid_rows}
Empty email_body cells: 0

All {self.valid_rows} entries have email bodies generated.
                """.strip()
            else:
                return """
=== EMPTY EMAIL BODY CHECK REPORT ===
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ NO DATA FOUND
No data rows found in the email sheet.
                """.strip()
        
        report = f"""
=== EMPTY EMAIL BODY CHECK REPORT ===
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 SUMMARY:
• Total rows in sheet: {self.total_rows}
• Data rows analyzed: {self.valid_rows}
• Missing email bodies: {len(self.empty_rows)}
• Completion rate: {((self.valid_rows - len(self.empty_rows)) / self.valid_rows * 100):.1f}%

📋 MISSING EMAIL BODIES DETAIL:
"""
        
        for i, row_data in enumerate(self.empty_rows, 1):
            report += f"""
--- Entry {i} ---
Row: {row_data['row_number']}
Job ID: {row_data['job_id']}
Company: {row_data['company_name']}
Role: {row_data['job_role']}
Location: {row_data['location']}
Email: {row_data['contact_email']}
Recruiter: {row_data['recruiter_name']}
Status: {row_data['status']}
Created: {row_data['created_at']}
Experience: {row_data['experience_required']}
Relevance: {row_data['job_relevance']}
Job Description Preview: {row_data['job_description_preview']}
Subject Line: {row_data['email_subject']}
Application Method: {row_data.get('application_method', 'N/A')}
"""
        
        return report.strip()
    
    def export_to_csv(self, filename: str = None) -> str:
        """Export the results to a CSV file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"empty_email_bodies_report_{timestamp}.csv"
        
        try:
            if not self.empty_rows:
                logger.info("No empty email bodies found to export")
                return ""
            
            fieldnames = [
                'row_number', 'job_id', 'company_name', 'job_role', 'location',
                'contact_email', 'recruiter_name', 'status', 'created_at',
                'experience_required', 'job_relevance', 'email_subject',
                'job_description_preview', 'application_link', 'application_method'
            ]
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.empty_rows)
            
            logger.info(f"Results exported to CSV: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return ""
    
    def print_summary(self):
        """Print a quick summary to console"""
        if not self.empty_rows:
            if self.valid_rows > 0:
                print(f"✅ SUCCESS: All {self.valid_rows} entries have email bodies!")
            else:
                print("⚠️ WARNING: No data found in email sheet")
        else:
            print(f"⚠️ ACTION NEEDED: {len(self.empty_rows)} entries missing email bodies out of {self.valid_rows} total")
            print(f"   📧 Emails to generate: {len(self.empty_rows)}")
            print(f"   📄 CSV report exported: empty_email_bodies_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

def main():
    """Main entry point"""
    print("🔍 Starting Google Sheets empty email body check...")
    print("=" * 60)
    
    try:
        # Initialize checker
        checker = EmptyEmailBodyChecker()
        
        # Check for empty email bodies
        empty_rows = checker.check_empty_email_bodies()
        
        # Print summary
        checker.print_summary()
        print()
        
        # Generate and display detailed report
        report = checker.generate_report()
        print(report)
        print()
        
        # Export to CSV
        if empty_rows:
            csv_file = checker.export_to_csv()
            if csv_file:
                print(f"📄 CSV report saved: {csv_file}")
        
        print("=" * 60)
        print("✅ Empty email body check completed successfully!")
        
        return 0 if not empty_rows else 1
        
    except Exception as e:
        logger.error(f"Script failed: {e}")
        print(f"❌ ERROR: {e}")
        return 1

if __name__ == "__main__":
    exit(main())