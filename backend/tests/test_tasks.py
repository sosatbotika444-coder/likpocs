from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.models import AuditEvent, StaffTask, User
from app.services import today_local


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user_id(database, email):
    return str(database.scalar(select(User.id).where(User.email == email)))


def test_task_board_requires_staff_session(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/tasks", json={"title": "Test"}).status_code == 401


def test_operator_assigns_task_and_assignee_is_notified_and_audited(client, database, operator_token, admin_token):
    admin_id = _user_id(database, "admin@example.com")
    due = (today_local() - timedelta(days=1)).isoformat()
    created = client.post("/api/tasks", headers=_auth(operator_token), json={
        "title": "  3-qavat dushini tuzatish ", "priority": "URGENT", "assignee_id": admin_id, "due_date": due,
    })
    assert created.status_code == 201
    task = created.json()
    assert task["title"] == "3-qavat dushini tuzatish"
    assert task["status"] == "TODO" and task["assignee_name"] == "Test Admin"
    assert task["is_overdue"] is True

    admin_alerts = client.get("/api/notifications", headers=_auth(admin_token)).json()
    assert any(item["kind"] == "TASK" and item["entity_id"] == task["id"] for item in admin_alerts)
    assert not any(item["kind"] == "TASK" for item in client.get("/api/notifications", headers=_auth(operator_token)).json())
    assert database.scalar(select(AuditEvent).where(AuditEvent.action == "TASK_CREATED")) is not None

    summary = client.get("/api/tasks/summary", headers=_auth(admin_token)).json()
    assert summary["todo"] == 1 and summary["overdue"] == 1 and summary["mine_open"] == 1


def test_admin_cannot_assign_others_or_edit_foreign_tasks(client, database, operator_token, admin_token):
    operator_id = _user_id(database, "operator@example.com")
    admin_id = _user_id(database, "admin@example.com")
    forbidden = client.post("/api/tasks", headers=_auth(admin_token), json={"title": "Boshqaga", "assignee_id": operator_id})
    assert forbidden.status_code == 403

    own = client.post("/api/tasks", headers=_auth(admin_token), json={"title": "O‘zimga", "assignee_id": admin_id})
    assert own.status_code == 201

    foreign = client.post("/api/tasks", headers=_auth(operator_token), json={"title": "Operator vazifasi"}).json()
    assert foreign["can_edit"] is True
    admin_view = next(item for item in client.get("/api/tasks", headers=_auth(admin_token)).json() if item["id"] == foreign["id"])
    assert admin_view["can_edit"] is False
    assert client.patch(f"/api/tasks/{foreign['id']}", headers=_auth(admin_token), json={"status": "DONE"}).status_code == 403
    # Admin may not reassign their own task to someone else either.
    assert client.patch(f"/api/tasks/{own.json()['id']}", headers=_auth(admin_token), json={"assignee_id": operator_id}).status_code == 403

    picker = client.get("/api/tasks/assignees", headers=_auth(admin_token)).json()
    assert [item["id"] for item in picker] == [admin_id]
    assert "email" not in picker[0]
    assert len(client.get("/api/tasks/assignees", headers=_auth(operator_token)).json()) == 2


def test_status_flow_records_completion_notifies_creator_and_never_deletes(client, database, operator_token, admin_token):
    admin_id = _user_id(database, "admin@example.com")
    task = client.post("/api/tasks", headers=_auth(operator_token), json={"title": "Kir yuvish", "assignee_id": admin_id}).json()

    moved = client.patch(f"/api/tasks/{task['id']}", headers=_auth(admin_token), json={"status": "IN_PROGRESS"})
    assert moved.status_code == 200 and moved.json()["completed_at"] is None
    done = client.patch(f"/api/tasks/{task['id']}", headers=_auth(admin_token), json={"status": "DONE"}).json()
    assert done["completed_at"] is not None
    operator_alerts = client.get("/api/notifications", headers=_auth(operator_token)).json()
    assert any(item["kind"] == "TASK_DONE" and item["entity_id"] == task["id"] for item in operator_alerts)

    reopened = client.patch(f"/api/tasks/{task['id']}", headers=_auth(admin_token), json={"status": "TODO"}).json()
    assert reopened["completed_at"] is None

    assert client.patch(f"/api/tasks/{task['id']}", headers=_auth(operator_token), json={"status": "CANCELLED"}).status_code == 200
    assert all(item["id"] != task["id"] for item in client.get("/api/tasks", headers=_auth(operator_token)).json())
    with_cancelled = client.get("/api/tasks", headers=_auth(operator_token), params={"include_cancelled": True}).json()
    assert any(item["id"] == task["id"] for item in with_cancelled)
    assert client.delete(f"/api/tasks/{task['id']}", headers=_auth(operator_token)).status_code == 405
    assert database.get(StaffTask, UUID(task["id"])) is not None

    updates = database.scalars(select(AuditEvent).where(AuditEvent.action == "TASK_UPDATED").order_by(AuditEvent.created_at)).all()
    assert len(updates) == 4
    assert updates[0].details["changes"]["status"] == {"old": "TODO", "new": "IN_PROGRESS"}


def test_task_validation_ordering_and_filters(client, operator_token):
    headers = _auth(operator_token)
    assert client.post("/api/tasks", headers=headers, json={"title": "x"}).status_code == 422
    assert client.post("/api/tasks", headers=headers, json={"title": "Yaxshi", "priority": "MEGA"}).status_code == 422
    missing_room = {"title": "Xona", "room_id": "00000000-0000-0000-0000-000000000001"}
    assert client.post("/api/tasks", headers=headers, json=missing_room).status_code == 422
    client.post("/api/tasks", headers=headers, json={"title": "Past ish", "priority": "LOW"})
    client.post("/api/tasks", headers=headers, json={"title": "Shoshilinch ish", "priority": "URGENT"})
    ordered = client.get("/api/tasks", headers=headers).json()
    assert [item["priority"] for item in ordered] == ["URGENT", "LOW"]
    assert [item["title"] for item in client.get("/api/tasks", headers=headers, params={"q": "past"}).json()] == ["Past ish"]
    assert client.get("/api/tasks", headers=headers, params={"scope": "mine"}).json() == []
    task_id = ordered[0]["id"]
    assert client.patch(f"/api/tasks/{task_id}", headers=headers, json={"title": None}).status_code == 422
    assert client.patch(f"/api/tasks/{task_id}", headers=headers, json={"status": "ARCHIVED"}).status_code == 422
    # Unassigned tasks must not create notifications for anyone.
    assert client.get("/api/notifications", headers=headers).json() == []
