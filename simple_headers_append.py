#!/usr/bin/env python3
"""
Simple Header Append Script
Appends headers as rows to all Google Sheets (one-time operation)
"""

from sheets_sync import GoogleSheetsSync
from config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

def append_headers_to_sheets():
    """Append headers as rows to all job tracking sheets"""
    
    print("📋 Adding Headers to Google Sheets")
    print("=" * 50)
    
    # Check if Google Sheets is configured
    if not GOOGLE_CREDENTIALS_JSON or not SPREADSHEET_ID:
        print("❌ Google Sheets credentials not configured!")
        print("Please set GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID in your .env file")
        return False
    
    try:
        # Initialize Google Sheets
        sheets = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        
        if not sheets.client:
            print("❌ Failed to connect to Google Sheets")
            return False
        
        print("✅ Connected to Google Sheets successfully!")
        
        # Define headers for job tracking
        headers = [
            'Job ID',           # 1. Unique job identifier
            'Company Name',     # 2. Company/Organization
            'Job Role',         # 3. Position/Title
            'Location',         # 4. Job location
            'Eligibility',      # 5. Year/requirements
            'Contact Email',    # 6. Email address
            'Contact Phone',    # 7. Phone number
            'Recruiter Name',   # 8. HR/Recruiter name
            'Application Link', # 9. External application URL
            'Application Method', # 10. How to apply (email/link/phone)
            'Job Description',  # 11. Full job posting text
            'Email Subject',    # 12. Generated email subject
            'Email Body',       # 13. Generated personalized email
            'Status',           # 14. pending/applied/rejected
            'Created At',       # 15. When job was added
            'Experience Required', # 16. NEW: Experience requirements
            'Job Relevance'     # 17. NEW: relevant/irrelevant for freshers
        ]
        
        # List of sheet names to update
        sheet_names = [
            'email',           # Relevant jobs with email
            'non-email',       # Relevant jobs with link/phone
            'email-exp',       # Irrelevant jobs with email
            'non-email-exp'    # Irrelevant jobs with link/phone
        ]
        
        success_count = 0
        
        for sheet_name in sheet_names:
            try:
                print(f"\n📝 Processing sheet: {sheet_name}")
                
                # Get the spreadsheet
                spreadsheet = sheets.client.open_by_key(SPREADSHEET_ID)
                
                # Get or create the worksheet
                try:
                    worksheet = spreadsheet.worksheet(sheet_name)
                    print(f"  ✅ Found existing sheet: {sheet_name}")
                except Exception:
                    # Sheet doesn't exist, create it
                    worksheet = spreadsheet.add_worksheet(
                        title=sheet_name, 
                        rows=1000, 
                        cols=17
                    )
                    print(f"  ✅ Created new sheet: {sheet_name}")
                
                # Check if sheet is empty or has data
                try:
                    existing_data = worksheet.get_all_values()
                    
                    if len(existing_data) == 0:
                        # Completely empty sheet, append headers
                        worksheet.append_row(headers)
                        print(f"  ✅ Headers added to empty sheet")
                        success_count += 1
                        
                    elif len(existing_data) == 1 and (len(existing_data[0]) == 0 or not existing_data[0][0].strip()):
                        # Sheet has only empty row(s), append headers
                        worksheet.append_row(headers)
                        print(f"  ✅ Headers added to sheet")
                        success_count += 1
                        
                    else:
                        # Sheet already has data
                        first_row = existing_data[0]
                        if len(first_row) >= 15 and first_row[0].strip().lower() in ['job id', 'id', 'company', 'job role']:
                            print(f"  ℹ️  Sheet already has headers, skipping")
                        else:
                            # Sheet has data but no headers, append headers at the beginning
                            worksheet.update('A1', [headers])
                            print(f"  ✅ Headers added to sheet with existing data")
                            success_count += 1
                            
                except Exception as e:
                    # If we can't check existing data, just try to append headers
                    worksheet.append_row(headers)
                    print(f"  ✅ Headers added to sheet")
                    success_count += 1
                
            except Exception as e:
                print(f"  ❌ Error processing sheet '{sheet_name}': {e}")
        
        # Final summary
        print("\n" + "=" * 50)
        print("📊 SUMMARY")
        print("=" * 50)
        print(f"✅ Sheets updated: {success_count}")
        print(f"📋 Total sheets processed: {len(sheet_names)}")
        
        if success_count > 0:
            print(f"\n🎉 Successfully added headers to {success_count} sheet(s)!")
            print(f"\n🌐 View your spreadsheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
            print(f"\n📋 Your sheets now have these 17 columns:")
            for i, header in enumerate(headers, 1):
                print(f"  {i:2d}. {header}")
        
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Failed to update sheets: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Simple Google Sheets Headers Setup")
    print("Appending headers as rows to all job tracking sheets")
    print("=" * 60)
    
    success = append_headers_to_sheets()
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 HEADER SETUP COMPLETE!")
        print("=" * 60)
        print("Your Google Sheets now have proper headers!")
        print("Future job data will align correctly with the columns.")
        print("The enhanced job relevance filtering is ready to work!")
    else:
        print("\n❌ Header setup failed. Please check your Google Sheets configuration.")