from datetime import date


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_expenses_are_idempotent_audited_and_voided_without_deletion(client, operator_token, admin_token):
    operator = auth(operator_token)
    payload = {
        "expense_date": date.today().isoformat(), "category": "UTILITIES",
        "description": "Elektr energiyasi", "amount": "125000.50", "method": "BANK", "reference": "INV-24",
    }
    headers = {**operator, "Idempotency-Key": "expense-test-0001"}
    first = client.post("/api/expenses", headers=headers, json=payload)
    replay = client.post("/api/expenses", headers=headers, json=payload)
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["amount"] == "125000.50"

    conflict = client.post("/api/expenses", headers=headers, json={**payload, "amount": "125001"})
    assert conflict.status_code == 409
    assert client.get("/api/expenses", headers=operator).json()["total"] == 1

    admin_void = client.post(f"/api/expenses/{first.json()['id']}/void", headers=auth(admin_token), json={"reason": "Xato qayd"})
    assert admin_void.status_code == 403
    voided = client.post(f"/api/expenses/{first.json()['id']}/void", headers=operator, json={"reason": "Hisob-faktura bekor qilindi"})
    assert voided.status_code == 200
    assert voided.json()["void_reason"] == "Hisob-faktura bekor qilindi"
    assert client.get("/api/expenses", headers=operator).json()["total"] == 0
    assert client.get("/api/expenses", headers=operator, params={"include_voided": True}).json()["total"] == 1
    events = client.get("/api/audit", headers=operator).json()["items"]
    assert any(item["action"] == "EXPENSE_RECORDED" for item in events)
    assert any(item["action"] == "EXPENSE_VOIDED" for item in events)


def test_dashboard_and_expense_report_only_include_active_expenses(client, operator_token):
    headers = auth(operator_token)
    client.post("/api/expenses", headers={**headers, "Idempotency-Key": "expense-report-0001"}, json={
        "expense_date": date.today().isoformat(), "category": "REPAIR",
        "description": "Xonani ta'mirlash", "amount": "90000", "method": "CASH",
    })
    dashboard = client.get("/api/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["actual_expenses"] == "90000.00"
    assert dashboard.json()["net_cash_flow"] == "-90000.00"
    report = client.get("/api/reports/expenses.csv", headers=headers)
    xlsx = client.get("/api/reports/expenses.xlsx", headers=headers)
    pdf = client.get("/api/reports/expenses.pdf", headers=headers)
    assert report.status_code == 200
    assert xlsx.status_code == pdf.status_code == 200
    assert xlsx.content[:2] == b"PK"
    assert pdf.content.startswith(b"%PDF")
    assert "90000.00" in report.content.decode("utf-8-sig")


def test_expense_input_rejects_future_dates_and_nonpositive_amount(client, operator_token):
    headers = {**auth(operator_token), "Idempotency-Key": "expense-invalid-0001"}
    base = {"category": "OTHER", "description": "Sinov", "amount": "100", "method": "CASH"}
    future = client.post("/api/expenses", headers=headers, json={**base, "expense_date": "2999-01-01"})
    zero = client.post("/api/expenses", headers={**headers, "Idempotency-Key": "expense-invalid-0002"}, json={**base, "expense_date": date.today().isoformat(), "amount": "0"})
    assert future.status_code == 422
    assert zero.status_code == 422
