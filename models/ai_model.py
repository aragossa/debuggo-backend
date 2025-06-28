from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class AIModelBase(BaseModel):
    name: str
    model_id: str
    description: Optional[str] = None
    is_active: bool = True
    is_default: bool = False

class AIModelCreate(AIModelBase):
    pass

class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    model_id: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

class AIModel(AIModelBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class UserAIModelPreference(BaseModel):
    ai_model_id: int
