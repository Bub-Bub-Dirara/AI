from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.models import Base

class AnalysisSnapshot(Base):
    """
    사용자의 분석 결과(또는 판례/법령 분석 결과 등)를 저장하는 스냅샷 테이블
    - JeonSafe 프로젝트나 AI 분석 결과 백업 용도로 사용 가능
    """
    __tablename__ = "analysis_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 분석 결과를 저장할 주요 필드
    title = Column(String(255), nullable=False)  # 예: "계약서 위험 문장 분석 결과"
    description = Column(Text, nullable=True)  # 분석 설명
    result_json = Column(Text, nullable=True)  # JSON 문자열로 저장 (AI 결과 등)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계 설정 (User와 연결)
    user = relationship("User", backref="analysis_snapshots")

    def __repr__(self):
        return f"<AnalysisSnapshot(id={self.id}, title='{self.title}')>"
