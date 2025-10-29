import json
import re
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp
import asyncio
from config import SYSTEM_PROMPT
import os
from pathlib import Path
import json

class LLMProcessor:
    def __init__(self, api_key: str, model: str, fallback_model: str):
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        # attempt to load a local user profile JSON (optional)
        self.user_profile = None
        try:
            profile_path = Path(__file__).parent / 'user_profile.json'
            if profile_path.exists():
                with open(profile_path, 'r', encoding='utf-8') as f:
                    self.user_profile = json.load(f)
        except Exception:
            self.user_profile = None
    
    async def parse_jobs(self, message_text: str, max_retries: int = 3) -> List[Dict]:
        """Parse job postings from message using LLM"""
        
        # Try primary model first
        jobs = await self._call_llm(message_text, self.model, max_retries)
        
        # If failed, try fallback model
        if jobs is None:
            print(f"  Primary model failed, trying fallback: {self.fallback_model}")
            jobs = await self._call_llm(message_text, self.fallback_model, max_retries)
        
        # If LLM completely failed, use regex fallback
        if jobs is None:
            print("  LLM failed, using regex fallback")
            jobs = self._regex_fallback(message_text)
        
        # If jobs were found, ensure each job has jd_text; if missing, try to split
        # the original message into sensible sections and assign per-job jd_text.
        result = jobs or []
        if result and any(not j.get('jd_text') for j in result):
            sections = re.split(r'\n\s*\n|---+', message_text)
            # assign sections to jobs in order as a best-effort mapping
            sec_iter = (s.strip() for s in sections if s.strip())
            for job in result:
                if not job.get('jd_text'):
                    try:
                        job['jd_text'] = next(sec_iter)
                    except StopIteration:
                        job['jd_text'] = message_text  # fallback to entire message
        return result
    
    async def _call_llm(self, message_text: str, model: str, 
                       max_retries: int) -> Optional[List[Dict]]:
        """Call LLM API with retry logic"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Parse the following message:\n\n{message_text}"}
            ],
            "temperature": 0.1,
            "max_tokens": 4000
        }
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.base_url, 
                                          headers=headers, 
                                          json=payload,
                                          timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data['choices'][0]['message']['content']
                            
                            # Parse JSON from response
                            jobs = self._extract_json(content)
                            if jobs is not None:
                                return jobs
                        else:
                            error_text = await response.text()
                            print(f"  LLM API error (attempt {attempt+1}): {response.status} - {error_text}")
                
                # Exponential backoff
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    
            except Exception as e:
                print(f"  LLM API exception (attempt {attempt+1}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        return None
    
    def _extract_json(self, content: str) -> Optional[List[Dict]]:
        """Extract JSON array from LLM response"""
        try:
            # Try direct JSON parse
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', 
                                 content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Try to find JSON array anywhere in text
            json_match = re.search(r'\[.*?\]', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
        
        return None
    
    def _regex_fallback(self, message_text: str) -> List[Dict]:
        """Fallback regex-based parsing"""
        jobs = []
        
        # Simple heuristic: split on double newlines or "---"
        sections = re.split(r'\n\s*\n|---+', message_text)
        
        for section in sections:
            if len(section.strip()) < 50:  # Too short to be a job
                continue
            
            job = {
                'company_name': self._extract_company(section),
                'job_role': self._extract_role(section),
                'location': self._extract_location(section),
                'eligibility': self._extract_eligibility(section),
                'email': self._extract_email(section),
                'phone': self._extract_phone(section),
                'application_link': self._extract_link(section),
                'recruiter_name': '',
                'email_subject': None,
                'jd_text': section.strip()
            }
            
            # Only add if we found at least company or role
            if job['company_name'] != 'Unknown' or job['job_role'] != 'Position':
                jobs.append(job)
        
        return jobs
    
    def _extract_company(self, text: str) -> str:
        patterns = [
            r'(?:Company|Organisation|Organization)[\s:]+([A-Za-z0-9\s&.,-]+?)(?:\n|$)',
            r'@([A-Za-z0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown"
    
    def _extract_role(self, text: str) -> str:
        patterns = [
            r'(?:Role|Position|Job Title)[\s:]+([A-Za-z0-9\s/,-]+?)(?:\n|$)',
            r'(?:hiring|looking for)[\s:]+([A-Za-z0-9\s/,-]+?)(?:\n|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Position"
    
    def _extract_location(self, text: str) -> str:
        pattern = r'(?:Location|Office)[\s:]+([A-Za-z0-9\s,/-]+?)(?:\n|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    def _extract_eligibility(self, text: str) -> str:
        pattern = r'(?:Eligibility|Batch|Graduation)[\s:]+([0-9\s,/-]+?)(?:\n|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    def _extract_email(self, text: str) -> Optional[str]:
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    
    def _extract_phone(self, text: str) -> Optional[str]:
        pattern = r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    
    def _extract_link(self, text: str) -> Optional[str]:
        pattern = r'https?://[^\s]+'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    
    def process_job_data(self, job_data: Dict, raw_message_id: int, generate_email: bool = False) -> Dict:
        """Processes and enriches raw job data extracted by the LLM.
        
        Args:
            job_data: Raw job data from LLM extraction
            raw_message_id: ID of the raw message
            generate_email: If True, generate email body during processing.
                           If False (default), leave email_body as None for later generation.
        """
        
        job_id = f"job_{raw_message_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        recruiter_name = job_data.get("recruiter_name", "")
        first_name, last_name = self._split_name(recruiter_name)
        
        application_method = "unknown"
        if job_data.get("email"):
            application_method = "email"
        elif job_data.get("application_link"):
            application_method = "link"
        elif job_data.get("phone"):
            application_method = "phone"

        email_subject = self._generate_email_subject(
            job_data.get("job_role", "Job Application"),
            job_data.get("email_subject")
        )

        jd_text_val = job_data.get('jd_text')
        if not jd_text_val:
            # fallback to the entire message text if not present
            jd_text_val = job_data.get('message_text') or job_data.get('full_text') or ''
        
        # Email body generation - only if explicitly requested
        email_body = None
        if generate_email:
            try:
                if self.user_profile:
                    email_body = self.generate_email_body(job_data, jd_text_val)
            except Exception:
                email_body = None

        return {
            "raw_message_id": raw_message_id,
            "job_id": job_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": job_data.get("email"),
            "company_name": job_data.get("company_name"),
            "job_role": job_data.get("job_role"),
            "location": job_data.get("location"),
            "eligibility": job_data.get("eligibility"),
            "application_method": application_method,
            "application_link": job_data.get("application_link"),  # FIX: Include application link
            "phone": job_data.get("phone"),  # FIX: Include phone number
            "recruiter_name": job_data.get("recruiter_name"),  # FIX: Include recruiter name
            "jd_text": jd_text_val,
            "email_subject": email_subject,
            "email_body": email_body,
            "status": "pending",
            "updated_at": datetime.now().isoformat(),
        }

    def generate_email_body(self, job_data: Dict, jd_text: str) -> str:
        """Enhanced email generation using job-specific personalization.
        
        This uses the sophisticated enhanced email generator for job-specific
        personalized outreach emails with skills matching and project prioritization.
        """
        try:
            # Try to use enhanced email generator
            if not hasattr(self, 'email_generator'):
                from enhanced_email_generator import EnhancedEmailGenerator
                self.email_generator = EnhancedEmailGenerator()
            
            # Generate job-specific email
            email_result = self.email_generator.generate_email(job_data, jd_text)
            return email_result['body']
            
        except Exception as e:
            print(f"Enhanced email generation failed: {e}, falling back to basic template")
            # Fallback to basic template
            return self._generate_basic_email_body(job_data, jd_text)
    
    def _generate_basic_email_body(self, job_data: Dict, jd_text: str) -> str:
        """Fallback basic email generation (original template-based approach)"""
        profile = self.user_profile or {}
        name = profile.get('full_name', 'Dheeraj Sharma')
        email = profile.get('email', '')
        current_title = profile.get('current_title', '')
        current_company = profile.get('current_company', '')
        linkedin = profile.get('linkedin', '')

        # pick up to two top projects for inclusion
        projects = profile.get('top_projects', [])[:2]
        proj_texts = []
        for p in projects:
            n = p.get('name')
            d = p.get('description')
            if n and d:
                proj_texts.append(f"{n}: {d}")

        project_section = ''
        if proj_texts:
            project_section = "\n\nA couple of relevant projects: \n- " + "\n- ".join(proj_texts)

        # Compose a short outreach body
        company = job_data.get('company_name') or ''
        role = job_data.get('job_role') or ''

        body = (
            f"Hi {job_data.get('recruiter_name') or 'Team'},\n\n"
            f"I came across the {role} opening at {company} and I wanted to express my interest."
            f" I am {name}, currently {current_title} at {current_company}."
            f"{project_section}\n\n"
            "I'm particularly excited about roles where I can contribute to backend systems, automation, and developer experience."
            " I'd love to discuss how I could help your team. You can reach me at "
            f"{email}.\n\nBest regards,\n{name}\n{linkedin}"
        )

        # Keep result reasonably sized
        if len(body) > 4000:
            body = body[:3990] + '...'

        return body

    def _split_name(self, full_name: str) -> tuple[str, str]:
        """Splits a full name into first and last name."""
        if not full_name:
            return "", ""
        parts = full_name.strip().split()
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])

    def _generate_email_subject(self, job_role: str, custom_subject: Optional[str]) -> str:
        """Generates an email subject line for the job application."""
        if custom_subject:
            return custom_subject.replace("[Your Name]", "Dheeraj Sharma").replace("[Name]", "Dheeraj Sharma")
        return f"Application for {job_role} - Dheeraj Sharma"
