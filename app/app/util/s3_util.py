from io import BytesIO
from typing import Any, Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet

from app.config.config import settings

_s3_client: Optional[Any] = None
_cipher: Optional[Fernet] = None


def get_s3_client() -> Any:
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="eu-central-1",
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        _cipher = Fernet(settings.S3_ENCRYPTION_KEY.encode())
    return _cipher


def ensure_bucket() -> None:
    s3_client = get_s3_client()
    try:
        s3_client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
    except ClientError:
        s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)


def avatar_s3_key(file_name: str) -> str:
    return f"{settings.PROJECT_NAME}/avatars/{file_name}.png"


def upload_avatar(avatar_bytes: bytes, s3_key: str, encrypted: bool = True) -> None:
    s3_client = get_s3_client()
    cipher = get_cipher()
    buffer = BytesIO()
    data = cipher.encrypt(avatar_bytes) if encrypted else avatar_bytes
    buffer.write(data)
    buffer.seek(0)
    content_type = "application/octet-stream" if encrypted else "image/png"
    s3_client.upload_fileobj(
        buffer,
        settings.S3_BUCKET_NAME,
        s3_key,
        ExtraArgs={"ContentType": content_type},
    )


def download_avatar(s3_key: str, encrypted: bool = True) -> Optional[bytes]:
    s3_client = get_s3_client()
    cipher = get_cipher()
    try:
        buffer = BytesIO()
        s3_client.download_fileobj(settings.S3_BUCKET_NAME, s3_key, buffer)
        buffer.seek(0)
        data = buffer.getvalue()
        if encrypted:
            return cipher.decrypt(data)
        return data
    except ClientError:
        return None


def delete_avatar(s3_key: str) -> None:
    s3_client = get_s3_client()
    try:
        s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
    except ClientError:
        pass
