#!/usr/bin/env python3
"""
Enhanced Google Sheets Automation Script for Job Applications
Integrates with existing Telegram Job Scraper Bot project

Features:
- Reads job data from existing database
- Intelligent resume selection based on job requirements
- Gmail API integration for sending applications
- Robust error handling and retry mechanisms
- Status tracking in Google Sheets
- Multiple resume format support
"""

import os
import json
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Import existing project components
from database import Database
from sheets_sync import GoogleSheetsSync
from config import (
    DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL
)

# Gmail API imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.application import MIMEApplication
    import base64
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    print("Warning: Gmail API dependencies not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sheets_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ResumeConfig:
    """Configuration for resume files"""
    name: str
    file_path: str
    skills_match: List[str]
    experience_level: str  # 'fresher', 'junior', 'mid', 'senior'
    description: str

@dataclass
class EmailConfig:
    """Configuration for email sending"""
    sender_email: str
    sender_name: str
    gmail_credentials_file: str  # Path to credentials.json
    gmail_token_file: str = 'token.json'
    
@dataclass
class JobApplication:
    """Job application data"""
    job_data: Dict
    selected_resume: ResumeConfig
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None
    status: str = 'pending'  # 'pending', 'sent', 'failed', 'retry'
    error_message: Optional[str] = None

class SheetsAutomationManager:
    """Main automation manager for Google Sheets job applications"""
    
    def __init__(self, config_file: str = 'automation_config.json'):
        """Initialize the automation manager"""
        self.config_file = config_file
        self.config = self._load_config()
        self.db = None
        self.sheets_sync = None
        self.gmail_service = None
        self.applications = []
        
        # Initialize components
        self._initialize_database()
        self._initialize_sheets()
        self._initialize_gmail()
        
    def _load_config(self) -> Dict:
        """Load configuration from file"""
        default_config = {
            'resumes': [],
            'email': {
                'sender_email': '',
                'sender_name': '',
                'gmail_credentials_file': 'credentials.json',
                'gmail_token_file': 'token.json'
            },
            'settings': {
                'max_emails_per_hour': 50,
                'retry_attempts': 3,
                'retry_delay_minutes': 30,
                'auto_resume_selection': True,
                'exclude_companies': [],
                'required_skills_weight': 0.7,
                'experience_weight': 0.3
            },
            'status_mapping': {
                'pending': 'Pending Review',
                'sent': 'Application Sent',
                'failed': 'Failed - Need Manual Review',
                'retry': 'Retry Scheduled'
            }
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                # Create default config file
                with open(self.config_file, 'w') as f:
                    json.dump(default_config, f, indent=2)
                logger.info(f"Created default configuration file: {self.config_file}")
                return default_config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return default_config
    
    def _initialize_database(self):
        """Initialize database connection"""
        try:
            self.db = Database(DATABASE_URL)
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _initialize_sheets(self):
        """Initialize Google Sheets connection"""
        try:
            if GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
                self.sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
                if self.sheets_sync.client:
                    logger.info("Google Sheets connection established")
                else:
                    logger.warning("Google Sheets client not available")
            else:
                logger.warning("Google Sheets credentials not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
    
    def _initialize_gmail(self):
        """Initialize Gmail API service"""
        if not GMAIL_AVAILABLE:
            logger.warning("Gmail API dependencies not available")
            return
            
        try:
            email_config = self.config['email']
            credentials_file = email_config['gmail_credentials_file']
            token_file = email_config['gmail_token_file']
            
            if not os.path.exists(credentials_file):
                logger.warning(f"Gmail credentials file not found: {credentials_file}")
                return
            
            # Gmail API scopes
            SCOPES = ['https://www.googleapis.com/auth/gmail.send']
            
            # Load credentials
            creds = None
            if os.path.exists(token_file):
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            
            # If no valid credentials, run OAuth flow
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        credentials_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save credentials for next run
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            
            # Build Gmail service
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API service initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gmail service: {e}")
    
    def add_resume(self, name: str, file_path: str, skills_match: List[str], 
                   experience_level: str, description: str = "") -> bool:
        """Add a new resume configuration"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"Resume file not found: {file_path}")
                return False
            
            resume_config = ResumeConfig(
                name=name,
                file_path=file_path,
                skills_match=skills_match,
                experience_level=experience_level,
                description=description
            )
            
            # Add to configuration
            self.config['resumes'].append({
                'name': name,
                'file_path': file_path,
                'skills_match': skills_match,
                'experience_level': experience_level,
                'description': description
            })
            
            # Save configuration
            self._save_config()
            
            logger.info(f"Added resume: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding resume: {e}")
            return False
    
    def _save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def get_unsent_jobs(self, limit: int = 50) -> List[Dict]:
        """Get jobs from database that need email applications"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get jobs with email contacts that haven't been processed
                query = """
                    SELECT * FROM processed_jobs 
                    WHERE email IS NOT NULL 
                    AND email != ''
                    AND (status IS NULL OR status = 'pending')
                    AND created_at >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                
                cursor.execute(query, (limit,))
                jobs = [dict(row) for row in cursor.fetchall()]
                
                logger.info(f"Found {len(jobs)} jobs ready for processing")
                return jobs
                
        except Exception as e:
            logger.error(f"Error fetching jobs: {e}")
            return []
    
    def analyze_job_requirements(self, job_data: Dict) -> Dict:
        """Analyze job requirements to match with resumes"""
        try:
            jd_text = job_data.get('jd_text', '')
            job_role = job_data.get('job_role', '')
            eligibility = job_data.get('eligibility', '')
            experience_required = job_data.get('experience_required', '')
            
            # Extract skills from job description
            job_skills = self._extract_skills(jd_text)
            
            # Determine experience level
            experience_level = self._determine_experience_level(
                eligibility, experience_required, jd_text
            )
            
            return {
                'extracted_skills': job_skills,
                'experience_level': experience_level,
                'job_role': job_role,
                'company': job_data.get('company_name', ''),
                'location': job_data.get('location', ''),
                'relevance_score': self._calculate_relevance_score(job_data)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing job requirements: {e}")
            return {'extracted_skills': [], 'experience_level': 'unknown'}
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from job description text"""
        # Common technology skills
        skills = [
            'python', 'javascript', 'java', 'c++', 'c#', 'ruby', 'php', 'go', 'rust',
            'react', 'angular', 'vue', 'node.js', 'django', 'flask', 'spring', 'laravel',
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab',
            'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch',
            'html', 'css', 'sass', 'less', 'bootstrap', 'tailwind',
            'git', 'github', 'gitlab', 'jira', 'confluence',
            'machine learning', 'ai', 'data science', 'analytics',
            'agile', 'scrum', 'devops', 'microservices', 'api', 'rest'
        ]
        
        found_skills = []
        text_lower = text.lower()
        
        for skill in skills:
            if skill.lower() in text_lower:
                found_skills.append(skill)
        
        return found_skills
    
    def _determine_experience_level(self, eligibility: str, experience_req: str, jd_text: str) -> str:
        """Determine the experience level required for the job"""
        text = f"{eligibility} {experience_req} {jd_text}".lower()
        
        # Freshers/Entry level indicators
        if any(word in text for word in ['fresher', '0 years', 'entry level', 'new graduate', 
                                        '2025 batch', '2026 batch', 'recent graduate']):
            return 'fresher'
        
        # Junior level indicators
        elif any(word in text for word in ['1-2 years', 'junior', '0-1 years', '1+ years']):
            return 'junior'
        
        # Senior level indicators
        elif any(word in text for word in ['5+ years', 'senior', 'lead', 'principal', 'architect']):
            return 'senior'
        
        # Default to mid-level
        else:
            return 'mid'
    
    def _calculate_relevance_score(self, job_data: Dict) -> float:
        """Calculate relevance score for the job"""
        score = 0.0
        
        # Base score from job relevance field if present
        job_relevance = job_data.get('job_relevance', '').lower()
        if job_relevance == 'relevant':
            score += 0.4
        elif job_relevance == 'irrelevant':
            return 0.0  # Skip irrelevant jobs
        
        # Experience level compatibility
        experience_required = job_data.get('experience_required', '').lower()
        if any(word in experience_required for word in ['fresher', '0-1', 'entry']):
            score += 0.3
        elif any(word in experience_required for word in ['2-5', 'mid']):
            score += 0.2
        elif any(word in experience_required for word in ['5+', 'senior']):
            score += 0.1
        
        # Email availability bonus
        if job_data.get('email'):
            score += 0.3
        
        return min(score, 1.0)
    
    def select_best_resume(self, job_analysis: Dict) -> Optional[ResumeConfig]:
        """Select the best resume for a job based on analysis"""
        if not self.config['resumes']:
            logger.warning("No resumes configured")
            return None
        
        if not self.config['settings']['auto_resume_selection']:
            # Return first resume as default
            resume_data = self.config['resumes'][0]
            return ResumeConfig(**resume_data)
        
        best_resume = None
        best_score = 0
        
        for resume_data in self.config['resumes']:
            resume = ResumeConfig(**resume_data)
            score = self._calculate_resume_match_score(resume, job_analysis)
            
            if score > best_score:
                best_score = score
                best_resume = resume
        
        logger.info(f"Selected resume '{best_resume.name}' with score {best_score:.2f}")
        return best_resume
    
    def _calculate_resume_match_score(self, resume: ResumeConfig, job_analysis: Dict) -> float:
        """Calculate how well a resume matches a job"""
        score = 0.0
        settings = self.config['settings']
        
        # Skills matching (70% weight)
        job_skills = set(job_analysis.get('extracted_skills', []))
        resume_skills = set(resume.skills_match)
        
        if job_skills and resume_skills:
            common_skills = job_skills.intersection(resume_skills)
            skills_score = len(common_skills) / len(job_skills) if job_skills else 0
            score += skills_score * settings['required_skills_weight']
        
        # Experience level matching (30% weight)
        job_experience = job_analysis.get('experience_level', 'unknown')
        if job_experience == resume.experience_level:
            score += settings['experience_weight']
        elif self._is_experience_compatible(job_experience, resume.experience_level):
            score += settings['experience_weight'] * 0.5
        
        return score
    
    def _is_experience_compatible(self, job_exp: str, resume_exp: str) -> bool:
        """Check if experience levels are compatible"""
        levels = {'fresher': 0, 'junior': 1, 'mid': 2, 'senior': 3}
        
        job_level = levels.get(job_exp, 1)
        resume_level = levels.get(resume_exp, 1)
        
        # Allow ±1 level difference
        return abs(job_level - resume_level) <= 1
    
    def send_job_application(self, job_application: JobApplication) -> bool:
        """Send job application email with resume attachment"""
        if not self.gmail_service:
            logger.error("Gmail service not available")
            return False
        
        try:
            job_data = job_application.job_data
            resume = job_application.selected_resume
            
            # Prepare email content
            email_config = self.config['email']
            recipient_email = job_data.get('email')
            subject = f"Application for {job_data.get('job_role', 'Position')} - {email_config['sender_name']}"
            
            # Generate personalized email body
            email_body = self._generate_personalized_email(job_data, resume)
            
            # Create email message
            message = MIMEMultipart()
            message['to'] = recipient_email
            message['from'] = email_config['sender_email']
            message['subject'] = subject
            
            # Add email body
            message.attach(MIMEText(email_body, 'plain'))
            
            # Add resume attachment
            if os.path.exists(resume.file_path):
                with open(resume.file_path, 'rb') as f:
                    attachment = MIMEApplication(f.read(), _subtype='pdf')
                    attachment.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {os.path.basename(resume.file_path)}'
                    )
                    message.attach(attachment)
            else:
                logger.warning(f"Resume file not found: {resume.file_path}")
            
            # Encode and send email
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            result = self.gmail_service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info(f"Email sent successfully to {recipient_email}")
            return True
            
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return False
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def _generate_personalized_email(self, job_data: Dict, resume: ResumeConfig) -> str:
        """Generate personalized email body for the job"""
        company = job_data.get('company_name', 'your company')
        role = job_data.get('job_role', 'the position')
        location = job_data.get('location', '')
        recruiter = job_data.get('recruiter_name', 'Hiring Team')
        
        sender_name = self.config['email']['sender_name']
        
        # Personalized email template
        email_body = f"""Dear {recruiter},

I hope this email finds you well. I am writing to express my strong interest in the {role} position at {company}{' in ' + location if location else ''}.

I am {sender_name}, and I have carefully reviewed the job requirements. I believe my skills and experience make me an excellent fit for this role, particularly given my background in {', '.join(resume.skills_match[:3])}.

I have attached my resume for your review. I would welcome the opportunity to discuss how my experience can contribute to {company}'s continued success.

Thank you for considering my application. I look forward to hearing from you.

Best regards,
{sender_name}
{self.config['email']['sender_email']}"""
        
        return email_body
    
    def update_job_status(self, job_data: Dict, status: str, error_message: str = None):
        """Update job status in database and Google Sheets"""
        try:
            job_id = job_data.get('job_id')
            
            # Update database
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE processed_jobs 
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                """, (status, job_id))
            
            # Update Google Sheets if available
            if self.sheets_sync and self.sheets_sync.client:
                try:
                    job_data['status'] = status
                    self.sheets_sync.sync_job(job_data)
                except Exception as e:
                    logger.warning(f"Failed to sync status to Google Sheets: {e}")
            
            logger.info(f"Updated job {job_id} status to {status}")
            
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
    
    def run_automation_cycle(self, limit: int = 20):
        """Run one cycle of the automation process"""
        logger.info("Starting automation cycle")
        
        try:
            # Get unsent jobs
            jobs = self.get_unsent_jobs(limit)
            if not jobs:
                logger.info("No jobs found for processing")
                return
            
            # Rate limiting check
            emails_sent_this_hour = self._get_emails_sent_recently(60)
            max_emails = self.config['settings']['max_emails_per_hour']
            
            if emails_sent_this_hour >= max_emails:
                logger.warning(f"Email limit reached: {emails_sent_this_hour}/{max_emails}")
                return
            
            # Process each job
            for job_data in jobs:
                try:
                    # Skip excluded companies
                    company = job_data.get('company_name', '').lower()
                    excluded = [c.lower() for c in self.config['settings']['exclude_companies']]
                    if any(exc in company for exc in excluded):
                        logger.info(f"Skipping excluded company: {company}")
                        continue
                    
                    # Analyze job requirements
                    job_analysis = self.analyze_job_requirements(job_data)
                    
                    # Check relevance score
                    relevance_score = job_analysis.get('relevance_score', 0)
                    if relevance_score < 0.3:  # Minimum relevance threshold
                        logger.info(f"Skipping low relevance job (score: {relevance_score:.2f})")
                        continue
                    
                    # Select best resume
                    selected_resume = self.select_best_resume(job_analysis)
                    if not selected_resume:
                        logger.warning("No suitable resume found")
                        continue
                    
                    # Create job application
                    application = JobApplication(
                        job_data=job_data,
                        selected_resume=selected_resume
                    )
                    
                    # Send application email
                    if self.send_job_application(application):
                        application.email_sent = True
                        application.email_sent_at = datetime.now()
                        application.status = 'sent'
                        
                        # Update status in database and sheets
                        self.update_job_status(job_data, 'sent')
                        
                        logger.info(f"Successfully sent application for {job_data.get('job_role')} at {company}")
                    else:
                        application.status = 'failed'
                        application.error_message = "Failed to send email"
                        self.update_job_status(job_data, 'failed')
                    
                    # Rate limiting delay
                    time.sleep(2)  # 2 seconds between emails
                    
                except Exception as e:
                    logger.error(f"Error processing job {job_data.get('job_id', 'unknown')}: {e}")
                    self.update_job_status(job_data, 'failed', str(e))
            
            logger.info("Automation cycle completed")
            
        except Exception as e:
            logger.error(f"Error in automation cycle: {e}")
    
    def _get_emails_sent_recently(self, minutes: int) -> int:
        """Get count of emails sent in the last N minutes"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # This requires a new column in the database to track email sending
                # For now, return 0 as placeholder
                return 0
                
        except Exception as e:
            logger.error(f"Error checking recent emails: {e}")
            return 0
    
    def run_continuous_automation(self, check_interval_minutes: int = 60):
        """Run continuous automation with periodic checks"""
        logger.info(f"Starting continuous automation (checking every {check_interval_minutes} minutes)")
        
        while True:
            try:
                self.run_automation_cycle()
                
                # Wait for next cycle
                logger.info(f"Waiting {check_interval_minutes} minutes until next cycle")
                time.sleep(check_interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("Automation stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in continuous automation: {e}")
                time.sleep(300)  # Wait 5 minutes before retrying
    
    def get_status_report(self) -> Dict:
        """Get automation status report"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get job statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_jobs,
                        SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                    FROM processed_jobs 
                    WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                """)
                
                stats = cursor.fetchone()
                
                return {
                    'total_jobs': stats['total_jobs'] or 0,
                    'applications_sent': stats['sent'] or 0,
                    'applications_failed': stats['failed'] or 0,
                    'pending_review': stats['pending'] or 0,
                    'configured_resumes': len(self.config['resumes']),
                    'gmail_configured': self.gmail_service is not None,
                    'sheets_configured': self.sheets_sync is not None and self.sheets_sync.client is not None
                }
                
        except Exception as e:
            logger.error(f"Error generating status report: {e}")
            return {}

def main():
    """Main entry point for the automation script"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Google Sheets Job Application Automation')
    parser.add_argument('--config', default='automation_config.json', help='Configuration file path')
    parser.add_argument('--mode', choices=['single', 'continuous'], default='single',
                       help='Run mode: single cycle or continuous automation')
    parser.add_argument('--limit', type=int, default=20, help='Number of jobs to process per cycle')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in minutes for continuous mode')
    parser.add_argument('--status', action='store_true', help='Show status report')
    parser.add_argument('--add-resume', nargs=5, metavar=('NAME', 'FILE', 'SKILLS', 'EXPERIENCE', 'DESCRIPTION'),
                       help='Add a new resume configuration')
    
    args = parser.parse_args()
    
    # Initialize automation manager
    try:
        automation = SheetsAutomationManager(args.config)
    except Exception as e:
        logger.error(f"Failed to initialize automation: {e}")
        return 1
    
    # Handle add-resume command
    if args.add_resume:
        name, file_path, skills, experience, description = args.add_resume
        skills_list = [s.strip() for s in skills.split(',')]
        
        success = automation.add_resume(name, file_path, skills_list, experience, description)
        if success:
            print(f"Successfully added resume: {name}")
        else:
            print(f"Failed to add resume: {name}")
        return 0 if success else 1
    
    # Handle status command
    if args.status:
        report = automation.get_status_report()
        print("\n=== AUTOMATION STATUS REPORT ===")
        for key, value in report.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
        return 0
    
    # Run automation
    try:
        if args.mode == 'single':
            automation.run_automation_cycle(args.limit)
        else:
            automation.run_continuous_automation(args.interval)
        return 0
    except KeyboardInterrupt:
        logger.info("Automation stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Automation failed: {e}")
        return 1

if __name__ == '__main__':
    exit(main())