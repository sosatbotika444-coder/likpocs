from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from app.api import spreadsheet_safe, xlsx_file


def tday():
    return datetime.now(ZoneInfo("Asia/Tashkent")).date()


def test_report_formats_return_exports_with_uzbek_headers(client, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    today = tday()
    person = client.post("/api/residents", headers=headers, json={
        "first_name": "Malika", "last_name": "Saidova", "payment_period_days": 21,
        "agreed_price": "350000", "billing_start": today.isoformat(),
    }).json()
    client.post("/api/payments", headers=headers, json={
        "resident_id": person["id"], "amount": "50000", "payment_date": today.isoformat(), "method": "CASH",
    })

    csv_file = client.get("/api/reports/residents.csv", headers=headers)
    xlsx_file = client.get("/api/reports/payments.xlsx", headers=headers)
    pdf_file = client.get("/api/reports/payments.pdf", headers=headers)

    assert csv_file.status_code == xlsx_file.status_code == pdf_file.status_code == 200
    assert "Ism" in csv_file.content.decode("utf-8-sig")
    assert xlsx_file.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert xlsx_file.content[:2] == b"PK"
    assert pdf_file.content.startswith(b"%PDF")


def test_spreadsheet_exports_neutralize_formula_like_text_but_keep_numeric_values():
    payload = xlsx_file(["Izoh", "Summa"], [["=HYPERLINK(\"https://example.invalid\")", -125]], "Xavfsizlik")
    sheet = load_workbook(BytesIO(payload), data_only=False).active
    assert sheet["A2"].value.startswith("'=HYPERLINK")
    assert sheet["A2"].data_type == "s"
    assert sheet["B2"].value == -125
    assert spreadsheet_safe("  @SUM(A1:A2)") == "'  @SUM(A1:A2)"
