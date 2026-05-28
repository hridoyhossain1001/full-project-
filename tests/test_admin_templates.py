import os
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

# Set up environment variables required by the app before importing it
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["ADMIN_API_KEY"] = "test-admin-api-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENCRYPTION_KEY"] = "ZFhnf1szwemka8kBbH9jPTC7oKBRTEv0EqWt1J8AD0M="

from app.main import app
from app.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.client import Client
from app.models.client_session import ClientSession
from app.models.client_user import ClientUser
from app.security import encrypt_token
from app.services.auth_service import hash_password, hash_session_token

# Setup clean async database engine for testing
engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestingSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="module", autouse=True)
async def cleanup_database_engine():
    yield
    await engine.dispose()


# ─── ADMIN PORTAL TESTS ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_admin_dashboard_render():
    client = TestClient(app)
    response = client.get(
        "/api/v1/admin",
        auth=("admin", "test-admin-password")
    )
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Buykori" in response.text
    assert "Client Management" not in response.text


@pytest.mark.anyio
async def test_admin_clients_render():
    client = TestClient(app)
    response = client.get(
        "/api/v1/admin/clients",
        auth=("admin", "test-admin-password")
    )
    assert response.status_code == 200
    assert "Client Management" in response.text
    assert "Total Clients" in response.text


@pytest.mark.anyio
async def test_admin_logs_render():
    client = TestClient(app)
    response = client.get(
        "/api/v1/admin/logs",
        auth=("admin", "test-admin-password")
    )
    assert response.status_code == 200
    assert "API Event Logs" in response.text
    assert "Recent Events" in response.text


@pytest.mark.anyio
async def test_admin_settings_render():
    client = TestClient(app)
    response = client.get(
        "/api/v1/admin/settings",
        auth=("admin", "test-admin-password")
    )
    assert response.status_code == 200
    assert "System Settings" in response.text
    assert "System Information" in response.text


@pytest.mark.anyio
async def test_admin_client_instructions_render():
    async with TestingSessionLocal() as session:
        test_client = Client(
            name="Test Store Instructions",
            api_key="instr-api-key",
            portal_key="instr-portal-key",
            pixel_id="123456",
            access_token=encrypt_token("fb-token"),
            is_active=True,
        )
        session.add(test_client)
        await session.commit()
        await session.refresh(test_client)
        client_id = test_client.id

    client = TestClient(app)
    response = client.get(
        f"/api/v1/admin/client/{client_id}/instructions",
        auth=("admin", "test-admin-password")
    )
    assert response.status_code == 200
    assert "Setup Guide" in response.text
    assert 'data-secret="instr-api-key"' in response.text
    assert "GTM Server Container" in response.text


@pytest.mark.anyio
async def test_admin_client_edit_render():
    async with TestingSessionLocal() as session:
        test_client = Client(
            name="Test Store Edit",
            api_key="edit-api-key",
            portal_key="edit-portal-key",
            pixel_id="789012",
            access_token=encrypt_token("fb-token"),
            is_active=True,
        )
        session.add(test_client)
        await session.commit()
        await session.refresh(test_client)
        client_id = test_client.id

    client = TestClient(app)
    response = client.get(
        f"/api/v1/admin/client/{client_id}/edit",
        auth=("admin", "test-admin-password")
    )
    assert response.status_code == 200
    assert "Edit Client" in response.text
    assert "Test Store Edit" in response.text


# ─── CLIENT PORTAL TESTS ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_client_login_page_render():
    client = TestClient(app)
    response = client.get("/client")
    assert response.status_code == 200
    assert "Buykori AdSync" in response.text
    assert "Login" in response.text
    assert "Signup" in response.text
    assert "Portal Login Key" not in response.text


@pytest.mark.anyio
async def test_client_login_failed_page_render():
    client = TestClient(app)
    response = client.post(
        "/client/login",
        data={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert "Access Denied" in response.text
    assert "Invalid email or password" in response.text


@pytest.mark.anyio
async def test_client_dashboard_unauthorized_redirect():
    client = TestClient(app)
    response = client.get("/client/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/client"


@pytest.mark.anyio
async def test_client_dashboard_render():
    # Insert a test client to verify dashboard rendering
    async with TestingSessionLocal() as session:
        test_client = Client(
            name="Test Store",
            api_key="test-api-key",
            portal_key="test-portal-key",
            pixel_id="1234567890",
            access_token=encrypt_token("test-fb-token"),
            is_active=True,
            deferred_purchase=True
        )
        session.add(test_client)
        await session.commit()
        await session.refresh(test_client)
        client_id = test_client.id

    # Generate valid session cookie value
    session_value = f"client:{client_id}:test-portal-key"
    encrypted_session = encrypt_token(session_value)

    client = TestClient(app)
    client.cookies.set("client_session", encrypted_session)

    response = client.get("/client/dashboard")
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert '/static/client-portal/assets/' in response.text


@pytest.mark.anyio
async def test_client_dashboard_render_with_email_session():
    async with TestingSessionLocal() as session:
        test_client = Client(
            name="Email Session Store",
            api_key="email-session-api-key",
            portal_key=None,
            pixel_id="1234567890",
            access_token=encrypt_token("test-fb-token"),
            is_active=True,
        )
        session.add(test_client)
        await session.flush()
        user = ClientUser(
            client_id=test_client.id,
            email="owner@email-session.test",
            password_hash=hash_password("correct-password"),
            full_name="Owner User",
            role="owner",
            is_active=True,
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        token = "email-session-token"
        session.add(ClientSession(
            user_id=user.id,
            client_id=test_client.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        ))
        await session.commit()

    client = TestClient(app)
    client.cookies.set("buykori_client_session", encrypt_token(token))

    response = client.get("/client/dashboard")
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


@pytest.mark.anyio
async def test_static_mounts_do_not_expose_client_portal_root():
    mount_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/static" not in mount_paths
    assert "/static/css" in mount_paths
    assert "/static/client-portal/assets" in mount_paths

    client = TestClient(app)
    assert client.get("/static/client-portal/server.cjs").status_code == 404
    assert client.get("/static/client-portal/server.cjs.map").status_code == 404
    assert client.get("/static/client-portal/index.html").status_code == 404
    assert client.get("/static/css/portal.css").status_code == 200


@pytest.mark.anyio
async def test_client_signup_form_creates_email_user():
    client = TestClient(app)
    response = client.post(
        "/client/signup",
        data={
            "full_name": "New Owner",
            "business_name": "New Signup Store",
            "email": "new-owner@example.com",
            "password": "strong-password-123",
            "domain": "example.com",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/client/dashboard"

    async with TestingSessionLocal() as session:
        user_r = await session.execute(
            select(ClientUser).where(ClientUser.email == "new-owner@example.com")
        )
        user = user_r.scalar_one_or_none()
        assert user is not None


@pytest.mark.anyio
async def test_marketing_home_render():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Buykori AdSync" in response.text
    assert "Optimize Your" in response.text


# ─── PLUGIN DOWNLOAD TESTS ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_plugin_download_standard_serves_static_zip(tmp_path, monkeypatch):
    test_zip = tmp_path / "buykori-adsync.zip"
    test_zip.write_bytes(b"dummy-zip-content")

    from app.routers import plugin
    monkeypatch.setattr(plugin, "PLUGIN_ZIP_PATH", test_zip)

    client = TestClient(app)
    response = client.get("/api/v1/plugin/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content == b"dummy-zip-content"


@pytest.mark.anyio
async def test_plugin_download_with_query_param(tmp_path, monkeypatch):
    import io
    async with TestingSessionLocal() as session:
        test_client = Client(
            name="Test Store Query",
            api_key="query-api-key",
            portal_key="query-portal-key",
            pixel_id="11111111",
            access_token=encrypt_token("fb-token"),
            is_active=True,
        )
        session.add(test_client)
        await session.commit()

    mock_src = tmp_path / "wordpress-plugin" / "buykori-adsync"
    mock_src.mkdir(parents=True)
    php_file = mock_src / "buykori-adsync.php"
    php_file.write_text("<?php\n// 'api_key' => '',\n// 'gateway_url' => BUYKORIGW_DEFAULT_GATEWAY_URL,")

    from app.routers import plugin
    monkeypatch.setattr(plugin, "PLUGIN_SOURCE_DIR", mock_src)

    client = TestClient(app)
    response = client.get("/api/v1/plugin/download?api_key=query-api-key")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    import zipfile
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        patched = zf.read("buykori-adsync/buykori-adsync.php").decode("utf-8")
        assert "query-api-key" in patched


@pytest.mark.anyio
async def test_plugin_download_with_session_cookie(tmp_path, monkeypatch):
    import io
    async with TestingSessionLocal() as session:
        test_client = Client(
            name="Test Store Cookie",
            api_key="cookie-api-key",
            portal_key="cookie-portal-key",
            pixel_id="22222222",
            access_token=encrypt_token("fb-token"),
            is_active=True,
        )
        session.add(test_client)
        await session.commit()
        await session.refresh(test_client)
        client_id = test_client.id

    mock_src = tmp_path / "wordpress-plugin" / "buykori-adsync"
    mock_src.mkdir(parents=True)
    php_file = mock_src / "buykori-adsync.php"
    php_file.write_text("<?php\n// 'api_key' => '',\n// 'gateway_url' => BUYKORIGW_DEFAULT_GATEWAY_URL,")

    from app.routers import plugin
    monkeypatch.setattr(plugin, "PLUGIN_SOURCE_DIR", mock_src)

    session_value = f"client:{client_id}:cookie-portal-key"
    encrypted_session = encrypt_token(session_value)

    client = TestClient(app)
    client.cookies.set("client_session", encrypted_session)

    response = client.get("/api/v1/plugin/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    import zipfile
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        patched = zf.read("buykori-adsync/buykori-adsync.php").decode("utf-8")
        assert "cookie-api-key" in patched

# ─── ADMIN API LOGIN TESTS ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_admin_api_login_success():
    client = TestClient(app)
    response = client.post(
        "/api/v1/admin/api/login",
        json={"username": "admin", "password": "test-admin-password"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    # Verify it is a valid JWT
    jwt_token = data["admin_api_key"]
    from app.routers.admin_api import decode_jwt
    payload = decode_jwt(jwt_token, "test-admin-api-key")
    assert payload["sub"] == "admin"

@pytest.mark.anyio
async def test_admin_api_login_failed_wrong_credentials():
    client = TestClient(app)
    response = client.post(
        "/api/v1/admin/api/login",
        json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "Incorrect username or password" in response.json()["detail"]


@pytest.mark.anyio
async def test_admin_api_events_endpoint():
    from app.models.event_log import EventLog
    
    async with TestingSessionLocal() as session:
        client1 = Client(
            name="Client A",
            api_key="client1-api-key",
            portal_key="client1-portal-key",
            pixel_id="111111",
            access_token=encrypt_token("token-a"),
            is_active=True,
        )
        client2 = Client(
            name="Client B",
            api_key="client2-api-key",
            portal_key="client2-portal-key",
            pixel_id="222222",
            access_token=encrypt_token("token-b"),
            is_active=True,
        )
        session.add(client1)
        session.add(client2)
        await session.commit()
        await session.refresh(client1)
        await session.refresh(client2)
        
        log1 = EventLog(
            client_id=client1.id,
            event_name="GA4:Purchase",
            status="success",
            ip_address="192.168.1.5",
            event_id="evt_001",
            event_count=1,
            value=1200.0,
            currency="BDT",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        log2 = EventLog(
            client_id=client1.id,
            event_name="TikTok:AddToCart",
            status="failed",
            error_message="Invalid token structure",
            ip_address="192.168.1.10",
            event_id="evt_002",
            event_count=1,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        log3 = EventLog(
            client_id=client2.id,
            event_name="Facebook:PageView",
            status="success",
            ip_address="10.0.0.1",
            event_id="evt_003",
            event_count=1,
            created_at=datetime.now(timezone.utc)
        )
        session.add(log1)
        session.add(log2)
        session.add(log3)
        await session.commit()
        
    client = TestClient(app)
    headers = {"X-Admin-API-Key": "test-admin-api-key"}
    
    # 1. Test fetching all events
    response = client.get("/api/v1/admin/api/events", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["totalCount"] == 3
    assert len(data["events"]) == 3
    
    # 2. Test pagination limit
    response = client.get("/api/v1/admin/api/events?limit=2", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["totalCount"] == 3
    assert len(data["events"]) == 2
    
    # 3. Test client ID filtering
    response = client.get(f"/api/v1/admin/api/events?client_id={client1.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["totalCount"] == 2
    assert all(e["client_id"] == client1.id for e in data["events"])
    
    # 4. Test platform filtering
    response = client.get("/api/v1/admin/api/events?platform=GA4", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["totalCount"] == 1
    assert data["events"][0]["platform"] == "GA4"
    
    # 5. Test status filtering
    response = client.get("/api/v1/admin/api/events?status=failed", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["totalCount"] == 1
    assert data["events"][0]["status"] == "Failed"
    
    # 6. Test search filter
    response = client.get("/api/v1/admin/api/events?search=token", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["totalCount"] == 1
    assert "token" in data["events"][0]["responseBody"]["error"]["message"].lower()


@pytest.mark.anyio
async def test_admin_api_delete_client_with_users_and_sessions():
    async with TestingSessionLocal() as session:
        # Create a client
        client_to_del = Client(
            name="To Delete Client API",
            api_key="del-api-key",
            portal_key="del-portal-key",
            pixel_id="111111",
            access_token=encrypt_token("token-del"),
            is_active=True,
        )
        session.add(client_to_del)
        await session.flush()
        
        # Create a user
        user = ClientUser(
            client_id=client_to_del.id,
            email="del-user@example.com",
            password_hash=hash_password("password"),
            full_name="User to Delete",
            role="owner",
            is_active=True,
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        
        # Create a session
        sess = ClientSession(
            user_id=user.id,
            client_id=client_to_del.id,
            token_hash=hash_session_token("some-session-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(sess)
        await session.commit()
        await session.refresh(client_to_del)
        client_id = client_to_del.id

    client = TestClient(app)
    headers = {"X-Admin-API-Key": "test-admin-api-key"}
    
    # Execute delete request
    response = client.delete(f"/api/v1/admin/api/clients/{client_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify database is clean
    async with TestingSessionLocal() as session:
        client_check = await session.get(Client, client_id)
        assert client_check is None
        
        user_check = (await session.execute(select(ClientUser).where(ClientUser.client_id == client_id))).scalars().all()
        assert len(user_check) == 0

        sess_check = (await session.execute(select(ClientSession).where(ClientSession.client_id == client_id))).scalars().all()
        assert len(sess_check) == 0


@pytest.mark.anyio
async def test_admin_views_delete_client_with_users_and_sessions():
    async with TestingSessionLocal() as session:
        # Create a client
        client_to_del = Client(
            name="To Delete Client View",
            api_key="del-view-key",
            portal_key="del-view-portal",
            pixel_id="222222",
            access_token=encrypt_token("token-del-view"),
            is_active=True,
        )
        session.add(client_to_del)
        await session.flush()
        
        # Create a user
        user = ClientUser(
            client_id=client_to_del.id,
            email="del-user-view@example.com",
            password_hash=hash_password("password"),
            full_name="User to Delete View",
            role="owner",
            is_active=True,
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        
        # Create a session
        sess = ClientSession(
            user_id=user.id,
            client_id=client_to_del.id,
            token_hash=hash_session_token("some-view-session-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(sess)
        await session.commit()
        await session.refresh(client_to_del)
        client_id = client_to_del.id

    client = TestClient(app)
    # Generate CSRF token
    from app.routers.admin_views import create_admin_csrf_token
    csrf_token = create_admin_csrf_token("admin")
    
    # Execute delete POST request
    response = client.post(
        f"/api/v1/admin/client/{client_id}/delete",
        auth=("admin", "test-admin-password"),
        data={"csrf_token": csrf_token},
        follow_redirects=False
    )
    assert response.status_code == 303  # redirect status
    assert "deleted" in response.headers["location"].lower()

    # Verify database is clean
    async with TestingSessionLocal() as session:
        client_check = await session.get(Client, client_id)
        assert client_check is None
        
        user_check = (await session.execute(select(ClientUser).where(ClientUser.client_id == client_id))).scalars().all()
        assert len(user_check) == 0

        sess_check = (await session.execute(select(ClientSession).where(ClientSession.client_id == client_id))).scalars().all()
        assert len(sess_check) == 0
