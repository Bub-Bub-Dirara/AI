from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Literal, List
from .chat_message import MessageOut

Channel = Literal["PREVENTION", "POST_CASE"]

class ThreadCreate(BaseModel):
    # mappingPage에서 쓸 body
    user_id: int
    channel: Channel
    title: Optional[str] = None
    # 새 필드: 리포트 파일 ID (EvidenceFile.id)
    report_file_id: Optional[int] = None


class ThreadOut(BaseModel):
    id: int
    user_id: int
    channel: Channel
    title: Optional[str] = None
    status: str
    report_file_id: Optional[int] = None
    created_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ThreadDetailOut(ThreadOut):
    # 스레드 상세에서 메시지 리스트까지 같이 내려줄 때 사용
    recent_messages: Optional[List[MessageOut]] = None


class ThreadListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ThreadOut]
