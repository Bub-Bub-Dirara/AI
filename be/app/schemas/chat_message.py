from pydantic import BaseModel
from typing import Optional, Dict, Any

class MessageCreate(BaseModel):
    role: str
    content: str
    step: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
