from pydantic import BaseModel
from typing import Optional, Literal

Channel = Literal["PREVENTION", "POST_CASE"]

class ThreadCreate(BaseModel):
    user_id: int
    channel: Channel
    title: Optional[str] = None

class ThreadOut(BaseModel):
    id: int
    user_id: int
    channel: Channel
    title: Optional[str]
    status: str
    class Config:
        from_attributes = True
