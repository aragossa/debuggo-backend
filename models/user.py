from pydantic import BaseModel, EmailStr, UUID4
from typing import Optional, Literal, Dict, Any
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    auth_provider: Optional[str] = None  # 'google', 'password', etc.
    auth_provider_id: Optional[str] = None  # External ID from auth provider
    profile_picture: Optional[str] = None  # URL to profile picture

    class Config:
        from_attributes = True

class UserCreate(UserBase):
    password: Optional[str] = None  # Optional for OAuth users
    client_id: Optional[UUID4] = None
    role: Optional[Literal['admin', 'user']] = 'user'

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    client_id: Optional[UUID4] = None
    role: str = 'user'

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_info: Optional[Dict[str, Any]] = None  # Additional user info for frontend

    class Config:
        from_attributes = True


class OAuthUserInfo(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    auth_provider: str
    auth_provider_id: str
    profile_picture: Optional[str] = None
