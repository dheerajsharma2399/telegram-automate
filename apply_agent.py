import logging
import asyncio
from typing import Dict
from llm_processor import LLMProcessor

logger = logging.getLogger(__name__)

def generate_email_draft(
    jd_text: str,
    profile: dict,
    company: str = "",
    role: str = "",
    recruiter_name: str = ""
) -> Dict:
    """
    Synchronous wrapper for LLMProcessor.generate_email_for_job.
    Used by background threads in Flask.
    """
    from config import OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS
    
    # Initialize a temporary processor for this call
    # In a real app, you might want to pass the existing instance
    llm = LLMProcessor(OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS)
    
    # Run the async method synchronously
    try:
        return asyncio.run(llm.generate_email_for_job(
            jd_text=jd_text,
            profile=profile,
            company=company,
            role=role,
            recruiter_name=recruiter_name
        ))
    except Exception as e:
        logger.error(f"Failed to generate email draft: {e}")
        raise
