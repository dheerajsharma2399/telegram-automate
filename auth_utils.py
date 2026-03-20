import os
import functools
import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)

def require_api_key(f):
    """
    API Key authentication decorator for Flask routes.
    Checks for API key in X-API-Key header or api_key query parameter.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in header or query param
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        # Get valid API key from environment
        valid_key = os.getenv('API_KEY')
        
        # If no API_KEY configured, allow (for development)
        if not valid_key:
            return f(*args, **kwargs)
        
        # Validate provided key
        if not api_key or api_key != valid_key:
            logger.warning(f"Unauthorized access attempt to {request.path}")
            return jsonify({'error': 'Unauthorized - Invalid or missing API key'}), 401
        
        return f(*args, **kwargs)
    return decorated_function
