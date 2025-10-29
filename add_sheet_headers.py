#!/usr/bin/env python3
"""
Add Headers to Existing Google Sheets
Run this script to add proper headers to all job tracking sheets
"""

from sheets_sync import GoogleSheetsSync
from config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

def add_headers_to_all_sheets():
    """Add headers to all existing job tracking sheets"""
    
    if not GOOGLE_CREDENTIALS_JSON or not SPREADSHEET_ID:
        print("❌ Google Sheets credentials not configured!")
        print("Please ensure GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID are set in .env")
        return False
    
    print("🔧 Adding Headers to Google Sheets")
    print("=" * 50)
    
    try:
        # Initialize Google Sheets sync
        sheets = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        
        if not sheets.client:
            print("❌ Failed to connect to Google Sheets")
            return False
        
        # Define headers for job tracking
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
        
        # List of sheets to add headers to
        sheets_to_update = [
            'email',           # Relevant jobs with email
            'non-email',       # Relevant jobs with link/phone
            'email-exp',       # Irrelevant jobs with email
            'non-email-exp'    # Irrelevant jobs with link/phone
        ]
        
        success_count = 0
        error_count = 0
        
        for sheet_name in sheets_to_update:
            try:
                print(f"\n📋 Updating sheet: {sheet_name}")
                
                # Get existing worksheet
                spreadsheet = sheets.client.open_by_key(sheets.spreadsheet_id)
                worksheet = spreadsheet.worksheet(sheet_name)
                
                # Check if sheet has any data
                all_values = worksheet.get_all_values()
                
                if len(all_values) == 0:
                    # Empty sheet, add headers
                    worksheet.append_row(headers)
                    print(f"  ✅ Headers added to empty sheet: {sheet_name}")
                    success_count += 1
                elif len(all_values) == 1:
                    # Only one row, check if it's headers or data
                    first_row = all_values[0]
                    if len(first_row) == 1 and not first_row[0].strip():
                        # Empty header row, add headers
                        worksheet.update('A1', [headers])
                        print(f"  ✅ Headers added to sheet: {sheet_name}")
                        success_count += 1
                    elif first_row[0].lower() in ['job id', 'id', '']:
                        # Already has headers, skip
                        print(f"  ℹ️  Sheet already has headers: {sheet_name}")
                        success_count += 1
                    else:
                        # Data without headers, add headers at top
                        worksheet.update('A1', [headers])
                        print(f"  ✅ Headers added to sheet with data: {sheet_name}")
                        success_count += 1
                else:
                    # Multiple rows, check if first row has headers
                    first_row = all_values[0]
                    if first_row[0].lower() not in ['job id', 'id', '']:
                        # No headers found, add them
                        worksheet.update('A1', [headers])
                        print(f"  ✅ Headers added to sheet with data: {sheet_name}")
                        success_count += 1
                    else:
                        # Headers already present
                        print(f"  ℹ️  Headers already exist: {sheet_name}")
                        success_count += 1
                        
            except Exception as e:
                print(f"  ❌ Error updating sheet {sheet_name}: {e}")
                error_count += 1
        
        print("\n" + "=" * 50)
        print("📊 SUMMARY")
        print("=" * 50)
        print(f"✅ Sheets updated successfully: {success_count}")
        print(f"❌ Sheets with errors: {error_count}")
        print(f"📋 Total sheets processed: {success_count + error_count}")
        
        if success_count > 0:
            print(f"\n🎉 Successfully added headers to {success_count} sheet(s)!")
            print("\n📋 Sheet Names:")
            for sheet_name in sheets_to_update:
                print(f"  - {sheet_name}")
            print(f"\n🌐 View your spreadsheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
        
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Failed to update sheets: {e}")
        return False

def verify_headers():
    """Verify that headers are properly added to all sheets"""
    print("\n🔍 Verifying Headers...")
    
    try:
        sheets = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        
        if not sheets.client:
            print("❌ Cannot connect to Google Sheets")
            return False
        
        spreadsheet = sheets.client.open_by_key(sheets.spreadsheet_id)
        sheets_to_check = ['email', 'non-email', 'email-exp', 'non-email-exp']
        
        for sheet_name in sheets_to_check:
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                first_row = worksheet.row_values(1)
                
                if len(first_row) >= 15:  # Should have at least 15 columns
                    print(f"  ✅ {sheet_name}: {len(first_row)} columns")
                else:
                    print(f"  ⚠️  {sheet_name}: Only {len(first_row)} columns")
                    
            except Exception as e:
                print(f"  ❌ {sheet_name}: Error - {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Google Sheets Header Setup")
    print("Adding proper headers to all job tracking sheets")
    print("=" * 60)
    
    # Add headers to all sheets
    success = add_headers_to_all_sheets()
    
    if success:
        # Verify the headers were added correctly
        verify_headers()
        
        print("\n" + "=" * 60)
        print("🎉 HEADER SETUP COMPLETE!")
        print("=" * 60)
        print("Your Google Sheets now have proper headers:")
        print("1. Job ID")
        print("2. Company Name")
        print("3. Job Role")
        print("4. Location")
        print("5. Eligibility")
        print("6. Contact Email")
        print("7. Contact Phone")
        print("8. Recruiter Name")
        print("9. Application Link")
        print("10. Application Method")
        print("11. Job Description")
        print("12. Email Subject")
        print("13. Email Body")
        print("14. Status")
        print("15. Created At")
        print("16. Experience Required (NEW)")
        print("17. Job Relevance (NEW)")
        print("\n🌐 View your spreadsheet: https://docs.google.com/spreadsheets/d/" + SPREADSHEET_ID)
        print("\n💡 The sheets will now accept data with proper column alignment!")
    else:
        print("\n❌ Header setup failed. Please check your Google Sheets credentials.")