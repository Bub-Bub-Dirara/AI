from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
import os
import boto3

from botocore.exceptions import ClientError
from app.core import s3 as s3core
from app.core.config import settings
from app.core.s3 import s3, build_s3_key
from app.models.evidence_file import EvidenceFile, EvidenceCategory
from app.schemas.evidence_file import EvidenceFileOut
from app.core.db import get_db

# --- DummyUser가 필요하다면 유지 ---
from pydantic import BaseModel
class DummyUser(BaseModel):
    id: int = 1
    username: str = "test_user"
def get_current_user():
    return DummyUser()

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

def parse_category(cat: str) -> EvidenceCategory:
    try:
        return EvidenceCategory(cat)
    except Exception:
        return EvidenceCategory.other


@router.post("", response_model=EvidenceFileOut, status_code=status.HTTP_201_CREATED)
async def upload_evidence_file(
    category: str = Form(..., description="contract | message | transfer | other"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only pdf, jpg, png are allowed")

    data = await file.read()
    if len(data) == 0 or len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File must be >0 and <= {settings.MAX_UPLOAD_BYTES} bytes",
        )

    category_enum = parse_category(category)

    storage = "s3" if settings.s3_enabled else "local"
    s3_key = None
    s3_url = None
    stored_filename = ""

    if storage == "s3":
        try:
            s3_key = build_s3_key(user.id, category_enum.value, file.filename)
            s3_url = s3.upload_bytes(data, s3_key, file.content_type)
        except Exception as e:
            # S3 실패 시 503으로 명확화
            raise HTTPException(status_code=503, detail=f"S3 upload failed: {e}")
    else:
        uploads_dir = os.path.abspath("./uploads")
        user_dir = os.path.join(uploads_dir, f"user_{user.id}", category_enum.value)
        os.makedirs(user_dir, exist_ok=True)
        ext = ALLOWED_CONTENT_TYPES[file.content_type]
        import secrets
        stored_filename = secrets.token_hex(16) + ext
        with open(os.path.join(user_dir, stored_filename), "wb") as f:
            f.write(data)

    entity = EvidenceFile(
        user_id=user.id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        content_type=file.content_type,
        size_bytes=len(data),
        storage=storage,
        s3_key=s3_key,
        s3_url=s3_url,
        category=category_enum,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("", response_model=list[EvidenceFileOut])
def list_my_files(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return (
        db.query(EvidenceFile)
        .filter(EvidenceFile.user_id == user.id)
        .order_by(EvidenceFile.created_at.desc())
        .all()
    )


@router.get("/{file_id}/download-url")
def get_presigned_download_url(
    file_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    entity = (
        db.query(EvidenceFile)
        .filter(EvidenceFile.id == file_id, EvidenceFile.user_id == user.id)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Not found")

    if entity.storage != "s3":
        # 로컬 파일이면 여기서 명확히 차단 (400)
        raise HTTPException(
            status_code=400,
            detail=f"Presigned URL only for S3-backed files (this is {entity.storage})",
        )

    # s3가 활성화되지 않았을 때도 503로 명확히
    if not settings.s3_enabled:
        raise HTTPException(status_code=503, detail="S3 is not configured")

    try:
        url = s3.generate_presigned_url(entity.s3_key)
        return {"url": url}
    except Exception as e:
        # presign 실패는 503으로
        raise HTTPException(status_code=503, detail=f"S3 presign failed: {e}")


@router.get("/{file_id}/download")
def download_local_file(
    file_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    로컬 저장 파일 다운로드 (테스트/로컬 환경용)
    """
    entity = (
        db.query(EvidenceFile)
        .filter(EvidenceFile.id == file_id, EvidenceFile.user_id == user.id)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Not found")

    if entity.storage != "local":
        raise HTTPException(
            status_code=400,
            detail=f"This file is stored on {entity.storage}; use /download-url instead.",
        )

    uploads_dir = os.path.abspath("./uploads")
    file_path = os.path.join(
        uploads_dir, f"user_{user.id}", entity.category.value, entity.stored_filename
    )
    if not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail="Local file not found on disk")

    return FileResponse(
        path=file_path,
        media_type=entity.content_type,
        filename=entity.original_filename,
    )

@router.get("/api/files/_s3/health")
def s3_health():
    try:
        # STS 클라이언트 생성(동일한 .env 자격증명 사용)
        sts = boto3.client(
            "sts",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        ident = sts.get_caller_identity()
        return {
            "ok": True,
            "account": ident.get("Account"),
            "arn": ident.get("Arn"),
            "user_id": ident.get("UserId"),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"S3/STS check failed: {e}")
