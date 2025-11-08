from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from ..db import get_db
from ..models.user import User
from ..schemas.user import UserCreate, UserLogin, UserOut, Token
from ..core.security import get_password_hash, verify_password, create_access_token
from ..core.config import ACCESS_TOKEN_EXPIRE_DELTA, SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/auth", tags=["Auth"])
bearer_scheme = HTTPBearer()

@router.post(
    "/signup",
    response_model=UserOut,
    summary="회원가입",
    status_code=status.HTTP_201_CREATED,
)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    """이메일 중복 확인 후 신규 사용자 생성"""
    exists = db.query(User).filter(User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    user = User(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post(
    "/login",
    response_model=Token,
    summary="로그인(JWT 발급)",
)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """이메일/비밀번호 검증 후 JWT 액세스 토큰 발급"""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(
        subject=str(user.id),
        expires_delta=ACCESS_TOKEN_EXPIRE_DELTA,
    )
    # Token 스키마가 access_token만 갖고 있다고 가정
    return Token(access_token=token)

@router.get(
    "/me",
    response_model=UserOut,
    summary="내 정보",
)
def me(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """Bearer 토큰에서 사용자 식별 후 프로필 반환"""
    token = creds.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")

    user = db.get(User, user_id)  # SQLAlchemy 2.x
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return user
