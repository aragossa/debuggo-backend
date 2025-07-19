from authlib.integrations.starlette_client import OAuth
from fastapi import Request
import os
from typing import Dict, Optional, Any

# Initialize OAuth
oauth = OAuth()

# Google OAuth configuration
# These values will be set from environment variables or configuration
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:9000/api/auth/google/callback"),
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
