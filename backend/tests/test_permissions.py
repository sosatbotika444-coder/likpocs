from datetime import datetime
from zoneinfo import ZoneInfo


def tday():
    return datetime.now(ZoneInfo("Asia/Tashkent")).date().isoformat()


def test_admin_cannot_read_audit_or_manage_users(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/api/audit", headers=headers).status_code == 403
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post("/api/users", headers=headers, json={"email": "new@example.com", "full_name": "New Admin", "password": "secure-admin-pass"}).status_code == 403


def test_only_operator_can_adjust_historical_payments(client, operator_token, admin_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    person = client.post("/api/residents", headers=headers, json={
        "first_name": "A", "last_name": "Resident", "payment_period_days": 30, "agreed_price": "500000",
        "billing_start": tday(),
    }).json()
    payment = client.post("/api/payments", headers=headers, json={
        "resident_id": person["id"], "amount": "100000", "payment_date": tday(), "method": "CASH",
    }).json()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    adjustment = client.post(f"/api/payments/{payment['id']}/adjustments", headers=admin_headers, json={"amount_delta": "-1000", "reason": "Xato kiritildi"})
    assert adjustment.status_code == 403
    assert client.patch(f"/api/payments/{payment['id']}", headers=admin_headers, json={"amount": "1"}).status_code == 404
    assert client.delete(f"/api/payments/{payment['id']}", headers=admin_headers).status_code == 404
    operator_adjustment = client.post(f"/api/payments/{payment['id']}/adjustments", headers=headers, json={"amount_delta": "-1000", "reason": "To‘lovdagi xatoni tuzatish"})
    assert operator_adjustment.status_code == 201
    history = client.get(f"/api/residents/{person['id']}/payments", headers=headers).json()
    assert len(history) == 1
    assert history[0]["amount"] == "100000.00"
    assert history[0]["net_amount"] == "99000.00"


def test_admin_cannot_extend_billing_when_not_authorized(client, operator_token, admin_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    person = client.post("/api/residents", headers=headers, json={
        "first_name": "A", "last_name": "Resident", "payment_period_days": 30, "agreed_price": "500000", "billing_start": tday(),
    }).json()
    response = client.post(f"/api/residents/{person['id']}/extend", headers={"Authorization": f"Bearer {admin_token}"}, json={"days": 5})
    assert response.status_code == 403


def test_admin_cannot_assign_operator_role(client, operator_token):
    response = client.post("/api/users", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "email": "promote@example.com", "full_name": "Not Operator", "password": "secure-admin-password", "role": "OPERATOR",
    })
    assert response.status_code == 422


def test_room_capacity_cannot_be_exceeded(client, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    room = client.post("/api/rooms", headers=headers, json={"number": "101", "capacity": 1}).json()
    first = client.post("/api/residents", headers=headers, json={"first_name": "One", "last_name": "Resident", "room_id": room["id"]})
    assert first.status_code == 201
    second = client.post("/api/residents", headers=headers, json={"first_name": "Two", "last_name": "Resident", "room_id": room["id"]})
    assert second.status_code == 409
