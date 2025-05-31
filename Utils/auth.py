from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from passlib.context import CryptContext
import secrets

# Update these with your own secret key and algorithm
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"  # Change this in production
REFRESH_TOKEN_SECRET_KEY = "a3e8d3e7b88cf63bcaa6f0f4c09f6f7099f63b93b7a9563556c818166d25e094"  # Change this in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory store for refresh tokens (in production, use Redis or database)
refresh_token_db = {}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    from jose import jwt
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(user_id: int, email: str) -> str:
    """Create a refresh token for the user"""
    # Generate a random token
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Store the token in our database with user info and expiry
    refresh_token_db[token] = {
        "user_id": user_id,
        "email": email,
        "expires": expires
    }
    
    return token

def verify_refresh_token(refresh_token: str) -> Tuple[bool, Optional[Dict]]:
    """Verify if the refresh token is valid and return user info"""
    if refresh_token not in refresh_token_db:
        return False, None
    
    token_data = refresh_token_db[refresh_token]
    if datetime.utcnow() > token_data["expires"]:
        # Token has expired, remove it
        del refresh_token_db[refresh_token]
        return False, None
    
    return True, token_data

def revoke_refresh_token(refresh_token: str) -> bool:
    """Revoke a refresh token"""
    if refresh_token in refresh_token_db:
        del refresh_token_db[refresh_token]
        return True
    return False
