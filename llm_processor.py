import json
import re
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp
import asyncio
from config import SYSTEM_PROMPT
import os
from pathlib import Path

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
            "Content-Type": "application/json",
            "HTTP-Referer": "https://job.mooh.me",  # Required by OpenRouter
            "X-Title": "Telegram Job Scraper"      # Required by OpenRouter
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
        # if generate_email:
        #     try:
        #         if self.user_profile:
        #             email_body = self.generate_email_body(job_data, jd_text_val)
        #     except Exception:
        #         email_body = None

        # Use the sheet_name provided by the LLM, with a sensible fallback.
        sheet_name = job_data.get('sheet_name', 'non-email')
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
            "experience_required": job_data.get("experience_required"),  # NEW: Experience requirements
            "job_relevance": job_data.get("job_relevance"),  # NEW: Job relevance for freshers
            "application_method": application_method,
            "application_link": job_data.get("application_link"),  # FIX: Include application link
            "phone": job_data.get("phone"),  # FIX: Include phone number
            "recruiter_name": job_data.get("recruiter_name"),  # FIX: Include recruiter name
            "jd_text": jd_text_val,
            "email_subject": email_subject,
            "email_body": email_body,
            "status": "pending",
            "updated_at": datetime.now().isoformat(),
            "is_hidden": False,
            "sheet_name": sheet_name,
        }

    def _extract_job_skills(self, jd_text: str) -> List[str]:
        """Extract skills mentioned in job description"""
        # Common tech stack patterns
        patterns = [
            r'JavaScript', r'React', r'Node\.js', r'Next\.js', r'AWS', r'PostgreSQL',
            r'Python', r'Docker', r'FastAPI', r'Flask', r'Vue\.js', r'Angular',
            r'TypeScript', r'MongoDB', r'Redis', r'GraphQL', r'Tailwind',
            r'HTML', r'CSS', r'SQL', r'Linux', r'Git'
        ]
        
        skills = []
        for pattern in patterns:
            if re.search(pattern, jd_text, re.IGNORECASE):
                skills.append(pattern.replace('\\', '').replace('.js', 'JS'))
        
        return skills

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
