import json
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path


class EnhancedEmailGenerator:
    """
    Enhanced email generator that creates job-specific personalized emails
    using the user's profile and job requirements.
    """
    
    def __init__(self, user_profile_path: str = "user_profile.json"):
        self.user_profile = self.load_user_profile(user_profile_path)
        self.role_templates = self.load_role_templates()
        self.skill_keywords = self.load_skill_keywords()
        
    def load_user_profile(self, path: str) -> Dict:
        """Load user profile from JSON file"""
        try:
            profile_path = Path(path)
            if profile_path.exists():
                with open(profile_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Return default profile if file doesn't exist
                return self.get_default_profile()
        except Exception as e:
            print(f"Error loading user profile: {e}")
            return self.get_default_profile()
    
    def get_default_profile(self) -> Dict:
        """Return default profile if user profile file is not found"""
        return {
            "full_name": "Dheeraj Sharma",
            "email": "deepakgp2128@gmail.com",
            "phone": "(+91) 98330 19396",
            "current_title": "Senior Software Engineer",
            "current_company": "Dattra Systems",
            "summary": "I build backend systems and developer tools. I help companies reduce costs and accelerate product development through automation, observability, and developer experience improvements.",
            "top_projects": [
                {
                    "name": "Jobhuntr",
                    "description": "An automated Telegram-to-Google-Sheets pipeline that extracts job postings from Telegram groups, parses them using LLMs, and prepares outreach emails."
                },
                {
                    "name": "SignalWatch", 
                    "description": "A lightweight observability agent that collects and forwards telemetry to a hosted analytics service with minimal overhead."
                },
                {
                    "name": "AutoDocs",
                    "description": "A documentation generator that converts code comments and API specs into well-structured markdown and HTML documentation."
                }
            ],
            "education": "B.Tech in Computer Science",
            "skills": ["Python", "AsyncIO", "Systems Design", "APIs", "Google Apps Script", "LLMs"],
            "availability": "Immediate",
            "location": "India",
            "linkedin": "https://www.linkedin.com/in/dheeraj-sharma/"
        }
    
    def load_role_templates(self) -> Dict:
        """Load email templates for different job types"""
        return {
            "backend": {
                "opening": "I came across the {job_role} opening at {company_name} and wanted to express my interest. I'm {name}, a {title} at {company}.",
                "skills_focus": "As a backend systems engineer, I specialize in building scalable systems and developer tools. My work focuses on automation, observability, and developer experience improvements.",
                "closing": "I'm particularly excited about {company_name}'s {company_interest} and would love to discuss how my backend systems experience could contribute to your team. I'm available immediately for remote or on-site work in India.",
                "projects_priority": ["jobhuntr", "signalwatch", "autodocs"]
            },
            "fullstack": {
                "opening": "I came across the {job_role} opportunity at {company_name} and wanted to apply. I'm {name}, currently working as a {title} at {company}.",
                "skills_focus": "My expertise spans backend systems, APIs, and developer tools. I enjoy building end-to-end solutions that improve developer productivity and system efficiency.",
                "closing": "I'm particularly interested in {company_name}'s {company_interest} and believe my full-stack development experience would be valuable for your team. Available for immediate start.",
                "projects_priority": ["jobhuntr", "autodocs", "signalwatch"]
            },
            "devops": {
                "opening": "I saw the {job_role} position at {company_name} and I'm very interested. I'm {name}, a {title} with a focus on systems automation and observability.",
                "skills_focus": "My background includes building lightweight infrastructure tools and monitoring systems that help teams maintain efficient, reliable systems with minimal overhead.",
                "closing": "I'm excited about {company_name}'s {company_interest} and would love to discuss how my systems engineering background could support your infrastructure needs.",
                "projects_priority": ["signalwatch", "jobhuntr", "autodocs"]
            },
            "ai_ml": {
                "opening": "I came across the {job_role} opportunity at {company_name} and I'm excited to apply. I'm {name}, a {title} with extensive experience in AI and automation systems.",
                "skills_focus": "My work involves building intelligent systems using LLMs, machine learning, and automation tools that help companies accelerate product development and reduce operational costs.",
                "closing": "I'm particularly interested in {company_name}'s {company_interest} and believe my AI/ML engineering experience would be valuable for your team. I'm available immediately for remote or on-site work.",
                "projects_priority": ["jobhuntr", "signalwatch", "autodocs"]
            },
            "systems": {
                "opening": "I found the {job_role} position at {company_name} very compelling. I'm {name}, a {title} specializing in systems architecture and performance optimization.",
                "skills_focus": "My expertise focuses on building efficient, scalable systems that improve developer experience and reduce operational overhead. I specialize in systems design, automation, and observability.",
                "closing": "I'm excited about {company_name}'s {company_interest} and would love to discuss how my systems engineering background could contribute to your technical challenges.",
                "projects_priority": ["signalwatch", "jobhuntr", "autodocs"]
            },
            "general": {
                "opening": "I came across the {job_role} opening at {company_name} and wanted to express my interest. I'm {name}, a {title} at {company}.",
                "skills_focus": "I build backend systems and developer tools that help companies reduce costs and accelerate product development through automation, observability, and developer experience improvements.",
                "closing": "I'm excited about {company_name}'s {company_interest} and would love to discuss how my experience could contribute to your team's success.",
                "projects_priority": ["jobhuntr", "signalwatch", "autodocs"]
            }
        }
    
    def load_skill_keywords(self) -> Dict:
        """Define keywords for matching skills to job requirements"""
        return {
            "python": ["python", "django", "flask", "fastapi", "pygame", "python3"],
            "javascript": ["javascript", "node.js", "nodejs", "react", "vue", "angular", "typescript"],
            "apis": ["api", "rest", "graphql", "microservices", "web services"],
            "databases": ["sql", "mysql", "postgresql", "mongodb", "redis", "database"],
            "cloud": ["aws", "azure", "gcp", "docker", "kubernetes", "cloud"],
            "devops": ["ci/cd", "jenkins", "gitlab", "terraform", "ansible", "deployment"],
            "ai_ml": ["machine learning", "tensorflow", "pytorch", "llm", "nlp", "artificial intelligence", "ai"],
            "systems": ["systems design", "architecture", "performance", "scalability", "infrastructure"],
            "backend": ["backend", "server-side", "api development", "database design"],
            "automation": ["automation", "scripting", "workflow", "orchestration"],
            "observability": ["monitoring", "observability", "telemetry", "logging", "metrics"],
            "documentation": ["documentation", "technical writing", "api docs", "knowledge management"]
        }
    
    def classify_job_type(self, job_data: Dict, jd_text: str) -> str:
        """
        Classify job type based on role and job description
        Returns: backend, frontend, fullstack, devops, ai_ml, systems, or general
        """
        # Combine role and description for analysis
        text = (job_data.get('job_role', '') + ' ' + jd_text).lower()
        
        # Define keyword sets for each job type
        backend_keywords = ['backend', 'server', 'api', 'database', 'microservices', 'django', 'flask', 'fastapi']
        frontend_keywords = ['frontend', 'ui', 'react', 'vue', 'angular', 'javascript', 'css', 'html']
        fullstack_keywords = ['full stack', 'full-stack', 'mern', 'mean', 'javascript', 'node']
        devops_keywords = ['devops', 'infrastructure', 'deployment', 'docker', 'kubernetes', 'ci/cd', 'jenkins']
        ai_ml_keywords = ['machine learning', 'ai', 'artificial intelligence', 'data science', 'tensorflow', 'pytorch', 'llm', 'nlp']
        systems_keywords = ['systems', 'infrastructure', 'performance', 'scalability', 'architecture', 'sre']
        
        # Score each category
        scores = {
            'backend': sum(1 for keyword in backend_keywords if keyword in text),
            'frontend': sum(1 for keyword in frontend_keywords if keyword in text),
            'fullstack': sum(1 for keyword in fullstack_keywords if keyword in text),
            'devops': sum(1 for keyword in devops_keywords if keyword in text),
            'ai_ml': sum(1 for keyword in ai_ml_keywords if keyword in text),
            'systems': sum(1 for keyword in systems_keywords if keyword in text)
        }
        
        # Return the job type with highest score, fallback to general
        max_score = max(scores.values())
        if max_score == 0:
            return 'general'
        
        return max(scores, key=scores.get)
    
    def extract_job_requirements(self, jd_text: str) -> List[str]:
        """Extract technical requirements from job description"""
        found_skills = []
        text = jd_text.lower()
        
        for skill, keywords in self.skill_keywords.items():
            if any(keyword in text for keyword in keywords):
                found_skills.append(skill)
        
        return found_skills
    
    def match_skills_to_job(self, user_skills: List[str], job_requirements: List[str]) -> List[str]:
        """Match user's skills to job requirements"""
        matched_skills = []
        
        # Convert user skills to lowercase for comparison
        user_skills_lower = [skill.lower() for skill in user_skills]
        
        for req in job_requirements:
            # Direct match
            if req in user_skills_lower:
                matched_skills.append(req)
            # Partial match (e.g., 'python' matches 'Python')
            else:
                for user_skill in user_skills_lower:
                    if req in user_skill or user_skill in req:
                        matched_skills.append(user_skill.title())
                        break
        
        return list(set(matched_skills))  # Remove duplicates
    
    def match_projects_to_job(self, projects: List[Dict], job_type: str, job_requirements: List[str]) -> List[Dict]:
        """Select most relevant projects for the job type and requirements"""
        if not projects:
            return []
        
        template = self.role_templates.get(job_type, self.role_templates['general'])
        priority_projects = template['projects_priority']
        
        # Score projects based on job type and requirements
        project_scores = []
        
        for project in projects:
            score = 0
            project_name = project.get('name', '').lower()
            project_desc = project.get('description', '').lower()
            
            # Priority scoring based on job type
            if project_name == priority_projects[0]:
                score += 3
            elif project_name in priority_projects[1:]:
                score += 2
            
            # Skills-based scoring
            for req in job_requirements:
                if req in ['python', 'apis', 'automation']:
                    if 'api' in project_desc or 'pipeline' in project_desc:
                        score += 2
                if req == 'ai_ml':
                    if any(word in project_desc for word in ['llm', 'ai', 'machine learning']):
                        score += 2
                if req == 'observability':
                    if 'monitoring' in project_desc or 'observability' in project_desc:
                        score += 2
                if req == 'systems':
                    if 'pipeline' in project_desc or 'systems' in project_desc:
                        score += 1
            
            project_scores.append((project, score))
        
        # Sort by score and return top 2-3 projects
        project_scores.sort(key=lambda x: x[1], reverse=True)
        selected_projects = [p[0] for p in project_scores[:3] if p[1] > 0]
        
        # If no projects scored well, return top 2 by default
        return selected_projects if selected_projects else projects[:2]
    
    def generate_company_interest(self, company_name: str, job_type: str) -> str:
        """Generate company-specific interest statement"""
        interests = {
            "google": "innovative products and technical excellence",
            "microsoft": "cloud computing and developer tools",
            "amazon": "scalable systems and customer-centric solutions",
            "netflix": "high-performance streaming and content delivery",
            "uber": "real-time systems and global marketplace technology",
            "stripe": "financial technology and payment infrastructure"
        }
        
        company_lower = company_name.lower()
        for company, interest in interests.items():
            if company in company_lower:
                return interest
        
        # Generic interests based on job type
        generic_interests = {
            "backend": "building scalable backend systems and APIs",
            "fullstack": "creating end-to-end solutions that improve user experience",
            "devops": "infrastructure automation and reliable deployment pipelines",
            "ai_ml": "intelligent systems and machine learning applications",
            "systems": "high-performance systems architecture and optimization",
            "general": "building innovative solutions that solve real problems"
        }
        
        return generic_interests.get(job_type, "innovative technology solutions")
    
    def format_projects_section(self, projects: List[Dict]) -> str:
        """Format projects section for email"""
        if not projects:
            return ""
        
        project_texts = []
        for project in projects:
            name = project.get('name', '')
            description = project.get('description', '')
            
            # Shorten description if too long
            if len(description) > 150:
                description = description[:147] + "..."
            
            project_texts.append(f"**{name}**: {description}")
        
        if len(project_texts) == 1:
            return f"Some of my relevant work includes {project_texts[0].lower()}."
        elif len(project_texts) == 2:
            return f"Some of my relevant work includes {project_texts[0].lower()} and {project_texts[1].lower()}."
        else:
            return f"Some of my relevant work includes {project_texts[0].lower()}, {project_texts[1].lower()}, and {project_texts[2].lower()}."
    
    def generate_subject(self, job_data: Dict, job_type: str) -> str:
        """Generate personalized email subject"""
        company_name = job_data.get('company_name', '')
        job_role = job_data.get('job_role', 'position')
        
        subjects = {
            "backend": f"Application for {job_role} - Backend Systems Engineer",
            "fullstack": f"Application for {job_role} - Full Stack Developer",
            "devops": f"Application for {job_role} - DevOps/Systems Engineer",
            "ai_ml": f"Application for {job_role} - AI/ML Engineer",
            "systems": f"Application for {job_role} - Systems Engineer",
            "general": f"Application for {job_role} - Dheeraj Sharma"
        }
        
        return subjects.get(job_type, f"Application for {job_role} - {self.user_profile['full_name']}")
    
    def generate_email(self, job_data: Dict, jd_text: str) -> Dict:
        """Generate complete personalized email"""
        # Step 1: Classify job type
        job_type = self.classify_job_type(job_data, jd_text)
        
        # Step 2: Extract job requirements
        job_requirements = self.extract_job_requirements(jd_text)
        
        # Step 3: Match skills and projects
        matched_skills = self.match_skills_to_job(self.user_profile['skills'], job_requirements)
        relevant_projects = self.match_projects_to_job(
            self.user_profile['top_projects'], job_type, job_requirements
        )
        
        # Step 4: Generate email components
        template = self.role_templates.get(job_type, self.role_templates['general'])
        
        # Personalized opening
        opening = template['opening'].format(
            job_role=job_data.get('job_role', 'position'),
            company_name=job_data.get('company_name', 'your company'),
            name=self.user_profile['full_name'],
            title=self.user_profile['current_title'],
            company=self.user_profile['current_company']
        )
        
        # Skills focus paragraph
        skills_paragraph = template['skills_focus']
        
        # Projects section
        projects_section = self.format_projects_section(relevant_projects)
        
        # Company-specific interest
        company_interest = self.generate_company_interest(
            job_data.get('company_name', ''), job_type
        )
        
        # Closing paragraph
        closing = template['closing'].format(
            company_name=job_data.get('company_name', 'your company'),
            company_interest=company_interest
        )
        
        # Skills highlight (if skills were matched)
        skills_highlight = ""
        if matched_skills:
            skills_list = ", ".join(matched_skills[:3])  # Top 3 skills
            skills_highlight = f"My experience with {skills_list} would be particularly valuable for this role."
        
        # Combine all parts
        email_body_parts = [
            opening,
            skills_paragraph,
            projects_section,
            skills_highlight,
            closing
        ]
        
        # Filter out empty parts
        email_body = "\n\n".join([part for part in email_body_parts if part.strip()])
        
        # Add contact information
        contact_info = f"\n\nYou can reach me at {self.user_profile['email']} or {self.user_profile['phone']}.\n\nBest regards,\n{self.user_profile['full_name']}\n{self.user_profile['linkedin']}"
        email_body += contact_info
        
        # Generate subject
        email_subject = self.generate_subject(job_data, job_type)
        
        return {
            'subject': email_subject,
            'body': email_body,
            'job_type': job_type,
            'matched_skills': matched_skills,
            'relevant_projects': [p['name'] for p in relevant_projects],
            'company_interest': company_interest
        }


def generate_enhanced_email(job_data: Dict, jd_text: str, user_profile_path: str = "user_profile.json") -> Dict:
    """
    Standalone function to generate enhanced email
    Usage: generate_enhanced_email(job_data, jd_text)
    """
    generator = EnhancedEmailGenerator(user_profile_path)
    return generator.generate_email(job_data, jd_text)


# Example usage and testing
if __name__ == "__main__":
    # Test with sample job data
    sample_job = {
        "company_name": "TechCorp",
        "job_role": "Senior Backend Engineer",
        "recruiter_name": "Sarah Johnson",
        "email": "hr@techcorp.com"
    }
    
    sample_jd = """
    We are looking for a Senior Backend Engineer to join our team. 
    The ideal candidate will have experience with Python, Django, API development, 
    microservices, and database design. Experience with Docker and AWS is preferred.
    """
    
    email = generate_enhanced_email(sample_job, sample_jd)
    print("Generated Email:")
    print(f"Subject: {email['subject']}")
    print(f"Body: {email['body']}")
    print(f"Job Type: {email['job_type']}")
    print(f"Matched Skills: {email['matched_skills']}")
    print(f"Relevant Projects: {email['relevant_projects']}")