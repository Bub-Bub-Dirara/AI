from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class MessageCreate(BaseModel):
    role: str
    content: str
    step: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MessageOut(BaseModel):
    id: int
    thread_id: int
    role: str
    content: str
    step: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[MessageOut]
