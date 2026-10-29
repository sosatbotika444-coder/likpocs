import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

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


def test_admission_approval_creates_resident_billing_and_updates_statistics(client, database, operator_token, admin_token, tmp_path, monkeypatch):
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

    room = client.post("/api/rooms", headers=admin, json={"number": "101", "dormitory_id": dormitory["id"], "floor": 1, "capacity": 1, "price": "300000"})
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
    assert resident.agreed_price == 300000
    assert resident.payment_period_days == 30
    periods = database.scalars(select(BillingPeriod).where(BillingPeriod.resident_id == resident.id)).all()
    assert len(periods) == 1
    assert periods[0].charge_amount == 300000
    assert periods[0].start_date.isoformat() == "2026-11-01"
    assert periods[0].end_date.isoformat() == "2026-12-01"

    summary_headers = _headers(admin_token)
    summary = client.get("/api/admissions/summary", headers=summary_headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["approved_applications"] == 1
    assert summary.json()["linked_residents"] == 1
    assert Decimal(summary.json()["expected_payments"]) == Decimal("300000.00")
    assert Decimal(summary.json()["outstanding_debt"]) == Decimal("300000.00")
    assert Decimal(summary.json()["actual_revenue_this_month"]) == Decimal("0.00")

    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    recorded_payment = client.post("/api/payments", headers=admin, json={
        "resident_id": str(resident.id), "amount": "100000", "payment_date": today.isoformat(), "method": "CASH",
    })
    assert recorded_payment.status_code == 201, recorded_payment.text
    summary = client.get("/api/admissions/summary", headers=summary_headers)
    assert Decimal(summary.json()["actual_revenue_this_month"]) == Decimal("100000.00")
    assert Decimal(summary.json()["outstanding_debt"]) == Decimal("200000.00")

    expense = client.post("/api/expenses", headers=admin, json={
        "expense_date": today.isoformat(), "category": "UTILITIES", "description": "Test utility cost",
        "amount": "25000", "method": "CASH", "reference": "",
    })
    assert expense.status_code == 201, expense.text
    dashboard = client.get("/api/dashboard", headers=summary_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert Decimal(dashboard.json()["actual_revenue"]) == Decimal("100000.00")
    assert Decimal(dashboard.json()["actual_expenses"]) == Decimal("25000.00")
    assert Decimal(dashboard.json()["net_cash_flow"]) == Decimal("75000.00")
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


def test_approval_links_matching_resident_without_duplicate_billing(client, database, operator_token, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    dormitory, _, _, _, public_session = _workflow(client, operator_token, admin_token)
    admin = _headers(admin_token)
    room = client.post("/api/rooms", headers=admin, json={
        "number": "303", "dormitory_id": dormitory["id"], "floor": 3, "capacity": 2, "price": "500000",
    })
    assert room.status_code == 201, room.text
    existing = client.post("/api/residents", headers=_headers(operator_token), json={
        "first_name": "Aziza", "last_name": "Karimova", "phone": "+998901234567",
        "payment_period_days": 30, "agreed_price": "400000",
        "billing_start": "2026-11-01", "billing_end": "2026-12-01",
    })
    assert existing.status_code == 201, existing.text

    _fill_application(client, public_session)
    submitted = client.post("/api/public/application/submit", headers={"X-CSRF-Token": public_session["csrf_token"]}, json={"consent": True})
    assert submitted.status_code == 200, submitted.text
    application = database.scalar(select(StudentApplication).where(StudentApplication.reference == submitted.json()["reference"]))
    assert application is not None
    duplicates = client.get(f"/api/admissions/applications/{application.id}/duplicates", headers=admin)
    assert duplicates.status_code == 200, duplicates.text
    assert duplicates.json()[0]["id"] == existing.json()["id"]
    assert Decimal(duplicates.json()[0]["agreed_price"]) == Decimal("400000.00")
    assert duplicates.json()[0]["payment_period_days"] == 30

    approved = client.post(f"/api/admissions/applications/{application.id}/approve", headers=admin, json={
        "reason": "Existing record verified.", "room_id": room.json()["id"], "move_in": "2026-11-01",
        "resident_id": existing.json()["id"],
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["resident_id"] == existing.json()["id"]
    resident = database.get(Resident, UUID(existing.json()["id"]))
    assert resident is not None and resident.room_id == UUID(room.json()["id"])
    assert resident.agreed_price == 400000
    assert database.scalar(select(func.count(Resident.id))) == 1
    assert database.scalar(select(func.count(BillingPeriod.id)).where(BillingPeriod.resident_id == resident.id)) == 1


def test_openrouter_failure_status_mapping_is_actionable_and_safe():
    from types import SimpleNamespace

    from app.ai_extraction import _provider_failure_status

    assert _provider_failure_status(SimpleNamespace(status_code=401)) == "PROVIDER_AUTH_ERROR"
    assert _provider_failure_status(SimpleNamespace(status_code=402)) == "PROVIDER_BILLING_ERROR"
    assert _provider_failure_status(SimpleNamespace(status_code=403)) == "PROVIDER_ACCESS_ERROR"
    assert _provider_failure_status(SimpleNamespace(status_code=404)) == "PROVIDER_MODEL_ERROR"
    assert _provider_failure_status(SimpleNamespace(status_code=429)) == "PROVIDER_RATE_LIMITED"
    assert _provider_failure_status(SimpleNamespace(status_code=400)) == "PROVIDER_REJECTED"
    assert _provider_failure_status(SimpleNamespace(status_code=503)) == "PROVIDER_UNAVAILABLE"
    assert _provider_failure_status(SimpleNamespace()) == "FAILED"


def test_free_vision_model_is_blocked_for_private_identity_documents(
    client,
    database,
    operator_token,
    admin_token,
    tmp_path,
    monkeypatch,
):
    import asyncio

    from app.ai_extraction import (
        extract_identity_document,
        openrouter_document_processing_available,
        openrouter_processing_issue,
    )

    monkeypatch.setattr(settings, "openrouter_api_key", "test-only-key")
    monkeypatch.setattr(settings, "openrouter_enabled", True)
    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    monkeypatch.setattr(
        settings,
        "openrouter_model",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    )

    assert openrouter_processing_issue() == "UNSAFE_MODEL_ROUTE"
    assert openrouter_document_processing_available() is False
    result = asyncio.run(extract_identity_document(_png_bytes(), "image/png"))
    assert result.status == "UNSAFE_MODEL_ROUTE"
    assert result.data == {}

    _, _, _, _, public_session = _workflow(
        client,
        operator_token,
        admin_token,
        document_types=["ID"],
    )
    assert public_session["campaign"]["ai_processing_available"] is False
    assert public_session["campaign"]["ai_processing_issue"] == "UNSAFE_MODEL_ROUTE"
    _fill_application(client, public_session)
    calls = []

    async def unexpected_openrouter_call(payload):
        calls.append(payload)
        raise AssertionError("free model must not receive private documents")

    monkeypatch.setattr("app.ai_extraction._post_chat_completion", unexpected_openrouter_call)
    upload = client.post(
        "/api/public/application/files",
        headers={
            "X-CSRF-Token": public_session["csrf_token"],
            "X-AI-Processing-Consent": "true",
        },
        data={"kind": "DOCUMENT", "document_type": "ID"},
        files={"upload": ("identity.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["ai_status"] == "UNSAFE_MODEL_ROUTE"
    assert calls == []
    application = database.scalar(select(StudentApplication))
    assert application is not None and application.ai_processing_consented_at is None


def test_selected_openrouter_vision_model_is_allowed_and_directly_configured(monkeypatch):
    from app.ai_extraction import openrouter_processing_issue

    monkeypatch.setattr(settings, "openrouter_api_key", "test-only-key")
    monkeypatch.setattr(settings, "openrouter_enabled", True)
    monkeypatch.setattr(settings, "openrouter_model", "dots-studio/dots-3-note-preview:free")

    assert openrouter_processing_issue() is None


def test_unexpected_openrouter_http_error_keeps_safe_provider_status(monkeypatch):
    import asyncio

    from app.ai_extraction import extract_identity_document

    class ProviderError(Exception):
        status_code = 400

    async def reject_request(_payload):
        raise ProviderError("private response body must not be returned")

    monkeypatch.setattr(settings, "openrouter_api_key", "test-only-key")
    monkeypatch.setattr(settings, "openrouter_enabled", True)
    monkeypatch.setattr(settings, "openrouter_model", "dots-studio/dots-3-note-preview:free")
    monkeypatch.setattr("app.ai_extraction.local_ocr_available", lambda: False)
    monkeypatch.setattr("app.ai_extraction._post_chat_completion", reject_request)

    result = asyncio.run(extract_identity_document(_png_bytes(), "image/png", allow_external_ai=True))
    assert result.status == "PROVIDER_REJECTED"
    assert result.data == {}


def test_openrouter_suggestions_require_consent_and_are_private(client, database, operator_token, admin_token, tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(settings, "file_local_directory", str(tmp_path / "private-files"))
    monkeypatch.setattr(settings, "openrouter_api_key", "test-only-key")
    monkeypatch.setattr(settings, "openrouter_enabled", True)
    monkeypatch.setattr(settings, "openrouter_model", "test/private-vision-model")
    calls = []

    async def fake_openrouter(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("simulated temporary provider failure")
        return {"choices": [{"message": {"content": json.dumps({
            "last_name_latin": "KARIMOVA",
            "first_name_latin": "ISMOIL",
            "middle_name_latin": "ANVAR QIZI",
            "birth_date": "11.04.2005",
            "phone": "+998000000000",
        })}}]}

    monkeypatch.setattr("app.ai_extraction._post_chat_completion", fake_openrouter)
    _, campaign, _, _, public_session = _workflow(client, operator_token, admin_token, document_types=["ID"])
    assert campaign["document_types"] == ["ID"]
    _fill_application(client, public_session)
    file_payload = {
        "data": {"kind": "DOCUMENT", "document_type": "ID"},
        "files": {"upload": ("identity.png", _png_bytes(), "image/png")},
    }
    upload_without_consent = client.post(
        "/api/public/application/files",
        headers={"X-CSRF-Token": public_session["csrf_token"]},
        **file_payload,
    )
    assert upload_without_consent.status_code == 201, upload_without_consent.text
    assert upload_without_consent.json()["ai_status"] == "CONSENT_REQUIRED"
    assert upload_without_consent.json()["extracted_data"] == {}
    assert calls == []

    upload = client.post(
        "/api/public/application/files",
        headers={"X-CSRF-Token": public_session["csrf_token"], "X-AI-Processing-Consent": "true", "X-External-AI-Consent": "true"},
        data={"kind": "DOCUMENT", "document_type": "ID"},
        files={"upload": ("identity.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["ai_status"] == "PROCESSING"
    uploaded_file_id = upload.json()["id"]
    failed_file = next(item for item in client.get("/api/public/application/files").json() if item["id"] == uploaded_file_id)
    assert failed_file["ai_status"] == "FAILED"
    assert failed_file["extracted_data"] == {}

    retry_without_consent = client.post(
        f"/api/public/application/files/{uploaded_file_id}/extract",
        headers={"X-CSRF-Token": public_session["csrf_token"]},
    )
    assert retry_without_consent.status_code == 403

    retried = client.post(
        f"/api/public/application/files/{uploaded_file_id}/extract",
        headers={"X-CSRF-Token": public_session["csrf_token"], "X-AI-Processing-Consent": "true", "X-External-AI-Consent": "true"},
    )
    assert retried.status_code == 202, retried.text
    completed_file = next(item for item in client.get("/api/public/application/files").json() if item["id"] == uploaded_file_id)
    assert completed_file["ai_status"] == "COMPLETED"
    assert completed_file["extracted_data"] == {
        "last_name_latin": "KARIMOVA",
        "first_name_latin": "ISMOIL",
        "middle_name_latin": "ANVAR QIZI",
        "birth_date": "2005-04-11",
    }
    assert calls[0]["model"] == "test/private-vision-model"
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "provider" not in calls[0]
    assert "ocr_text" not in completed_file

    public_files = client.get("/api/public/application/files")
    assert public_files.status_code == 200
    assert all("ocr_text" not in file for file in public_files.json())
    public_document = next(file for file in public_files.json() if file["kind"] == "DOCUMENT")
    assert public_document["extracted_data"] == completed_file["extracted_data"]

    application = database.scalar(select(StudentApplication))
    database.refresh(application)
    assert application.ai_processing_consented_at is not None
    attachment = database.scalar(select(ApplicationFile).where(ApplicationFile.application_id == application.id, ApplicationFile.kind == "DOCUMENT", ApplicationFile.deleted_at.is_(None)))
    admin = _headers(admin_token)
    detail = client.get(f"/api/admissions/applications/{application.id}", headers=admin)
    assert detail.status_code == 200, detail.text
    staff_file = next(file for file in detail.json()["files"] if file["id"] == str(attachment.id))
    assert staff_file["ai_status"] == "COMPLETED"
    assert staff_file["extracted_data"] == completed_file["extracted_data"]

    removed = client.delete(f"/api/admissions/applications/{application.id}/files/{attachment.id}", headers=admin)
    assert removed.status_code == 204
    database.refresh(attachment)
    assert attachment.extracted_data == {}
    assert attachment.ai_status == "DELETED"


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
    room = client.post("/api/rooms", headers=admin, json={"number": "202", "dormitory_id": dormitory["id"], "floor": 2, "capacity": 1, "price": "250000"})
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
