from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
from sqlalchemy.sql import func
from be.app.core.db import Base
import enum

class ChannelType(str, enum.Enum):
    PREVENTION = "PREVENTION"
    POST_CASE = "POST_CASE"

class ChatThread(Base):
    __tablename__ = "chat_thread"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    channel = Column(Enum(ChannelType), nullable=False)
    title = Column(String, nullable=True)
    status = Column(String, default="OPEN")  # OPEN/CLOSED/ARCHIVED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
