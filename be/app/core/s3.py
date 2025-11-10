from __future__ import annotations

from typing import Optional
import urllib.parse
import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from be.app.core.config import settings


class S3Client:
    """
    Thin wrapper around boto3 S3 client.
    - 업로드는 private로 저장
    - 다운로드는 presigned URL(get_object)로 제공
    - 외부에서는 프라이빗 속성(_session/_client)에 접근하지 말고 공개 메서드만 사용
    """

    def __init__(self) -> None:
        if not settings.s3_enabled:
            # 환경 미설정 시 안전하게 비활성화
            self._session = None
            self._client = None
            return

        # 세션 & 클라이언트 준비
        self._session = boto3.session.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        # s3v4 서명 사용
        self._client = self._session.client(
            "s3",
            config=Config(signature_version="s3v4"),
            region_name=settings.aws_region,
        )

    # -----------------------------
    # Utilities
    # -----------------------------
    @staticmethod
    def build_s3_key(user_id: int, category: str, original_filename: str) -> str:
        """user/{user_id}/{category}/{random}.ext 형태의 키 생성"""
        from secrets import token_hex

        name, ext = os.path.splitext(original_filename)
        return f"user/{user_id}/{category}/{token_hex(16)}{ext.lower()}"

    # -----------------------------
    # Upload
    # -----------------------------
    def upload_bytes(self, data: bytes, key: str, content_type: str) -> Optional[str]:
        """
        파일 바이트를 S3에 업로드. 성공 시 public base URL(설정된 경우) 반환.
        실제 다운로드는 presigned URL 사용 권장.
        """
        if not self._client:
            raise RuntimeError("S3 is not enabled/configured")

        self._client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ACL="private",
        )

        if settings.s3_public_base:
            return f"{settings.s3_public_base}/{urllib.parse.quote(key)}"
        return None

    # -----------------------------
    # Presign (download)
    # -----------------------------
    def presign_get_url(self, key: str, expires: int = 600) -> str:
        """
        get_object용 presigned URL 생성 (기본 10분)
        """
        if not self._client:
            raise RuntimeError("S3 is not enabled/configured")

        return self._client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=expires,
        )

    def generate_presigned_url(self, key: str, expires_in: int = 600) -> str:
        return self.presign_get_url(key=key, expires=expires_in)

    # -----------------------------
    # STS WhoAmI (health check 용)
    # -----------------------------
    def whoami(self) -> dict:
        """
        현재 자격 증명 확인 (외부에서 _session에 직접 접근하지 말고 이 메서드 사용)
        """
        if self._session:
            sts = self._session.client("sts", region_name=settings.aws_region)
        else:
            # s3 비활성 상태에서도 .env 자격으로 확인 시도
            sts = boto3.client(
                "sts",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
        return sts.get_caller_identity()

s3 = S3Client()

build_s3_key = S3Client.build_s3_key
