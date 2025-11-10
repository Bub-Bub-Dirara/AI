from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)  # .env 로드

import os
import secrets
from datetime import timedelta

# ===== JWT / Security =====
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ACCESS_TOKEN_EXPIRE_DELTA = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

# ===== App Settings =====
class Settings:
    def __init__(self):
        self.app_env = os.getenv("APP_ENV", "local")

        # S3
        self.aws_region = os.getenv("AWS_REGION", "")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.s3_bucket = os.getenv("S3_BUCKET", "")
        self.s3_public_base = os.getenv("S3_PUBLIC_BASE", "")

        # 업로드 용량(바이트). 기본 20MB
        self.MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))

    @property
    def s3_enabled(self) -> bool:
        """S3 업로드 활성화 여부 (필수 값 4종이 모두 채워져야 True)."""
        return all([
            self.aws_region,
            self.aws_access_key_id,
            self.aws_secret_access_key,
            self.s3_bucket,
        ])

settings = Settings()