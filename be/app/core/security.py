from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from be.app.core.config import SECRET_KEY, ALGORITHM

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(subject: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {"sub": subject, "iat": now, "exp": now + expires_delta}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
