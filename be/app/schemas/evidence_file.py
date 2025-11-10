from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal
from datetime import datetime

EvidenceCategory = Literal["contract", "message", "transfer", "other"]

class EvidenceFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # pydantic v2

    id: int
    user_id: int
    original_filename: str
    content_type: str
    size_bytes: int
    storage: str
    s3_key: Optional[str] = None
    s3_url: Optional[str] = None
    category: EvidenceCategory
    created_at: datetime
