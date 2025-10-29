from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime

class GenerateStepsRequest(BaseModel):
    project_id: Optional[UUID4] = None
    environment_id: Optional[int] = None
    ai_model_id: Optional[int] = None
    force_preconditions: Optional[bool] = False
    
    class Config:
        from_attributes = True
