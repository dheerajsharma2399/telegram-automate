#!/usr/bin/env python3
"""
CSV Export Script for Job Relevance Filtering System
Exports jobs to separate CSV files based on relevance and contact method
"""

import csv
import os
from datetime import datetime
from database import Database

def create_export_directories():
    """Create export directories if they don't exist"""
    base_dir = "exports"
    os.makedirs(f"{base_dir}/relevant", exist_ok=True)
    os.makedirs(f"{base_dir}/irrelevant", exist_ok=True)
    return base_dir

def get_csv_headers():
    """Define consistent CSV headers for all exports"""
    return [
        'Job ID',
        'Company Name', 
        'Job Role',
        'Location',
        'Eligibility',
        'Contact Email',
        'Contact Phone',
        'Recruiter Name',
        'Application Link', 
        'Application Method',
        'Job Description',
        'Email Subject',
        'Email Body',
        'Status',
        'Created At',
        'Experience Required',
        'Job Relevance'
    ]

def format_job_for_csv(job):
    """Format job data for CSV export"""
    return {
        'Job ID': job.get('job_id', ''),
        'Company Name': job.get('company_name', ''),
        'Job Role': job.get('job_role', ''),
        'Location': job.get('location', ''),
        'Eligibility': job.get('eligibility', ''),
        'Contact Email': job.get('email', ''),
        'Contact Phone': job.get('phone', ''),
        'Recruiter Name': job.get('recruiter_name', ''),
        'Application Link': job.get('application_link', ''),
        'Application Method': job.get('application_method', ''),
        'Job Description': job.get('jd_text', ''),
        'Email Subject': job.get('email_subject', ''),
        'Email Body': job.get('email_body', ''),
        'Status': job.get('status', 'pending'),
        'Created At': job.get('created_at', ''),
        'Experience Required': job.get('experience_required', ''),
        'Job Relevance': job.get('job_relevance', 'relevant')
    }

def export_relevant_jobs(db, base_dir):
    """Export relevant jobs (fresher-friendly)"""
    print("📤 Exporting Relevant Jobs...")
    
    # Get relevant jobs with and without email
    relevant_with_email = db.get_relevant_jobs(has_email=True)
    relevant_without_email = db.get_relevant_jobs(has_email=False)
    
    headers = get_csv_headers()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export relevant jobs with email
    email_file = f"{base_dir}/relevant/relevant_jobs_with_email_{timestamp}.csv"
    with open(email_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in relevant_with_email:
            writer.writerow(format_job_for_csv(job))
    
    # Export relevant jobs without email
    no_email_file = f"{base_dir}/relevant/relevant_jobs_without_email_{timestamp}.csv"
    with open(no_email_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in relevant_without_email:
            writer.writerow(format_job_for_csv(job))
    
    # Export combined relevant jobs
    combined_file = f"{base_dir}/relevant/relevant_jobs_all_{timestamp}.csv"
    with open(combined_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in relevant_with_email + relevant_without_email:
            writer.writerow(format_job_for_csv(job))
    
    total_relevant = len(relevant_with_email) + len(relevant_without_email)
    print(f"  ✅ Relevant jobs exported: {total_relevant}")
    print(f"     - With email: {len(relevant_with_email)}")
    print(f"     - Without email: {len(relevant_without_email)}")
    print(f"  📁 Files created:")
    print(f"     - {email_file}")
    print(f"     - {no_email_file}")
    print(f"     - {combined_file}")
    
    return {
        'total': total_relevant,
        'with_email': len(relevant_with_email),
        'without_email': len(relevant_without_email),
        'files': [email_file, no_email_file, combined_file]
    }

def export_irrelevant_jobs(db, base_dir):
    """Export irrelevant jobs (experienced required)"""
    print("📤 Exporting Irrelevant Jobs...")
    
    # Get irrelevant jobs with and without email
    irrelevant_with_email = db.get_irrelevant_jobs(has_email=True)
    irrelevant_without_email = db.get_irrelevant_jobs(has_email=False)
    
    headers = get_csv_headers()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export irrelevant jobs with email
    email_file = f"{base_dir}/irrelevant/irrelevant_jobs_with_email_{timestamp}.csv"
    with open(email_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in irrelevant_with_email:
            writer.writerow(format_job_for_csv(job))
    
    # Export irrelevant jobs without email
    no_email_file = f"{base_dir}/irrelevant/irrelevant_jobs_without_email_{timestamp}.csv"
    with open(no_email_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in irrelevant_without_email:
            writer.writerow(format_job_for_csv(job))
    
    # Export combined irrelevant jobs
    combined_file = f"{base_dir}/irrelevant/irrelevant_jobs_all_{timestamp}.csv"
    with open(combined_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in irrelevant_with_email + irrelevant_without_email:
            writer.writerow(format_job_for_csv(job))
    
    total_irrelevant = len(irrelevant_with_email) + len(irrelevant_without_email)
    print(f"  ✅ Irrelevant jobs exported: {total_irrelevant}")
    print(f"     - With email: {len(irrelevant_with_email)}")
    print(f"     - Without email: {len(irrelevant_without_email)}")
    print(f"  📁 Files created:")
    print(f"     - {email_file}")
    print(f"     - {no_email_file}")
    print(f"     - {combined_file}")
    
    return {
        'total': total_irrelevant,
        'with_email': len(irrelevant_with_email),
        'without_email': len(irrelevant_without_email),
        'files': [email_file, no_email_file, combined_file]
    }

def export_master_summary(db, base_dir):
    """Export master summary file with all jobs"""
    print("📤 Exporting Master Summary...")
    
    all_relevant = db.get_relevant_jobs()
    all_irrelevant = db.get_irrelevant_jobs()
    all_jobs = all_relevant + all_irrelevant
    
    headers = get_csv_headers()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export master file
    master_file = f"{base_dir}/ALL_JOBS_SUMMARY_{timestamp}.csv"
    with open(master_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for job in all_jobs:
            writer.writerow(format_job_for_csv(job))
    
    # Export statistics summary
    stats_file = f"{base_dir}/EXPORT_STATISTICS_{timestamp}.txt"
    with open(stats_file, 'w') as f:
        f.write("Job Relevance Filtering - Export Statistics\n")
        f.write("=" * 50 + "\n")
        f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Jobs: {len(all_jobs)}\n")
        f.write(f"Relevant Jobs: {len(all_relevant)}\n")
        f.write(f"  - With Email: {len([j for j in all_relevant if j.get('email')])}\n")
        f.write(f"  - Without Email: {len([j for j in all_relevant if not j.get('email')])}\n")
        f.write(f"Irrelevant Jobs: {len(all_irrelevant)}\n")
        f.write(f"  - With Email: {len([j for j in all_irrelevant if j.get('email')])}\n")
        f.write(f"  - Without Email: {len([j for j in all_irrelevant if not j.get('email')])}\n")
        f.write("\nFiles Generated:\n")
        f.write("- relevant_jobs_with_email_*.csv\n")
        f.write("- relevant_jobs_without_email_*.csv\n") 
        f.write("- relevant_jobs_all_*.csv\n")
        f.write("- irrelevant_jobs_with_email_*.csv\n")
        f.write("- irrelevant_jobs_without_email_*.csv\n")
        f.write("- irrelevant_jobs_all_*.csv\n")
        f.write("- ALL_JOBS_SUMMARY_*.csv\n")
        f.write("- EXPORT_STATISTICS_*.txt\n")
    
    print(f"  ✅ Master summary exported: {master_file}")
    print(f"  📊 Statistics file: {stats_file}")
    
    return {
        'total_jobs': len(all_jobs),
        'master_file': master_file,
        'stats_file': stats_file
    }

def create_import_instructions(base_dir):
    """Create instructions for importing CSV files"""
    instructions_file = f"{base_dir}/IMPORT_INSTRUCTIONS.md"
    
    with open(instructions_file, 'w') as f:
        f.write("# CSV Import Instructions\n\n")
        f.write("## File Structure\n\n")
        f.write("The export creates the following directory structure:\n")
        f.write("```\n")
        f.write("exports/\n")
        f.write("├── relevant/\n")
        f.write("│   ├── relevant_jobs_with_email_YYYYMMDD_HHMMSS.csv\n")
        f.write("│   ├── relevant_jobs_without_email_YYYYMMDD_HHMMSS.csv\n")
        f.write("│   └── relevant_jobs_all_YYYYMMDD_HHMMSS.csv\n")
        f.write("├── irrelevant/\n")
        f.write("│   ├── irrelevant_jobs_with_email_YYYYMMDD_HHMMSS.csv\n")
        f.write("│   ├── irrelevant_jobs_without_email_YYYYMMDD_HHMMSS.csv\n")
        f.write("│   └── irrelevant_jobs_all_YYYYMMDD_HHMMSS.csv\n")
        f.write("├── ALL_JOBS_SUMMARY_YYYYMMDD_HHMMSS.csv\n")
        f.write("└── EXPORT_STATISTICS_YYYYMMDD_HHMMSS.txt\n")
        f.write("```\n\n")
        
        f.write("## Column Headers\n\n")
        f.write("All CSV files contain these 17 columns:\n")
        headers = get_csv_headers()
        for i, header in enumerate(headers, 1):
            f.write(f"{i:2d}. {header}\n")
        
        f.write("\n## Google Sheets Import\n\n")
        f.write("1. **Open Google Sheets**\n")
        f.write("2. **Create new spreadsheet**\n")
        f.write("3. **Import CSV files**:\n")
        f.write("   - Import `relevant_jobs_with_email_*.csv` → Sheet name: 'Relevant+Email'\n")
        f.write("   - Import `relevant_jobs_without_email_*.csv` → Sheet name: 'Relevant+NoEmail'\n")
        f.write("   - Import `irrelevant_jobs_with_email_*.csv` → Sheet name: 'Irrelevant+Email'\n")
        f.write("   - Import `irrelevant_jobs_without_email_*.csv` → Sheet name: 'Irrelevant+NoEmail'\n")
        f.write("   - Import `ALL_JOBS_SUMMARY_*.csv` → Sheet name: 'All Jobs'\n\n")
        
        f.write("## Excel Import\n\n")
        f.write("1. **Open Excel**\n")
        f.write("2. **Data** → **From Text/CSV**\n")
        f.write("3. **Select CSV file** and import\n")
        f.write("4. **Choose appropriate sheet names**\n\n")
        
        f.write("## Custom Sheet Names\n\n")
        f.write("You can rename the imported sheets to match your preference:\n")
        f.write("- 'Relevant+Email' → 'Freshers Email'\n")
        f.write("- 'Relevant+NoEmail' → 'Freshers NoEmail'\n")
        f.write("- 'Irrelevant+Email' → 'Experienced Email'\n")
        f.write("- 'Irrelevant+NoEmail' → 'Experienced NoEmail'\n")
        f.write("- 'All Jobs' → 'Complete Database'\n\n")
        
        f.write("## Job Relevance Meaning\n\n")
        f.write("**Relevant**: Suitable for freshers (2024/2025/2026 batch, entry level, 0-1 years experience)\n")
        f.write("**Irrelevant**: Requires experience (2023/2022 batch, 2+ years, senior positions)\n\n")
        
        f.write("## Contact Method Categories\n\n")
        f.write("**Email**: Jobs with direct email contact\n")
        f.write("**NoEmail**: Jobs with application links, phone numbers, or other contact methods\n")
    
    print(f"  📖 Instructions created: {instructions_file}")
    return instructions_file

def main():
    """Main export function"""
    print("🚀 CSV Export for Job Relevance Filtering System")
    print("=" * 60)
    
    # Initialize database
    db = Database("jobs.db")
    
    # Create export directories
    base_dir = create_export_directories()
    print(f"📁 Export directory created: {base_dir}")
    
    # Export jobs by relevance
    relevant_stats = export_relevant_jobs(db, base_dir)
    irrelevant_stats = export_irrelevant_jobs(db, base_dir)
    
    # Export master summary
    master_stats = export_master_summary(db, base_dir)
    
    # Create import instructions
    instructions_file = create_import_instructions(base_dir)
    
    # Final summary
    print("\n" + "=" * 60)
    print("📊 EXPORT SUMMARY")
    print("=" * 60)
    print(f"Total Jobs Exported: {master_stats['total_jobs']}")
    print(f"Relevant Jobs: {relevant_stats['total']}")
    print(f"  - With Email: {relevant_stats['with_email']}")
    print(f"  - Without Email: {relevant_stats['without_email']}")
    print(f"Irrelevant Jobs: {irrelevant_stats['total']}")
    print(f"  - With Email: {irrelevant_stats['with_email']}")
    print(f"  - Without Email: {irrelevant_stats['without_email']}")
    
    print(f"\n📁 Files Location: {base_dir}/")
    print(f"📖 Import Guide: {instructions_file}")
    print(f"📊 Master File: {master_stats['master_file']}")
    
    print("\n✅ CSV Export Complete!")
    print("🎯 You can now import these files into Google Sheets, Excel, or any other tool.")
    print("📋 Check the IMPORT_INSTRUCTIONS.md for detailed import steps.")
    
    return {
        'total_jobs': master_stats['total_jobs'],
        'relevant_jobs': relevant_stats['total'],
        'irrelevant_jobs': irrelevant_stats['total'],
        'export_directory': base_dir,
        'instructions_file': instructions_file
    }

if __name__ == "__main__":
    try:
        results = main()
    except Exception as e:
        print(f"\n❌ Export failed: {e}")
        import traceback
        traceback.print_exc()