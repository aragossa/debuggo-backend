from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime

class GenerateStepsRequest(BaseModel):
    project_id: Optional[UUID4] = None
    
    class Config:
        from_attributes = True
