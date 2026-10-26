from datetime import date
from datetime import timedelta
from zoneinfo import ZoneInfo
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from app.models import BillingPeriod
from app.scheduled_jobs import run_daily_jobs


def test_payment_retries_return_the_original_receipt_without_double_counting(client, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    resident = client.post("/api/residents", headers=headers, json={
        "first_name": "Sardor", "last_name": "Aliyev", "payment_period_days": 30,
        "agreed_price": "500000", "billing_start": today.isoformat(),
        "billing_end": (today + timedelta(days=30)).isoformat(),
    }).json()
    payload = {"resident_id": resident["id"], "amount": "150000", "payment_date": today.isoformat(), "method": "CASH"}
    request_headers = {**headers, "Idempotency-Key": "payment-retry-0001"}
    first = client.post("/api/payments", headers=request_headers, json=payload)
    retry = client.post("/api/payments", headers=request_headers, json=payload)
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]
    assert client.get(f"/api/residents/{resident['id']}/payments", headers=headers).json().__len__() == 1

    conflict = client.post("/api/payments", headers=request_headers, json={**payload, "amount": "200000"})
    assert conflict.status_code == 409


def test_get_requests_do_not_create_billing_periods_but_daily_job_does(client, database, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    person = client.post("/api/residents", headers=headers, json={
        "first_name": "Nodira", "last_name": "Islomova", "payment_period_days": 10,
        "agreed_price": "200000", "billing_start": (today - timedelta(days=10)).isoformat(),
        "billing_end": today.isoformat(),
    }).json()
    period = database.get(BillingPeriod, UUID(person["billing_period_id"]))
    period.status = "PAID"
    period.end_date = today - timedelta(days=1)
    database.commit()

    client.get("/api/residents", headers=headers)
    client.get(f"/api/residents/{person['id']}", headers=headers)
    client.get("/api/dashboard", headers=headers)
    client.get("/api/notifications", headers=headers)
    client.get("/api/reports/residents.csv", headers=headers)
    assert database.scalar(select(func.count(BillingPeriod.id)).where(BillingPeriod.resident_id == UUID(person["id"]))) == 1

    run_daily_jobs(database, today)
    assert database.scalar(select(func.count(BillingPeriod.id)).where(BillingPeriod.resident_id == UUID(person["id"]))) == 2
