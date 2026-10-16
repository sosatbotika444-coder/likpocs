from datetime import date, timedelta
from zoneinfo import ZoneInfo
from datetime import datetime


def tday():
    return datetime.now(ZoneInfo("Asia/Tashkent")).date()


def room(client, token, capacity=2):
    response = client.post("/api/rooms", headers={"Authorization": f"Bearer {token}"}, json={"number": "101", "capacity": capacity, "floor": 1})
    assert response.status_code == 201, response.text
    return response.json()


def resident(client, token, billing=True, period_days=45):
    payload = {"first_name": "Dilnoza", "last_name": "Karimova"}
    if billing:
        payload.update({"payment_period_days": period_days, "agreed_price": "600000.00"})
        payload.update({"billing_start": tday().isoformat(), "billing_end": (tday() + timedelta(days=period_days)).isoformat()})
    response = client.post("/api/residents", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_arbitrary_period_partial_payment_then_full_payment_stays_paid_until_due(client, operator_token):
    room(client, operator_token)
    person = resident(client, operator_token, period_days=45)
    assert person["payment_period_days"] == 45
    assert person["balance"] == "600000.00"
    assert person["billing_status"] == "CURRENT"

    partial = client.post("/api/payments", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "resident_id": person["id"], "amount": "150000", "payment_date": tday().isoformat(), "method": "CASH",
    })
    assert partial.status_code == 201, partial.text
    after_partial = client.get(f"/api/residents/{person['id']}", headers={"Authorization": f"Bearer {operator_token}"}).json()
    assert after_partial["balance"] == "450000.00"

    remainder = client.post("/api/payments", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "resident_id": person["id"], "amount": "450000", "payment_date": tday().isoformat(), "method": "CLICK",
    })
    assert remainder.status_code == 201, remainder.text
    current = client.get(f"/api/residents/{person['id']}", headers={"Authorization": f"Bearer {operator_token}"}).json()
    assert current["billing_period_id"] == person["billing_period_id"]
    assert current["billing_status"] == "PAID"
    assert current["balance"] == "0.00"
    assert len(current["billing_history"]) == 1


def test_payment_without_a_valid_billing_period_is_rejected(client, operator_token):
    person = resident(client, operator_token, billing=False)
    response = client.post("/api/payments", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "resident_id": person["id"], "amount": "1000", "payment_date": tday().isoformat(), "method": "CASH",
    })
    assert response.status_code == 409
    assert "davr" in response.json()["detail"].lower()


def test_billing_can_be_configured_later_without_manual_dates(client, operator_token):
    person = resident(client, operator_token, billing=False)
    response = client.patch(f"/api/residents/{person['id']}", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "payment_period_days": 14, "agreed_price": "250000",
    })
    assert response.status_code == 200, response.text
    today = tday()
    assert response.json()["billing_start"] == today.isoformat()
    assert response.json()["billing_end"] == (today + timedelta(days=14)).isoformat()
    assert response.json()["balance"] == "250000.00"


def test_explicit_end_date_applies_to_the_current_cycle_and_period_days_roll_forward(client, operator_token):
    start = tday()
    explicit_end = start + timedelta(days=9)
    response = client.post("/api/residents", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "first_name": "Aziza", "last_name": "Saidova", "payment_period_days": 30,
        "agreed_price": "180000", "billing_start": start.isoformat(), "billing_end": explicit_end.isoformat(),
    })
    assert response.status_code == 201, response.text
    person = response.json()
    assert person["billing_end"] == explicit_end.isoformat()
    details = client.get(f"/api/residents/{person['id']}", headers={"Authorization": f"Bearer {operator_token}"}).json()
    assert details["billing_history"][0]["period_days"] == 9
    payment = client.post("/api/payments", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "resident_id": person["id"], "amount": "180000", "payment_date": tday().isoformat(), "method": "CASH",
    })
    assert payment.status_code == 201, payment.text
    renewed = client.get(f"/api/residents/{person['id']}", headers={"Authorization": f"Bearer {operator_token}"}).json()
    assert renewed["billing_period_id"] == person["billing_period_id"]
    assert renewed["billing_status"] == "PAID"
    assert renewed["balance"] == "0.00"


def test_overpayment_cannot_be_silently_applied(client, operator_token):
    person = resident(client, operator_token)
    response = client.post("/api/payments", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "resident_id": person["id"], "amount": "600001", "payment_date": tday().isoformat(), "method": "CASH",
    })
    assert response.status_code == 422


def test_extension_is_separate_from_payment_and_preserves_old_dates(client, operator_token):
    person = resident(client, operator_token)
    old_end = date.fromisoformat(person["billing_end"])
    response = client.post(f"/api/residents/{person['id']}/extend", headers={"Authorization": f"Bearer {operator_token}"}, json={"days": 17, "reason": "Kelishuv bo‘yicha"})
    assert response.status_code == 200, response.text
    assert response.json()["end_date"] == (old_end + timedelta(days=17)).isoformat()
    detail = client.get(f"/api/residents/{person['id']}", headers={"Authorization": f"Bearer {operator_token}"}).json()
    assert detail["billing_history"][0]["end_date"] == (old_end + timedelta(days=17)).isoformat()
    assert detail["billing_history"][0]["balance"] == "600000.00"
    assert detail["changes"][0]["old_end_date"] == old_end.isoformat()
    assert detail["changes"][0]["new_end_date"] == (old_end + timedelta(days=17)).isoformat()


def test_invalid_billing_dates_are_rejected(client, operator_token):
    response = client.post("/api/residents", headers={"Authorization": f"Bearer {operator_token}"}, json={
        "first_name": "Test", "last_name": "Resident", "payment_period_days": 7, "agreed_price": "100000",
        "billing_start": (tday() + timedelta(days=5)).isoformat(), "billing_end": tday().isoformat(),
    })
    assert response.status_code == 422
