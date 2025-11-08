from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import os

from ..db import get_db
from ..models.user import User
from ..core.security import get_password_hash

router = APIRouter(prefix="/api/admin", tags=["BE", "Admin"])

def _dev_guard():
    # 환경변수 DEV_MODE=1 일 때만 허용 (실서비스에서 차단 안전장치)
    if os.getenv("DEV_MODE") != "1":
        raise HTTPException(status_code=403, detail="DEV_MODE is not enabled")

@router.post("/seed-user", summary="(DEV) 샘플 유저 생성")
def seed_user(db: Session = Depends(get_db)):
    _dev_guard()
    email = "test@example.com"
    password = "PEssw0rd!"
    exists = db.query(User).filter(User.email == email).first()
    if exists:
        return {"ok": True, "msg": "already exists", "email": email}
    u = User(email=email, password_hash=get_password_hash(password))
    db.add(u); db.commit(); db.refresh(u)
    return {"ok": True, "id": u.id, "email": u.email, "password_hint": "PEssw0rd!"}

@router.get("/ping-db", summary="(DEV) DB 연결 확인")
def ping_db(db: Session = Depends(get_db)):
    _dev_guard()
    db.execute("SELECT 1")
    return {"ok": True}
