from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from be.app.core.db import get_db
from be.app.models.chat_thread import ChatThread, ChannelType
from be.app.models.chat_message import ChatMessage
from be.app.schemas.chat_thread import (
    ThreadCreate,
    ThreadOut,
    ThreadDetailOut,
    ThreadListOut,
)
from be.app.schemas.chat_message import (
    MessageCreate,
    MessageOut,
    MessageListOut,
)

router = APIRouter(prefix="/chat", tags=["Chat"])

# --- POST: 스레드 생성 ---------------------------------------------------------
@router.post("/threads", response_model=ThreadOut)
def create_thread(body: ThreadCreate, db: Session = Depends(get_db)):
    thread = ChatThread(
        user_id=body.user_id,
        channel=ChannelType(body.channel),
        title=body.title,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread

# --- POST: 메시지 추가 ---------------------------------------------------------
@router.post("/threads/{thread_id}/messages", response_model=MessageOut)
def add_message(thread_id: int, body: MessageCreate, db: Session = Depends(get_db)):
    # 스레드 존재 확인 (권한 체크가 필요하면 여기서 user_id 검증 추가)
    thread = db.query(ChatThread).filter(ChatThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    msg = ChatMessage(
        thread_id=thread_id,
        role=body.role,
        content=body.content,
        step=body.step,
        meta_data=body.metadata or {},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

# --- GET: 내 스레드 목록(페이징) -----------------------------------------------
@router.get("/threads", response_model=ThreadListOut)
def list_threads(
    user_id: int = Query(..., description="조회 대상 사용자 ID"),
    channel: Optional[ChannelType] = Query(None, description="채널 필터"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(ChatThread).filter(ChatThread.user_id == user_id)
    if channel:
        q = q.filter(ChatThread.channel == channel)

    total = q.count()
    items = (
        q.order_by(ChatThread.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}

# --- GET: 특정 스레드 상세(최근 N개 메시지 포함) -------------------------------
@router.get("/threads/{thread_id}", response_model=ThreadDetailOut)
def get_thread(
    thread_id: int,
    limit: int = Query(20, ge=1, le=200, description="최근 메시지 개수"),
    db: Session = Depends(get_db),
):
    thread = db.query(ChatThread).filter(ChatThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    # 시간순으로 보여주고 싶으면 reverse
    msgs = list(reversed(msgs))

    # Pydantic v2: from_orm 호환 위해 dict로 구성
    detail = ThreadDetailOut(
        id=thread.id,
        user_id=thread.user_id,
        channel=thread.channel.value,
        title=thread.title,
        status=thread.status,
        created_at=thread.created_at,
        closed_at=thread.closed_at,
        recent_messages=[MessageOut.model_validate(m) for m in msgs],
    )
    return detail

# --- GET: 특정 스레드의 메시지 목록(페이징) ------------------------------------
@router.get("/threads/{thread_id}/messages", response_model=MessageListOut)
def list_messages(
    thread_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # 스레드 존재 확인
    exists = db.query(ChatThread.id).filter(ChatThread.id == thread_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Thread not found")

    q = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id)
    total = q.count()
    items = (
        q.order_by(ChatMessage.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }

# --- GET: 단일 메시지 조회(선택) -----------------------------------------------
@router.get("/messages/{message_id}", response_model=MessageOut)
def get_message(message_id: int, db: Session = Depends(get_db)):
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg
