from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import timedelta
from auroqa.Utils.oauth import oauth, google, get_user_info_from_google
from auroqa.models.user import OAuthUserInfo, Token
from auroqa.models.crud import get_or_create_oauth_user
from auroqa.Utils.auth import create_access_token
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
import secrets
import os

router = APIRouter()

@router.get("/login/google")
async def login_google(request: Request):
    """
    Initiate Google OAuth login flow
    """
    # Generate a secure random state
    state = secrets.token_urlsafe(16)
    
    # Store state in session
    request.session['oauth_state'] = state
    
    # Use configured redirect URI from environment
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "https://debuggo.app/api/auth/google/callback")
    
    # Debug logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔍 OAuth Debug - GOOGLE_REDIRECT_URI from env: {os.getenv('GOOGLE_REDIRECT_URI')}")
    logger.info(f"🔍 OAuth Debug - Using redirect_uri: {redirect_uri}")
    logger.info(f"🔍 OAuth Debug - Google client_id: {os.getenv('GOOGLE_CLIENT_ID')}")
    
    return await google.authorize_redirect(request, redirect_uri, state=state)

@router.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    """
    Handle the Google OAuth callback
    """
    try:
        # Manually verify state parameter to prevent CSRF attacks
        callback_state = request.query_params.get('state')
        session_state = request.session.get('oauth_state')
        
        # Clear the state from session after use
        if 'oauth_state' in request.session:
            del request.session['oauth_state']
        
        # Skip state verification in development if needed
        # Comment this out in production for security
        # callback_state = session_state = "valid"
        
        if not callback_state or not session_state or callback_state != session_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state parameter. CSRF protection triggered."
            )
            
        # Get user info from Google
        user_info = await get_user_info_from_google(request)
        
        # Extract relevant user information
        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )
        
        # Create OAuth user info
        oauth_user = OAuthUserInfo(
            email=email,
            full_name=user_info.get("name"),
            auth_provider="google",
            auth_provider_id=user_info.get("sub"),  # Google's user ID
            profile_picture=user_info.get("picture")
        )
        
        # Get or create user in database
        with get_db_connection_context() as conn:
            user = get_or_create_oauth_user(conn, oauth_user)
            
            # Create access token
            access_token_expires = timedelta(hours=24)
            access_token = create_access_token(
                data={"sub": user.email}, expires_delta=access_token_expires
            )
            
            # Create token response
            token = Token(
                access_token=access_token,
                token_type="bearer",
                user_info={
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "profile_picture": user.profile_picture,
                    "role": user.role
                }
            )
            
            # Redirect to frontend with token
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            redirect_url = f"{frontend_url}?token={access_token}"
            return RedirectResponse(url=redirect_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication error: {str(e)}"
        )
