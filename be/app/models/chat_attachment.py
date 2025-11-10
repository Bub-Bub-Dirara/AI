from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from be.app.models import Base

class ChatAttachment(Base):
    __tablename__ = "chat_attachments"

    id = Column(Integer, primary_key=True, index=True)
    file_url = Column(String, nullable=False)

    # __tablename__ 확인! "chat_messages"와 동일해야 함
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False)

    # 양쪽에 back_populates가 서로 일치해야 함
    message = relationship("ChatMessage", back_populates="attachments")
