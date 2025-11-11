from authlib.integrations.starlette_client import OAuth
from fastapi import Request
import os
from typing import Dict, Optional, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables before initializing OAuth
# This ensures GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are available
env_path = Path('/app/.env')
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

# Initialize OAuth
oauth = OAuth()

# Google OAuth configuration
# These values will be set from environment variables or configuration
import logging
logger = logging.getLogger(__name__)
client_id = os.getenv("GOOGLE_CLIENT_ID", "")
client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
logger.info(f"🔍 OAuth Init - GOOGLE_CLIENT_ID loaded: {client_id[:10]}... (length: {len(client_id)})")
logger.info(f"🔍 OAuth Init - GOOGLE_CLIENT_SECRET loaded: {'*' * len(client_secret)} (length: {len(client_secret)})")

google = oauth.register(
    name="google",
    client_id=client_id,
    client_secret=client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        # redirect_uri should be passed dynamically in authorize_redirect(), not hardcoded here
    },
)

async def get_user_info_from_google(request: Request) -> Dict[str, Any]:
    """
    Get user information from Google after successful authentication
    """
    try:
        # Get the token from Google OAuth
        token = await google.authorize_access_token(request)
        
        # Try to get user info from userinfo endpoint
        resp = await google.get('https://www.googleapis.com/oauth2/v3/userinfo', token=token)
        user_info = resp.json()
        
        # If we don't have the required fields, try to get them from the token
        if 'sub' not in user_info and 'id_token' in token:
            try:
                id_token_info = await google.parse_id_token(request, token)
                # Merge the information
                user_info.update(id_token_info)
            except Exception as e:
                print(f"Error parsing ID token: {e}")
        
        return user_info
    except Exception as e:
        # Log the error and re-raise
        print(f"Error getting user info from Google: {e}")
        raise
