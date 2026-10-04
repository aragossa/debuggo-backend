from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime

class GenerateStepsRequest(BaseModel):
    project_id: Optional[UUID4] = None
    environment_id: Optional[int] = None
    ai_model_id: Optional[int] = None
    # UI tests: let the model use calls of the project's API library to prepare and clean up data.
    # Not sent = allowed.
    use_api: Optional[bool] = None
    
    class Config:
        from_attributes = True
