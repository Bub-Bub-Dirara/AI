import secrets
from datetime import timedelta

# 실제 운영에선 .env로 분리 권장
SECRET_KEY = secrets.token_urlsafe(32)  # 개발용 자동 생성
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 60분
ACCESS_TOKEN_EXPIRE_DELTA = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
