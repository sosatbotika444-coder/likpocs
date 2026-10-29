from __future__ import annotations

import io
import re
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApplicationFileBlob

ALLOWED_TYPES = {
    "application/pdf": (".pdf",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
}


def sniff_content_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(status_code=415, detail="Faqat PDF, JPEG, PNG yoki WebP faylini yuklash mumkin.")


def validate_upload(upload: UploadFile, content: bytes) -> tuple[str, str]:
    if not content:
        raise HTTPException(status_code=422, detail="Bo‘sh fayl yuklab bo‘lmaydi.")
    if len(content) > settings.file_max_bytes:
        raise HTTPException(status_code=413, detail="Fayl hajmi ruxsat etilgan chegaradan oshdi.")
    content_type = sniff_content_type(content)
    if content_type.startswith("image/"):
        expected_format = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format != expected_format:
                    raise HTTPException(status_code=415, detail="Rasm faylining formati noto'g'ri.")
                if image.width * image.height > settings.file_max_image_pixels:
                    raise HTTPException(status_code=413, detail="Rasm o'lchami ruxsat etilgan chegaradan oshdi.")
                image.verify()
        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(status_code=415, detail="Rasm fayli buzilgan yoki uni o'qib bo'lmadi.") from None
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix and suffix not in ALLOWED_TYPES[content_type]:
        raise HTTPException(status_code=415, detail="Fayl kengaytmasi uning mazmuniga mos emas.")
    raw_name = Path(upload.filename or "fayl").name
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_name).strip(" .")[:180] or "fayl"
    return content_type, safe_name


class PrivateFileStorage:
    @property
    def backend(self) -> str:
        configured_backend = settings.file_storage_backend.strip().lower()
        # Production defaults to durable PostgreSQL storage when an external
        # object store has not been configured. Railway already provisions the DB.
        if configured_backend == "local" and settings.environment.lower() == "production":
            return "postgres"
        return configured_backend

    def configured(self) -> bool:
        if self.backend == "local":
            return settings.environment != "production"
        if self.backend == "postgres":
            return True
        return self.backend == "s3" and all((settings.s3_bucket, settings.s3_access_key_id, settings.s3_secret_access_key))

    def _s3(self):
        if not self.configured() or self.backend != "s3":
            raise RuntimeError("Private S3 storage is not configured")
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def put(self, object_key: str, content: bytes, content_type: str, db: Session | None = None) -> None:
        if self.backend == "s3":
            self._s3().put_object(
                Bucket=settings.s3_bucket,
                Key=object_key,
                Body=io.BytesIO(content),
                ContentLength=len(content),
                ContentType=content_type,
                ContentDisposition="attachment",
                ServerSideEncryption="AES256",
            )
            return
        if self.backend == "postgres":
            if db is None:
                raise RuntimeError("PostgreSQL file storage requires a database session")
            db.add(ApplicationFileBlob(object_key=object_key, content=content))
            return
        if settings.environment == "production":
            raise RuntimeError("Local file storage is disabled in production")
        path = self._local_path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def local_path(self, object_key: str) -> Path:
        if self.backend != "local" or settings.environment == "production":
            raise RuntimeError("Local file storage is unavailable")
        return self._local_path(object_key)

    def _local_path(self, object_key: str) -> Path:
        root = Path(settings.file_local_directory).resolve()
        path = (root / object_key).resolve()
        if root not in path.parents:
            raise RuntimeError("Invalid private object key")
        return path

    def signed_download_url(self, object_key: str) -> str:
        if self.backend != "s3":
            raise RuntimeError("Signed URLs are available only for S3 storage")
        return self._s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": object_key, "ResponseContentDisposition": "attachment"},
            ExpiresIn=300,
        )

    def read(self, object_key: str, db: Session) -> bytes | None:
        if self.backend == "postgres":
            blob = db.get(ApplicationFileBlob, object_key)
            return blob.content if blob else None
        if self.backend == "s3":
            response = self._s3().get_object(Bucket=settings.s3_bucket, Key=object_key)
            body = response["Body"]
            try:
                return body.read(settings.file_max_bytes + 1)
            finally:
                body.close()
        path = self._local_path(object_key)
        return path.read_bytes() if path.exists() else None

    def delete(self, object_key: str, db: Session | None = None) -> None:
        if self.backend == "s3":
            self._s3().delete_object(Bucket=settings.s3_bucket, Key=object_key)
            return
        if self.backend == "postgres":
            if db is None:
                raise RuntimeError("PostgreSQL file storage requires a database session")
            db.execute(delete(ApplicationFileBlob).where(ApplicationFileBlob.object_key == object_key))
            return
        path = self._local_path(object_key)
        if path.exists():
            path.unlink()


storage = PrivateFileStorage()
