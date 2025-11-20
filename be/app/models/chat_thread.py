import enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from be.app.core.db import Base

class ChannelType(str, enum.Enum):
    PREVENTION = "PREVENTION"
    POST_CASE = "POST_CASE"

class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    channel = Column(Enum(ChannelType), nullable=False)
    title = Column(String, nullable=True)
    status = Column(String, default="OPEN")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True))

    # 새로 추가: 이 스레드에 연결된 리포트 파일 (EvidenceFile.id)
    report_file_id = Column(Integer, ForeignKey("evidence_files.id"), nullable=True)

    # 관계
    messages = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    report_file = relationship("EvidenceFile", backref="chat_threads", lazy="selectin")
