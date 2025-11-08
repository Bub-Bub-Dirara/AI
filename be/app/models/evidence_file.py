from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, BigInteger
from sqlalchemy.orm import relationship
import enum

from app.models import Base

class EvidenceCategory(str, enum.Enum):
    contract = "contract"    # 계약서
    message  = "message"     # 문자 내역
    transfer = "transfer"    # 입금 내역
    other    = "other"       # 기타

class EvidenceFile(Base):
    __tablename__ = "evidence_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    original_filename = Column(String(255), nullable=False)
    stored_filename   = Column(String(255), nullable=False)  # 로컬 저장 시 파일명
    content_type      = Column(String(100), nullable=False)
    size_bytes        = Column(BigInteger, nullable=False)

    # 저장 위치
    storage = Column(String(20), nullable=False)  # "s3" | "local"
    s3_key  = Column(String(512), nullable=True)
    s3_url  = Column(String(1024), nullable=True) # 퍼블릭 접근 시

    category = Column(Enum(EvidenceCategory), nullable=False, default=EvidenceCategory.other)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="evidence_files")
