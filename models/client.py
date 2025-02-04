from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import Optional

class ClientBase(BaseModel):
    name: str

    class Config:
        from_attributes = True

class ClientCreate(ClientBase):
    pass

class Client(ClientBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
