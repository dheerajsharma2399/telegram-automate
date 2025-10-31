#!/usr/bin/env python3
"""
Enhanced Email Generator for Telegram Job Scraper Bot
This module provides enhanced email generation with IoT project prioritization,
GitHub integration, and updated contact information.
"""

import json
import re
from datetime import datetime
from typing import Dict, Optional
import os
from pathlib import Path


class EnhancedEmailGenerator:
    """Enhanced email generator with IoT priority and GitHub integration"""
    
    def __init__(self, user_profile_path: str = "user_profile.json"):
        self.user_profile_path = user_profile_path
        self.user_profile = self._load_user_profile()
        
    def _load_user_profile(self) -> Dict:
        """Load user profile from JSON file"""
        try:
            if os.path.exists(self.user_profile_path):
                with open(self.user_profile_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load user profile: {e}")
        
        # Default profile if file doesn't exist
        return {
            "full_name": "Dheeraj Sharma",
            "email": "dheerajsharma2930@gmail.com",
            "current_title": "Backend Developer & Automation Specialist",
            "current_company": "TechFlow Systems",
            "linkedin": "linkedin.com/in/dheeraj-sharma-2a8367259",
            "github": "github.com/DheerajSharma2930",
            "phone": "+91-9829197483",
            "top_projects": [
                {
                    "name": "IoT Monitoring System",
                    "description": "Real-time IoT sensor monitoring with alert system",
                    "github": "https://github.com/DheerajSharma2930/iot-monitoring-system",
                    "demo": "Live demo available",
                    "tech_stack": ["Python", "MQTT", "InfluxDB", "Grafana", "ESP32"]
                },
                
            ]
        }
    
    def generate_enhanced_email(self, job_data: Dict, jd_text: str = "") -> str:
        """Generate enhanced email body with IoT priority and GitHub links"""
        
        profile = self.user_profile
        name = profile.get('full_name', 'Dheeraj Sharma')
        email = profile.get('email', 'dheerajsharma2399@gmail.com')
        current_title = profile.get('current_title', 'Backend Developer & Automation Specialist')
        current_company = profile.get('current_company', 'Sonar Instruments and Technology Pvt Ltd')
        linkedin = profile.get('linkedin', 'linkedin.com/in/dheerajsharma2399')
        github = profile.get('github', 'github.com/gheerajsharma2399')
        phone = profile.get('phone', '+91-8860964920')
        
        company = job_data.get('company_name', 'your organization')
        role = job_data.get('job_role', 'the position')
        recruiter_name = job_data.get('recruiter_name', 'Team')
        
        # Always prioritize IoT projects first
        projects = profile.get('top_projects', [])
        iot_projects = [p for p in projects if 'IoT' in p.get('name', '')]
        other_projects = [p for p in projects if 'IoT' not in p.get('name', '')]
        
        # Take first 2 IoT projects and 1 other project for email
        selected_projects = iot_projects[:2] + other_projects[:1]
        
        # Build project section
        project_section = ""
        if selected_projects:
            project_texts = []
            for i, proj in enumerate(selected_projects, 1):
                name = proj.get('name', '')
                description = proj.get('description', '')
                github_url = proj.get('github', '')
                demo = proj.get('demo', '')
                tech_stack = proj.get('tech_stack', [])
                
                tech_list = ", ".join(tech_stack[:4])  # Limit to 4 technologies
                if tech_list:
                    tech_list = f" ({tech_list})"
                
                project_text = f"{name}: {description}{tech_list} - {github_url}"
                if demo and "live" in demo.lower():
                    project_text += f" | {demo}"
                
                project_texts.append(f"{i}. {project_text}")
            
            if project_texts:
                project_section = "\n\nA couple of relevant projects that demonstrate my IoT and automation expertise:\n" + "\n".join(f"• {text}" for text in project_texts)
        
        # Analyze job requirements for better matching
        backend_keywords = ['backend', 'api', 'server', 'database', 'python', 'django', 'flask']
        iot_keywords = ['iot', 'sensor', 'automation', 'monitoring', 'embedded', 'arduino']
        
        job_text_lower = (job_data.get('job_role', '') + ' ' + jd_text).lower()
        
        emphasis = ""
        if any(keyword in job_text_lower for keyword in backend_keywords):
            emphasis += " I'm particularly excited about backend development opportunities where I can contribute to building robust APIs, scalable systems, and database optimization. "
        
        if any(keyword in job_text_lower for keyword in iot_keywords):
            emphasis += " My IoT project experience would be especially valuable for this role, as I've successfully implemented real-time sensor networks, data collection systems, and automation solutions. "
        
        # Build the email body
        body = (
            f"Hi {recruiter_name},\n\n"
            f"I came across the {role} opening at {company} and I wanted to express my interest."
            f" I am {name}, currently {current_title} at {current_company}."
            f"{emphasis}"
            f"{project_section}\n\n"
            "I'm particularly excited about roles where I can contribute to backend systems, automation, "
            "and developer experience. With my hands-on experience in IoT systems, real-time monitoring, "
            "and automation, I bring a unique perspective to software development that combines practical "
            "problem-solving with scalable architecture design.\n\n"
            "You can reach me directly at "
            f"{email} or {phone}. I'd love to discuss how I could help your team build "
            "innovative solutions that bridge hardware and software effectively.\n\n"
            "Best regards,\n"
            f"{name}\n"
            f"📧 {email}\n"
            f"📱 {phone}\n"
            f"💼 LinkedIn: {linkedin}\n"
            f"💻 GitHub: {github}"
        )
        
        # Ensure reasonable length
        if len(body) > 4000:
            # Trim project section if too long
            if project_section:
                trimmed_projects = selected_projects[:1]  # Keep only the most relevant project
                if trimmed_projects:
                    proj = trimmed_projects[0]
                    tech_stack = ", ".join(proj.get('tech_stack', [])[:3])
                    if tech_stack:
                        tech_stack = f" ({tech_stack})"
                    
                    project_section = (
                        f"\n\nHere's a project that demonstrates my relevant experience:\n"
                        f"• {proj.get('name', '')}: {proj.get('description', '')}{tech_stack} - {proj.get('github', '')}"
                    )
            
            body = (
                f"Hi {recruiter_name},\n\n"
                f"I came across the {role} opening at {company} and I wanted to express my interest."
                f" I am {name}, currently {current_title} at {current_company}."
                f"{emphasis}"
                f"{project_section}\n\n"
                "I bring strong experience in backend development, automation, and IoT systems."
                " You can reach me at {email} or {phone} to discuss how I could contribute to your team.\n\n"
                f"Best regards,\n"
                f"{name}\n"
                f"📧 {email} | 📱 {phone} | 💼 {linkedin} | 💻 {github}"
            )
        
        return body.strip()
    
    def generate_subject_line(self, job_data: Dict, custom_subject: Optional[str] = None) -> str:
        """Generate enhanced subject line"""
        
        job_role = job_data.get('job_role', 'Job Application')
        name = self.user_profile.get('full_name', 'Dheeraj Sharma')
        company = job_data.get('company_name', 'your organization')
        
        if custom_subject:
            # Clean up common placeholders
            custom_subject = custom_subject.replace("[Your Name]", name)
            custom_subject = custom_subject.replace("[Name]", name)
            custom_subject = custom_subject.replace("[Company]", company)
            return custom_subject
        
        # Generate contextual subject based on role
        role_lower = job_role.lower()
        
        if 'backend' in role_lower or 'api' in role_lower:
            return f"Backend Developer Application - {name}"
        elif 'iot' in role_lower or 'sensor' in role_lower:
            return f"IoT & Automation Specialist - {name}"
        elif 'automation' in role_lower:
            return f"Automation Engineer Application - {name}"
        elif 'full stack' in role_lower or 'full-stack' in role_lower:
            return f"Full Stack Developer - {name}"
        else:
            return f"Application for {job_role} - {name}"


def test_enhanced_email_generation():
    """Test the enhanced email generation"""
    
    generator = EnhancedEmailGenerator()
    
    # Test job data
    test_job = {
        'company_name': 'TechCorp',
        'job_role': 'Backend Developer',
        'recruiter_name': 'HR Team',
        'location': 'Bangalore, India'
    }
    
    test_jd = "We are looking for a backend developer with Python and Django experience. Experience with APIs and database optimization is preferred."
    
    # Generate email
    email_body = generator.generate_enhanced_email(test_job, test_jd)
    subject_line = generator.generate_subject_line(test_job)
    
    print("Generated Email Subject:", subject_line)
    print("\nGenerated Email Body:")
    print("=" * 50)
    print(email_body)
    print("=" * 50)
    print(f"\nEmail length: {len(email_body)} characters")
    
    return email_body, subject_line


if __name__ == "__main__":
    test_enhanced_email_generation()