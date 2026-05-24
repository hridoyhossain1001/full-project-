import os
import pytest
from fastapi.testclient import TestClient

# Set up environment variables required by the app before importing it
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["ADMIN_API_KEY"] = "test-admin-api-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENCRYPTION_KEY"] = "ZFhnf1szwemka8kBbH9jPTC7oKBRTEv0EqWt1J8AD0M="

from app.main import app
from app.database import get_db
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.client import Client
from app.security import encrypt_token

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
    assert "Sign in to your Client Portal" in response.text


@pytest.mark.anyio
async def test_client_login_failed_page_render():
    client = TestClient(app)
    response = client.post("/client/login", data={"api_key": "invalid-key"})
    assert response.status_code == 401
    assert "Access Denied" in response.text
    assert "Invalid or inactive Portal Login Key" in response.text


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
