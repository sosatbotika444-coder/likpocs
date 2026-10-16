from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    session = TestingSession()
    operator = User(email="operator@example.com", full_name="Test Operator", password_hash=hash_password("test-operator-password"), role="OPERATOR", is_active=True, is_primary=True)
    admin = User(email="admin@example.com", full_name="Test Admin", password_hash=hash_password("test-admin-password"), role="ADMIN", is_active=True, is_primary=False)
    session.add_all([operator, admin])
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(database):
    def override_get_db():
        yield database

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def operator_token(client):
    response = client.post("/api/auth/login", json={"email": "operator@example.com", "password": "test-operator-password"})
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def admin_token(client):
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"})
    assert response.status_code == 200
    return response.json()["access_token"]
