from __future__ import annotations

import argparse

from sqlalchemy import select

from app.audit import audit
from app.db import SessionLocal
from app.file_storage import storage
from app.models import ApplicationFile, utcnow


def purge_expired_files(batch_size: int = 100) -> tuple[int, int]:
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    now = utcnow()
    deleted = 0
    failed = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(ApplicationFile.id, ApplicationFile.object_key)
            .where(ApplicationFile.delete_after.is_not(None), ApplicationFile.delete_after <= now)
            .order_by(ApplicationFile.delete_after)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for file_id, object_key in rows:
            try:
                storage.delete(object_key)
            except Exception:
                failed += 1
                continue
            attachment = db.get(ApplicationFile, file_id)
            if not attachment or attachment.delete_after is None or attachment.delete_after > now:
                continue
            attachment.deleted_at = attachment.deleted_at or now
            attachment.delete_after = None
            attachment.ocr_text = None
            attachment.ocr_status = "DELETED"
            attachment.ocr_truncated = False
            audit(db, None, "APPLICATION_FILE_PURGED", "ApplicationFile", attachment.id, {"kind": attachment.kind, "document_type": attachment.document_type})
            db.commit()
            deleted += 1
    return deleted, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge expired private admission files.")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    deleted, failed = purge_expired_files(args.batch_size)
    print(f"deleted={deleted} failed={failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
