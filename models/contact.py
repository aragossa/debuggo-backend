from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class ContactRequest(BaseModel):
    name: str
    message: str

class ContactRequestResponse(BaseModel):
    id: int
    name: str
    message: str
    created_at: datetime
    status: str
