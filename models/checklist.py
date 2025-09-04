from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ChecklistItemBase(BaseModel):
    title: str
    description: Optional[str] = None
    is_enabled: bool = True
    is_checked: bool = False
    order_index: int = 0

class ChecklistItemCreate(ChecklistItemBase):
    pass

class ChecklistItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    is_checked: Optional[bool] = None
    order_index: Optional[int] = None

class ChecklistItem(ChecklistItemBase):
    id: int
    checklist_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ChecklistBase(BaseModel):
    title: str
    description: Optional[str] = None
    is_active: bool = True

class ChecklistCreate(ChecklistBase):
    pass

class ChecklistUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class Checklist(ChecklistBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    items: List[ChecklistItem] = []

    class Config:
        from_attributes = True

class ChecklistWithoutItems(ChecklistBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
