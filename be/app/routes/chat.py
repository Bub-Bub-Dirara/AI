from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from be.app.core.db import get_db
from be.app.models.chat_thread import ChatThread, ChannelType
from be.app.models.chat_message import ChatMessage
from be.app.schemas.chat_thread import ThreadCreate, ThreadOut
from be.app.schemas.chat_message import MessageCreate

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("/threads", response_model=ThreadOut)
def create_thread(body: ThreadCreate, db: Session = Depends(get_db)):
    thread = ChatThread(user_id=body.user_id, channel=ChannelType(body.channel), title=body.title)
    db.add(thread); db.commit(); db.refresh(thread)
    return thread

@router.post("/threads/{thread_id}/messages")
def add_message(thread_id: int, body: MessageCreate, db: Session = Depends(get_db)):
    msg = ChatMessage(thread_id=thread_id, role=body.role, content=body.content,
                      step=body.step, meta=body.metadata or {})
    db.add(msg); db.commit(); db.refresh(msg)
    return {"id": msg.id, "created_at": msg.created_at}
