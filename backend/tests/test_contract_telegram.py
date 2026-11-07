from sqlalchemy import select

from app.models import AuditEvent, StudentApplication, User
from tests.test_admissions import SUBMIT, _fill_application, _headers, _workflow


def test_contract_must_be_read_and_signed_before_submit(client, database, operator_token, admin_token):
    _, _, _, _, session = _workflow(client, operator_token, admin_token)
    _fill_application(client, session)
    csrf = {"X-CSRF-Token": session["csrf_token"]}
    contract = client.get("/api/public/application/contract")
    assert contract.status_code == 200
    assert contract.json()["title"].startswith("HOSTELDA YASHASH")
    for body in (
        {"consent": True},
        {"consent": True, "contract_accepted": True, "signature_name": "Aziza"},
        {"consent": True, "contract_accepted": False, "signature_name": "Aziza Karimova"},
    ):
        assert client.post("/api/public/application/submit", headers=csrf, json=body).status_code == 422
    assert client.post("/api/public/application/submit", headers=csrf, json=SUBMIT).status_code == 200
    application = database.scalar(select(StudentApplication))
    assert application.contract_accepted_at and application.contract_signed_via == "WEB"
    assert application.contract_signature_name == "Aziza Karimova"
    staff_view = client.get(f"/api/admissions/applications/{application.id}/contract", headers=_headers(admin_token))
    assert staff_view.status_code == 200
    assert staff_view.json()["signed"] is True and staff_view.json()["signed_hash_matches"] is True
    assert client.get(f"/api/admissions/applications/{application.id}/contract").status_code == 401


def test_investor_account_is_aggregate_only_and_role_can_change(client, operator_token):
    headers = _headers(operator_token)
    created = client.post("/api/users", headers=headers, json={
        "email": "inv@example.com", "full_name": "Investor One", "password": "investor-pass-123", "role": "INVESTOR",
    })
    assert created.status_code == 201 and created.json()["role"] == "INVESTOR"
    login = client.post("/api/auth/login", json={"email": "inv@example.com", "password": "investor-pass-123"}).json()
    inv = _headers(login["access_token"])
    assert client.get("/api/investor/summary", headers=inv).status_code == 200
    assert client.get("/api/residents", headers=inv).status_code == 403
    assert client.get("/api/payments", headers=inv).status_code == 403
    changed = client.patch(f"/api/users/{created.json()['id']}", headers=headers, json={"role": "ADMIN"})
    assert changed.json()["role"] == "ADMIN"
    assert database_role(client, headers, "inv@example.com") == "ADMIN"


def test_operator_contract_signature_is_private_and_audited(client, database, operator_token, admin_token):
    operator = _headers(operator_token)
    saved = client.put("/api/settings/operator-contract-signature", headers=operator, json={"full_name": "Dilshod Operatorov"})
    assert saved.status_code == 200 and saved.json()["full_name"] == "Dilshod Operatorov"
    assert client.get("/api/settings/operator-contract-signature", headers=operator).json()["full_name"] == "Dilshod Operatorov"
    assert client.put("/api/settings/operator-contract-signature", headers=_headers(admin_token), json={"full_name": "Admin O‘zgartirdi"}).status_code == 403
    created = client.post("/api/users", headers=operator, json={
        "email": "contract-investor@example.com", "full_name": "Contract Investor", "password": "investor-pass-123", "role": "INVESTOR",
    })
    token = client.post("/api/auth/login", json={"email": "contract-investor@example.com", "password": "investor-pass-123"}).json()["access_token"]
    assert client.put("/api/settings/operator-contract-signature", headers=_headers(token), json={"full_name": "Investor O‘zgartirdi"}).status_code == 403
    assert database.scalar(select(AuditEvent).where(AuditEvent.action == "OPERATOR_CONTRACT_SIGNATURE_UPDATED")) is not None


def test_operator_downloads_assigned_contract_pdf_and_others_cannot(client, database, operator_token, admin_token):
    operator = _headers(operator_token)
    assert client.put("/api/settings/operator-contract-signature", headers=operator, json={"full_name": "Dilshod Operatorov"}).status_code == 200
    dormitory, _, _, _, session = _workflow(client, operator_token, admin_token)
    _fill_application(client, session)
    assert client.post("/api/public/application/submit", headers={"X-CSRF-Token": session["csrf_token"]}, json=SUBMIT).status_code == 200
    application = database.scalar(select(StudentApplication))
    room = client.post("/api/rooms", headers=operator, json={"number": "501", "dormitory_id": dormitory["id"], "floor": 5, "capacity": 1, "price": "300000"})
    assert room.status_code == 201
    approved = client.post(f"/api/admissions/applications/{application.id}/approve", headers=operator, json={
        "reason": "Hujjatlar tekshirildi.", "room_id": room.json()["id"], "move_in": "2026-11-01", "agreed_price": "300000", "payment_period_days": 30,
    })
    assert approved.status_code == 200
    database.refresh(application)
    assert application.contract_snapshot and application.contract_operator_signature_name == "Dilshod Operatorov"
    assert client.put("/api/settings/operator-contract-signature", headers=operator, json={"full_name": "Yangi Operator"}).status_code == 200
    viewed = client.get(f"/api/admissions/applications/{application.id}/contract", headers=operator)
    assert viewed.status_code == 200 and viewed.json()["operator_signature_name"] == "Dilshod Operatorov"
    pdf = client.get(f"/api/admissions/applications/{application.id}/contract.pdf", headers=operator)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert "attachment" in pdf.headers["content-disposition"] and f"shartnoma-{application.id}" in pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF")
    assert database.scalar(select(AuditEvent).where(AuditEvent.action == "APPLICATION_CONTRACT_DOWNLOADED", AuditEvent.entity_id == application.id)) is not None
    other = User(email="other-operator@example.com", full_name="Other Operator", password_hash="not-used", role="OPERATOR", is_active=True)
    database.add(other)
    database.commit()
    # Reuse the known-good hash routine through the login endpoint rather than exposing a second staff route.
    from app.security import hash_password
    other.password_hash = hash_password("other-operator-password")
    database.commit()
    other_token = client.post("/api/auth/login", json={"email": "other-operator@example.com", "password": "other-operator-password"}).json()["access_token"]
    assert client.get(f"/api/admissions/applications/{application.id}/contract.pdf", headers=_headers(other_token)).status_code == 403
    assert client.get(f"/api/admissions/applications/{application.id}/contract.pdf").status_code == 401
    assert client.get(f"/api/admissions/applications/{application.id}/contract.pdf", headers=_headers(admin_token)).status_code == 200


def database_role(client, headers, email):
    return next(item["role"] for item in client.get("/api/users", headers=headers).json() if item["email"] == email)


def test_bootstrap_creates_optional_admin_and_investor_once(database, monkeypatch):
    from app.bootstrap import bootstrap
    from app.config import settings

    monkeypatch.setattr(settings, "initial_admin_email", "boot-admin@example.com")
    monkeypatch.setattr(settings, "initial_admin_password", "boot-admin-pass-1")
    monkeypatch.setattr(settings, "initial_investor_email", "boot-inv@example.com")
    monkeypatch.setattr(settings, "initial_investor_password", "boot-investor-pass-1")
    bootstrap(database)
    bootstrap(database)
    roles = {u.email: u.role for u in database.scalars(select(User)).all()}
    assert roles["boot-admin@example.com"] == "ADMIN" and roles["boot-inv@example.com"] == "INVESTOR"
    assert len([e for e in roles if e.startswith("boot-")]) == 2
