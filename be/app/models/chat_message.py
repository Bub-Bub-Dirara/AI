from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, String, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from be.app.core.db import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    role = Column(String(32), nullable=False)  # "user" | "assistant" | "system" 등
    content = Column(Text, nullable=False)
    step = Column(String(64), nullable=True)  # 파이프라인 단계 태깅용
    meta_data = Column(JSON, nullable=True)  # 임의 메타데이터 보관
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 역참조 (스레드)
    thread = relationship("ChatThread", back_populates="messages")

    # 첨부파일 역참조가 이미 있다면 유지
    attachments = relationship(
        "ChatAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
