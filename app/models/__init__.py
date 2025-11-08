from app.core.db import Base  # 모든 모델이 공유할 Base

# --- 테이블 등록을 위해 모델 모듈을 import ---
from .user import User
from .chat_thread import ChatThread
from .chat_message import ChatMessage
from .chat_attachment import ChatAttachment
from .audit_log import AuditLog
from .analysis_snapshot import AnalysisSnapshot

# 새로 만든 파일 업로드 메타 모델
from .evidence_file import EvidenceFile

__all__ = [
    "Base",
    "User",
    "ChatThread",
    "ChatMessage",
    "ChatAttachment",
    "AuditLog",
    "AnalysisSnapshot",
    "EvidenceFile",
]
