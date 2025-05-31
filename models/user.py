from pydantic import BaseModel, EmailStr, UUID4
from typing import Optional, Literal
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

    class Config:
        from_attributes = True

class UserCreate(UserBase):
    password: str
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
    refresh_token: Optional[str] = None
    token_type: str = "bearer"

    class Config:
        from_attributes = True

class RefreshToken(BaseModel):
    refresh_token: str

    class Config:
        from_attributes = True
