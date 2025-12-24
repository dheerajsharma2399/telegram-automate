import json
import re
import random
from datetime import datetime
from typing import List, Dict, Optional, Union
import aiohttp
import asyncio
from config import SYSTEM_PROMPT
import os
from pathlib import Path

class LLMProcessor:    

    def __init__(self, api_keys: List[str], models: List[str], fallback_models: List[str]):
        self.api_keys = api_keys
        self.models = models
        self.fallback_models = fallback_models
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
        """Parse job postings from message using LLM with failover and rotation"""
        
        # Try primary model pool
        jobs = await self._try_pool(self.models, message_text, max_retries, "Primary")
        
        # If failed, try fallback model pool
        if jobs is None and self.fallback_models:
            print(f"  Primary pool failed, trying fallback pool...")
            jobs = await self._try_pool(self.fallback_models, message_text, max_retries, "Fallback")
        
        # If LLM completely failed, use regex fallback
        if jobs is None:
            print("  LLM failed, using regex fallback")
            jobs = self._regex_fallback(message_text)
        
        # If jobs were found, ensure each job has jd_text; if missing, try to split
        # the original message into sensible sections and assign per-job jd_text.
        result = jobs or []
        
        # ... (rest of the method remains the same)
        # Helper to find link in text
        def find_link_in_text(text):
            if not text: return None
            # Regex to capture http/https URLs, stopping at whitespace or end of string
            match = re.search(r'https?://[^\s]+', text)
            return match.group(0) if match else None
            
        # Helper to merge fragmented jobs (e.g. Email fragment + JD fragment)
        def _merge_fragmented_jobs(job_list):
            if not job_list or len(job_list) < 2:
                return job_list
            
            merged = []
            skip_next = False
            
            for i in range(len(job_list)):
                if skip_next:
                    skip_next = False
                    continue
                    
                current_job = job_list[i]
                
                if i < len(job_list) - 1:
                    next_job = job_list[i+1]
                    
                    # Normalize strings for comparison (remove spaces, special chars, lowercase)
                    def normalize(s): return re.sub(r'[^a-z0-9]', '', str(s).lower())
                    
                    c1 = normalize(current_job.get('company_name', ''))
                    c2 = normalize(next_job.get('company_name', ''))
                    
                    # Loose company match
                    same_company = (c1 == c2) or (c1 in c2) or (c2 in c1) or c1 == 'unknown' or c2 == 'unknown'
                    
                    if same_company:
                        jd_a_raw = current_job.get('jd_text', '') or ''
                        jd_b_raw = next_job.get('jd_text', '') or ''
                        
                        jd_a_len = len(jd_a_raw)
                        jd_b_len = len(jd_b_raw)
                        
                        email_a = bool(current_job.get('email'))
                        email_b = bool(next_job.get('email'))
                        
                        # Heuristic: Is Next a Contact Fragment?
                        is_next_contact = False
                        if jd_b_len < 300 and email_b and not email_a:
                            is_next_contact = True
                        if jd_b_raw.lower().strip().startswith(('how to apply', 'share your cv', 'send your resume', '📩')):
                            is_next_contact = True
                            
                        # Heuristic: Is Current a Contact Fragment?
                        is_curr_contact = False
                        if jd_a_len < 300 and email_a and not email_b:
                            is_curr_contact = True
                        if jd_a_raw.lower().strip().startswith(('how to apply', 'share your cv', 'send your resume', '📩')):
                            is_curr_contact = True

                        # Case A: Merge Next into Current
                        if is_next_contact and not is_curr_contact:
                            current_job['email'] = next_job['email']
                            if not current_job.get('application_link'):
                                current_job['application_link'] = next_job.get('application_link')
                            if current_job.get('company_name') == 'Unknown' and next_job.get('company_name') != 'Unknown':
                                current_job['company_name'] = next_job.get('company_name')
                            skip_next = True
                            
                        # Case B: Merge Current into Next
                        elif is_curr_contact and not is_next_contact:
                            next_job['email'] = current_job['email']
                            if not next_job.get('application_link'):
                                next_job['application_link'] = current_job.get('application_link')
                            if next_job.get('company_name') == 'Unknown' and current_job.get('company_name') != 'Unknown':
                                next_job['company_name'] = current_job.get('company_name')
                            
                            current_job = next_job
                            skip_next = True

                merged.append(current_job)
            return merged

        # Step 0: Merge fragmented jobs
        if result:
            result = _merge_fragmented_jobs(result)

        if result:
            # 1. Enhance jd_text using Position-Based Extraction (Raw Text Slicing)
            # This ensures we get the EXACT original text for each job, not an LLM summary.
            try:
                if message_text and len(result) > 0:
                    # Create a list of (job_index, start_index)
                    job_indices = []
                    current_search_pos = 0
                    
                    # Sort result by company name just in case, or trust LLM order? 
                    # Trusting LLM order is safer as they usually output in sequence.
                    for i, job in enumerate(result):
                        cname = job.get('company_name', '')
                        if not cname: continue
                        
                        # Find company name in text
                        idx = message_text.find(cname, current_search_pos)
                        if idx == -1:
                            # Try case-insensitive
                            idx = message_text.lower().find(cname.lower(), current_search_pos)
                        
                        if idx != -1:
                            job_indices.append((i, idx))
                            # Advance search position to avoid finding same company twice
                            current_search_pos = idx + len(cname)
                    
                    # Only apply slicing if we found positions for at least some jobs
                    if job_indices:
                        # Pre-calculate REAL start positions (start of the line) for all jobs
                        real_starts = []
                        for k in range(len(job_indices)):
                            job_idx, name_start_pos = job_indices[k]
                            
                            # Look back up to 50 chars for the preceding newline
                            lookback_limit = max(0, name_start_pos - 50)
                            prefix_text = message_text[lookback_limit:name_start_pos]
                            last_newline_idx = prefix_text.rfind('\n')
                            
                            if last_newline_idx != -1:
                                # Start from the character after the newline
                                real_start = lookback_limit + last_newline_idx + 1
                            else:
                                # No newline found, start from lookback limit (start of message)
                                real_start = lookback_limit
                            
                            real_starts.append((job_idx, real_start))
                            
                        # Now slice using the real start boundaries
                        for k in range(len(real_starts)):
                            job_idx, start_pos = real_starts[k]
                            
                            # Determine end position
                            if k < len(real_starts) - 1:
                                _, next_real_start = real_starts[k+1]
                                end_pos = next_real_start
                            else:
                                end_pos = len(message_text)
                                
                            # Extract the raw slice
                            raw_slice = message_text[start_pos:end_pos].strip()
                            
                            # Update the job's jd_text with the exact raw text
                            if len(raw_slice) > 10: # Sanity check
                                result[job_idx]['jd_text'] = raw_slice
                                
            except Exception as e:
                print(f"Error in raw text reconstruction: {e}")

            # 2. HYBRID FIX: If application_link or email is missing, try to find it in jd_text using regex
            for job in result:
                # Link Backfill
                if not job.get('application_link'):
                    found_link = find_link_in_text(job.get('jd_text'))
                    if found_link:
                        # Don't overwrite if the found link is just an email (regex shouldn't match emails but safety first)
                        if '@' not in found_link or 'http' in found_link:
                            job['application_link'] = found_link
                            # print(f"  [Hybrid Fix] Auto-detected link for {job.get('company_name')}: {found_link}")
                
                # Email Backfill
                if not job.get('email'):
                    found_email = self._extract_email(job.get('jd_text'))
                    if found_email:
                        job['email'] = found_email
                        # print(f"  [Hybrid Fix] Auto-detected email for {job.get('company_name')}: {found_email}")

        return result
    
    async def _try_pool(self, model_pool: List[str], message_text: str, max_retries: int, pool_name: str) -> Optional[List[Dict]]:
        """Try to fetch jobs using a specific model pool with retries and rotation"""
        if not model_pool:
            return None

        for attempt in range(max_retries):
            # Select random model and key
            model = random.choice(model_pool)
            api_key = random.choice(self.api_keys) if self.api_keys else None
            
            if not api_key:
                print("  Error: No API keys available")
                return None

            try:
                jobs = await self._call_llm(message_text, model, api_key)
                if jobs is not None:
                    return jobs
            except Exception as e:
                print(f"  {pool_name} pool error (attempt {attempt+1}/{max_retries}) with model {model}: {e}")
            
            # Exponential backoff
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return None

    async def _call_llm(self, message_text: str, model: str, api_key: str) -> Optional[List[Dict]]:
        """Make a single LLM API call"""
        
        headers = {
            "Authorization": f"Bearer {api_key}",
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
                        return self._extract_json(content)
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
        except Exception as e:
            # Re-raise to be handled by _try_pool
            raise e

    
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
        
        # Strategy 1: Split by "Company - " if present (User Request)
        # We look for "Company -" at the start of a line.
        # (?m) enables multiline mode for ^
        # Updated to support optional numbering like "1) Company -" or "7. Company -"
        company_split_pattern = r'(?:\n|^)\s*(?:[\d]+[\).]\s*)?(?:Company|Organisation|Organization)\s*[-:–—]\s*'
        
        if re.search(company_split_pattern, message_text, re.IGNORECASE):
            # Find all start indices of the pattern
            matches = list(re.finditer(company_split_pattern, message_text, re.IGNORECASE))
            sections = []
            
            for i in range(len(matches)):
                start_pos = matches[i].start()
                # If it matched the newline before, we want to include the "Company..." text
                # check if the match started with newline
                if message_text[start_pos] == '\n':
                    start_pos += 1
                
                if i < len(matches) - 1:
                    end_pos = matches[i+1].start()
                else:
                    end_pos = len(message_text)
                
                sections.append(message_text[start_pos:end_pos].strip())
                
        else:
            # Strategy 2: Original fallback (newlines / dashes)
            raw_sections = re.split(r'\n\s*\n|---+', message_text)
            
            # Merge sections that look like continuations (e.g. "How to Apply")
            sections = []
            if raw_sections:
                sections.append(raw_sections[0])
                for i in range(1, len(raw_sections)):
                    prev = sections[-1]
                    curr = raw_sections[i]
                    
                    # Check if current section is just contact info
                    is_continuation = False
                    lower_curr = curr.lower().strip()
                    if (lower_curr.startswith("how to apply") or 
                        lower_curr.startswith("share your cv") or 
                        lower_curr.startswith("send your resume") or
                        (len(curr) < 200 and ("@" in curr or "http" in curr) and "company" not in lower_curr)):
                        is_continuation = True
                    
                    if is_continuation:
                        sections[-1] = prev + "\n\n" + curr
                    else:
                        sections.append(curr)
        
        for section in sections:
            if len(section.strip()) < 20:  # Too short to be a job (lowered threshold slightly)
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
            
            # Only add if we found at least company or role, OR if it has a valid email/link
            # (Sometimes regex misses company name but we still want the lead)
            if (job['company_name'] != 'Unknown' or job['job_role'] != 'Position') or (job['email'] or job['application_link']):
                jobs.append(job)
        
        return jobs
    
    def _extract_company(self, text: str) -> str:
        patterns = [
            # Handle "Company - Name" or "Company: Name" - Add parens and other dash types
            r'(?:Company|Organisation|Organization)[\s]*[-:–—][\s]*([A-Za-z0-9\s&.,()–—]+?)(?:\n|$)',
            # Fallback for just space separator if colon/dash missing
            r'(?:Company|Organisation|Organization)[\s]+([A-Za-z0-9\s&.,()–—]+?)(?:\n|$)',
            r'@([A-Za-z0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown"
    
    def _extract_role(self, text: str) -> str:
        patterns = [
            # Handle "Role - Name" or "Role: Name" - Add parens and other dash types
            r'(?:Role|Position|Job Title)[\s]*[-:–—][\s]*([A-Za-z0-9\s/,-–—()]+?)(?:\n|$)',
            r'(?:Role|Position|Job Title)[\s]+([A-Za-z0-9\s/,-–—()]+?)(?:\n|$)',
            r'(?:hiring|looking for)[\s:]+([A-Za-z0-9\s/,-–—()]+?)(?:\n|$)',
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
