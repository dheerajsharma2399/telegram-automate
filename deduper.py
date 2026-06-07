"""Deduplication Engine for Jobs.

Implements tiered deduplication checks:
1. Exact fingerprint matching.
2. Simhash semantic similarity matching.
3. Email matching.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from normalizer import normalize_role, extract_location

logger = logging.getLogger(__name__)

def make_fingerprint(company: Optional[str], role: Optional[str], location: Optional[str] = None) -> str:
    """Generate a unique job fingerprint key.
    
    Format: normalize(company):normalize_role(role):normalize(location)
    """
    c = re.sub(r'[^a-z0-9]', '', (company or '').lower()) if company else 'unknown'
    r = normalize_role(role) if role else 'unknown'
    
    # Extract coarse location mapping
    loc_hint = extract_location(location or '') or ''
    l = loc_hint.lower().strip()[:50]
    
    return f"{c}:{r}:{l}"

def get_features(text: str) -> List[str]:
    """Tokenize text into features (words + character 3-grams) for Simhash."""
    text = text.lower()
    # Alphanumeric words of length >= 2
    words = re.findall(r'\b\w{2,}\b', text)
    # Character 3-grams
    cleaned_chars = re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', '', text))
    char_ngrams = [cleaned_chars[i:i+3] for i in range(len(cleaned_chars)-2)]
    return words + char_ngrams

def simhash(text: str) -> int:
    """Compute a 64-bit Simhash fingerprint for the given text."""
    if not text:
        return 0
    features = get_features(text)
    if not features:
        return 0
    
    v = [0] * 64
    for feature in features:
        h = hashlib.md5(feature.encode('utf-8')).digest()
        h_val = int.from_bytes(h[:8], byteorder='big')
        
        for i in range(64):
            bit = (h_val >> i) & 1
            if bit:
                v[i] += 1
            else:
                v[i] -= 1
                
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    # Convert to signed 64-bit int for Postgres BIGINT compatibility
    if fingerprint >= 0x8000000000000000:
        fingerprint -= 0x10000000000000000
    return fingerprint

def hamming_distance(h1: int, h2: int) -> int:
    """Compute Hamming distance between two 64-bit Simhashes."""
    return bin(h1 ^ h2).count('1')

class DedupAgent:
    """Agent that performs tiered deduplication checks against PostgreSQL."""
    
    def __init__(self, db: Any):
        self.db = db

    def find_duplicate(self, candidate: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Find if a candidate job is a duplicate in the database.
        
        Returns:
            Tuple of (matched_job, match_method) or (None, None)
        """
        company = candidate.get("company_name")
        job_role = candidate.get("job_role")
        location = candidate.get("location")
        email = candidate.get("email")
        jd_text = candidate.get("jd_text")
        role_category = candidate.get("role_category") or normalize_role(job_role or '')

        # Tier 1: Exact Fingerprint Match
        fingerprint = candidate.get("job_fingerprint") or make_fingerprint(company, job_role, location)
        if fingerprint and fingerprint != "unknown:unknown:":
            matched = self.db.jobs.search_by_fingerprint(fingerprint)
            if matched:
                return matched, "fingerprint"

        # Tier 2: Simhash Distance Match (Hamming distance < 3)
        if jd_text and len(jd_text) > 100 and role_category:
            cand_sim = simhash(jd_text)
            
            # Query for potential duplicates using Hamming distance directly in Postgres
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, job_id, company_name, job_role, jd_text, created_at, role_category
                        FROM jobs
                        WHERE role_category = %s 
                          AND simhash IS NOT NULL
                          AND created_at > NOW() - INTERVAL '30 days'
                          AND length(replace((simhash # %s)::bit(64)::text, '0', '')) < 3
                        LIMIT 1
                    """, (role_category, cand_sim))
                    row = cursor.fetchone()
            
            if row:
                logger.info("Semantic match (Hamming distance < 3) with existing job '%s' (%s) directly in SQL", row.get("job_role"), row.get("job_id"))
                return dict(row), "simhash"

        # Tier 3: Email Match
        if email:
            matched = self.db.jobs.search_by_email(email)
            if matched:
                return matched, "email"

        return None, None
