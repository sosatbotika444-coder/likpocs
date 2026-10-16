from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_due_reminders_are_persisted_and_acknowledged(client, operator_token):
    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    headers = {"Authorization": f"Bearer {operator_token}"}
    person = client.post("/api/residents", headers=headers, json={
        "first_name": "Zuhra", "last_name": "Rahimova", "payment_period_days": 30,
        "agreed_price": "300000", "billing_start": (today - timedelta(days=31)).isoformat(),
    }).json()

    reminders = client.get("/api/notifications", headers=headers)
    assert reminders.status_code == 200
    assert any(item["entity_id"] == person["id"] and item["kind"] == "OVERDUE" for item in reminders.json())
    assert client.post("/api/notifications/read-all", headers=headers).status_code == 204
    assert client.get("/api/notifications", headers=headers).json() == []
