import io
from datetime import UTC, datetime, timedelta
from uuid import UUID

from PIL import Image
from sqlalchemy import func, select

from app.config import settings
from app.file_storage import storage
from app.models import (
    AdmissionInvitation,
    ApplicationFile,
    ApplicationFileBlob,
    ApplicationStatusEvent,
    AuditEvent,
    BillingPeriod,
    ResidencePeriod,
    Resident,
    StudentApplication,
)
from app.ocr import OCRResult


def _png_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workflow(client, operator_token: str, admin_token: str, *, max_submissions: int = 1, document_types: list[str] | None = None):
    dormitory = client.post("/api/dormitories", headers=_headers(operator_token), json={"name": "North Dorm", "address": ""})
    assert dormitory.status_code == 201, dormitory.text
    campaign = client.post("/api/admissions/campaigns", headers=_headers(operator_token), json={
        "name": "Autumn intake",
        "dormitory_id": dormitory.json()["id"],
        "document_types": document_types or [],
        "custom_fields": [],
        "consent_version": "v1",
        "consent_text": "I agree to admission data processing.",
    })
    assert campaign.status_code == 201, campaign.text
    invitation = client.post("/api/admissions/invitations", headers=_headers(admin_token), json={
        "campaign_id": campaign.json()["id"],
        "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "max_submissions": max_submissions,
    })
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["link"].split("#", 1)[1]
    exchange = client.post("/api/public/invitations/exchange", json={"token": token, "draft_key": "stable-public-draft-key-0001"})
    assert exchange.status_code == 200, exchange.text
    return dormitory.json(), campaign.json(), invitation.json(), token, exchange.json()


def _fill_application(client, session: dict, *, phone: str = "+998901234567") -> None:
    response = client.patch("/api/public/application", headers={"X-CSRF-Token": session["csrf_token"]}, json={
        "first_name_latin": "Aziza",
        "last_name_latin": "Karimova",
        "birth_date": "2005-04-11",
        "phone": phone,
        "institution": "National University",
        "requested_move_in": "2026-11-01",
    })
    assert response.status_code == 200, response.text
    upload = client.post(
        "/api/public/application/files",
        headers={"X-CSRF-Token": session["csrf_token"]},
        data={"kind": "PHOTO", "document_type": ""},
        files={"upload": ("photo.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text


def test_admission_submit_is_idempotent_and_approval_does_not_bill(client, database, operator_token, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    monkeypatch.setattr(settings, "file_retention_days", 30)
    dormitory, _, invitation, raw_invite, public_session = _workflow(client, operator_token, admin_token)

    _fill_application(client, public_session)
    submitted = client.post("/api/public/application/submit", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"consent": True})
    assert submitted.status_code == 200, submitted.text
    first_result = submitted.json()
    assert first_result["access_code"]
    assert raw_invite not in str(database.query(AdmissionInvitation).first().token_hash)

    retry = client.post("/api/public/application/submit", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"consent": True})
    assert retry.status_code == 200, retry.text
    assert retry.json()["reference"] == first_result["reference"]
    assert retry.json()["access_code"] == ""

    application = database.scalar(select(StudentApplication).where(StudentApplication.reference == first_result["reference"]))
    assert application is not None
    assert application.tracking_code_hash
    assert first_result["access_code"] not in application.tracking_code_hash
    audit_details = [str(row.details) for row in database.scalars(select(AuditEvent)).all()]
    assert all(raw_invite not in value and first_result["access_code"] not in value for value in audit_details)
    assert database.scalar(select(func.count(ApplicationStatusEvent.id)).where(ApplicationStatusEvent.application_id == application.id, ApplicationStatusEvent.to_status == "SUBMITTED")) == 1
    assert database.get(AdmissionInvitation, UUID(invitation["id"])).submission_count == 1
    assert client.post("/api/public/invitations/exchange", json={"token": raw_invite, "draft_key": "another-public-draft-key-0002"}).status_code == 404

    admin = _headers(admin_token)
    asked = client.post(f"/api/admissions/applications/{application.id}/request-info", headers=admin, json={"reason": "Please confirm your phone number.", "fields": ["phone"]})
    assert asked.status_code == 200, asked.text
    assert asked.json()["status"] == "NEEDS_INFO"
    rejected_csrf = client.post("/api/public/application/respond", json={"phone": "+998901112233"})
    assert rejected_csrf.status_code == 403
    response = client.post("/api/public/application/respond", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"phone": "+998901112233"})
    assert response.status_code == 200, response.text
    submitted_again = client.post("/api/public/application/submit", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"consent": True})
    assert submitted_again.status_code == 200, submitted_again.text
    assert submitted_again.json()["access_code"] == ""
    assert application.tracking_code_hash

    asked_file = client.post(f"/api/admissions/applications/{application.id}/request-info", headers=admin, json={"reason": "Please upload a new photo.", "fields": ["photo"]})
    assert asked_file.status_code == 200
    stale_file_submit = client.post("/api/public/application/submit", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"consent": True})
    assert stale_file_submit.status_code == 422
    refreshed_photo = client.post(
        "/api/public/application/files",
        headers={"X-CSRF-Token": public_session["csrf_token"]},
        data={"kind": "PHOTO", "document_type": ""},
        files={"upload": ("new-photo.png", _png_bytes(), "image/png")},
    )
    assert refreshed_photo.status_code == 201
    final_submit = client.post("/api/public/application/submit", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"consent": True})
    assert final_submit.status_code == 200

    room = client.post("/api/rooms", headers=admin, json={"number": "101", "dormitory_id": dormitory["id"], "floor": 1, "capacity": 1})
    assert room.status_code == 201, room.text
    approved = client.post(f"/api/admissions/applications/{application.id}/approve", headers=admin, json={
        "reason": "Identity and documents checked.",
        "room_id": room.json()["id"],
        "move_in": "2026-11-01",
    })
    assert approved.status_code == 200, approved.text
    stored_file = database.scalar(select(ApplicationFile).where(ApplicationFile.application_id == application.id, ApplicationFile.deleted_at.is_(None)))
    assert stored_file is not None and stored_file.delete_after is not None
    resident = database.get(Resident, UUID(approved.json()["resident_id"]))
    assert resident is not None and resident.room_id is not None
    assert database.scalar(select(func.count(ResidencePeriod.id)).where(ResidencePeriod.resident_id == resident.id)) == 1
    assert database.scalar(select(func.count(BillingPeriod.id)).where(BillingPeriod.resident_id == resident.id)) == 0
    repeated_approval = client.post(f"/api/admissions/applications/{application.id}/approve", headers=admin, json={
        "reason": "Repeated request.", "room_id": room.json()["id"], "move_in": "2026-11-01",
    })
    assert repeated_approval.status_code == 200
    assert database.scalar(select(func.count(Resident.id))) == 1
    assert database.scalar(select(func.count(ResidencePeriod.id))) == 1


def test_invitation_uses_public_domain_when_local_setting_is_stale(client, operator_token, admin_token, monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "public_app_url", "http://localhost:5173")
    _, _, invitation, _, _ = _workflow(client, operator_token, admin_token)
    assert invitation["link"].startswith("https://dormflows.netlify.app/apply#")
    assert "https://dormflows.netlify.app" in settings.cors_origin_list


def test_ocr_text_is_only_returned_to_staff_and_is_removed_with_the_file(client, database, operator_token, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    monkeypatch.setattr("app.admissions_api.extract_document_text", lambda *_: OCRResult("COMPLETED", "STUDENT: Aziza Karimova"))
    _, campaign, _, _, public_session = _workflow(client, operator_token, admin_token, document_types=["ID"])
    assert campaign["document_types"] == ["ID"]
    _fill_application(client, public_session)
    upload = client.post(
        "/api/public/application/files",
        headers={"X-CSRF-Token": public_session["csrf_token"]},
        data={"kind": "DOCUMENT", "document_type": "ID"},
        files={"upload": ("identity.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["ocr_status"] == "COMPLETED"
    assert "ocr_text" not in upload.json()
    public_files = client.get("/api/public/application/files")
    assert public_files.status_code == 200
    assert all("ocr_text" not in file for file in public_files.json())

    application = database.scalar(select(StudentApplication))
    attachment = database.scalar(select(ApplicationFile).where(ApplicationFile.application_id == application.id, ApplicationFile.kind == "DOCUMENT"))
    admin = _headers(admin_token)
    detail = client.get(f"/api/admissions/applications/{application.id}", headers=admin)
    assert detail.status_code == 200, detail.text
    staff_file = next(file for file in detail.json()["files"] if file["id"] == str(attachment.id))
    assert staff_file["ocr_text"] == "STUDENT: Aziza Karimova"

    removed = client.delete(f"/api/admissions/applications/{application.id}/files/{attachment.id}", headers=admin)
    assert removed.status_code == 204
    database.refresh(attachment)
    assert attachment.ocr_text is None
    assert attachment.ocr_status == "DELETED"


def test_rejects_a_forged_image_instead_of_saving_it(client, database, operator_token, admin_token):
    _, _, _, _, public_session = _workflow(client, operator_token, admin_token, document_types=["ID"])
    response = client.post(
        "/api/public/application/files",
        headers={"X-CSRF-Token": public_session["csrf_token"]},
        data={"kind": "DOCUMENT", "document_type": "ID"},
        files={"upload": ("fake.png", b"\x89PNG\r\n\x1a\nnot-an-image", "image/png")},
    )
    assert response.status_code == 415
    assert database.scalar(select(func.count(ApplicationFile.id))) == 0


def test_invitation_pause_resume_revoke_expiry_and_role_access(client, database, operator_token, admin_token):
    dormitory, campaign, invitation, token, _ = _workflow(client, operator_token, admin_token)
    admin = _headers(admin_token)
    invitation_id = invitation["id"]

    assert client.post(f"/api/admissions/invitations/{invitation_id}/pause", headers=admin).json()["status"] == "PAUSED"
    denied = client.post("/api/public/invitations/exchange", json={"token": token, "draft_key": "paused-public-draft-key-001"})
    assert denied.status_code == 404
    assert client.post(f"/api/admissions/invitations/{invitation_id}/resume", headers=admin).json()["status"] == "ACTIVE"
    assert client.post("/api/public/invitations/exchange", json={"token": token, "draft_key": "resumed-public-draft-key-001"}).status_code == 200
    assert client.post(f"/api/admissions/invitations/{invitation_id}/revoke", headers=admin).json()["status"] == "REVOKED"
    assert client.post("/api/public/invitations/exchange", json={"token": token, "draft_key": "revoked-public-draft-key-001"}).status_code == 404

    row = database.get(AdmissionInvitation, UUID(invitation_id))
    row.revoked_at = None
    row.paused_at = None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    database.commit()
    expired = client.post("/api/public/invitations/exchange", json={"token": token, "draft_key": "expired-public-draft-key-001"})
    assert expired.status_code == 404

    campaign = client.get("/api/admissions/campaigns", headers=admin).json()[0]
    forbidden = client.post("/api/admissions/campaigns", headers=admin, json={
        "name": "Not allowed", "dormitory_id": campaign["dormitory_id"], "consent_text": "This should be rejected.",
    })
    assert forbidden.status_code == 403
    assert client.get("/api/admissions/applications").status_code == 401
    assert client.patch(f"/api/dormitories/{dormitory['id']}", headers=_headers(operator_token), json={"is_active": False}).status_code == 409
    closed = client.patch(f"/api/admissions/campaigns/{campaign['id']}/status", headers=_headers(operator_token), params={"status_value": "CLOSED"})
    assert closed.status_code == 200
    disabled = client.patch(f"/api/dormitories/{dormitory['id']}", headers=_headers(operator_token), json={"is_active": False})
    assert disabled.status_code == 200 and not disabled.json()["is_active"]
    assert client.get("/api/dormitories", headers=admin, params={"include_inactive": True}).status_code == 403
    assert any(not row["is_active"] for row in client.get("/api/dormitories", headers=_headers(operator_token), params={"include_inactive": True}).json())
    reopen = client.patch(f"/api/admissions/campaigns/{campaign['id']}/status", headers=_headers(operator_token), params={"status_value": "ACTIVE"})
    assert reopen.status_code == 409


def test_private_application_files_require_staff_auth_and_audit_metadata_only(client, database, operator_token, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    _, _, _, _, public_session = _workflow(client, operator_token, admin_token)
    _fill_application(client, public_session)
    file_rows = client.get("/api/public/application/files")
    assert file_rows.status_code == 200
    file_id = file_rows.json()[0]["id"]
    application = database.scalar(select(StudentApplication))

    unauthenticated = client.get(f"/api/admissions/applications/{application.id}/files/{file_id}")
    assert unauthenticated.status_code == 401
    denied = client.get(f"/api/admissions/applications/{application.id}/files/{file_id}", headers=_headers(admin_token))
    assert denied.status_code == 200
    assert denied.content.startswith(b"\x89PNG")
    audit_details = [str(row.details) for row in database.scalars(select(AuditEvent)).all()]
    assert all(public_session["csrf_token"] not in value for value in audit_details)
    assert all("valid image bytes" not in value for value in audit_details)


def test_production_file_storage_uses_postgres_and_supports_staff_download_and_delete(client, database, operator_token, admin_token, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "file_storage_backend", "local")
    assert storage.backend == "postgres"
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "file_storage_backend", "postgres")
    monkeypatch.setattr(settings, "file_retention_days", 365)
    _, _, _, _, public_session = _workflow(client, operator_token, admin_token)
    _fill_application(client, public_session)

    settings_response = client.get("/api/admissions/settings", headers=_headers(admin_token))
    assert settings_response.status_code == 200
    assert settings_response.json()["storage_backend"] == "postgres"
    assert settings_response.json()["uploads_enabled"] is True

    application = database.scalar(select(StudentApplication))
    attachment = database.scalar(select(ApplicationFile).where(ApplicationFile.application_id == application.id))
    blob = database.get(ApplicationFileBlob, attachment.object_key)
    assert blob is not None and blob.content.startswith(b"\x89PNG")
    public_files = client.get("/api/public/application/files")
    assert public_files.status_code == 200
    assert all("content" not in row and "ocr_text" not in row for row in public_files.json())

    downloaded = client.get(f"/api/admissions/applications/{application.id}/files/{attachment.id}", headers=_headers(admin_token))
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"\x89PNG")

    removed = client.delete(f"/api/admissions/applications/{application.id}/files/{attachment.id}", headers=_headers(admin_token))
    assert removed.status_code == 204
    assert database.get(ApplicationFileBlob, attachment.object_key) is None


def test_room_stay_intervals_reject_overlapping_approvals(client, operator_token, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    dormitory, _, _, invitation_token, first_session = _workflow(client, operator_token, admin_token, max_submissions=2)
    admin = _headers(admin_token)
    room = client.post("/api/rooms", headers=admin, json={"number": "202", "dormitory_id": dormitory["id"], "floor": 2, "capacity": 1})
    assert room.status_code == 201, room.text

    _fill_application(client, first_session)
    first_submit = client.post("/api/public/application/submit", headers={"X-CSRF-Token": first_session["csrf_token"]}, json={"consent": True})
    first_id = client.get("/api/admissions/applications", headers=admin, params={"q": first_submit.json()["reference"]}).json()["items"][0]["id"]
    first_approval = client.post(f"/api/admissions/applications/{first_id}/approve", headers=admin, json={
        "reason": "Checked.", "room_id": room.json()["id"], "move_in": "2026-11-01", "move_out": "2026-12-01",
    })
    assert first_approval.status_code == 200, first_approval.text

    second_exchange = client.post("/api/public/invitations/exchange", json={"token": invitation_token, "draft_key": "second-student-draft-key-0001"})
    assert second_exchange.status_code == 200, second_exchange.text
    second_session = second_exchange.json()
    _fill_application(client, second_session, phone="+998909998877")
    second_submit = client.post("/api/public/application/submit", headers={"X-CSRF-Token": second_session["csrf_token"]}, json={"consent": True})
    assert second_submit.status_code == 200, second_submit.text
    second_id = client.get("/api/admissions/applications", headers=admin, params={"q": second_submit.json()["reference"]}).json()["items"][0]["id"]
    conflict = client.post(f"/api/admissions/applications/{second_id}/approve", headers=admin, json={
        "reason": "Checked.", "room_id": room.json()["id"], "move_in": "2026-11-15", "move_out": "2026-12-15",
    })
    assert conflict.status_code == 409
