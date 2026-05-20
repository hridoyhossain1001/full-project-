import os
import html
import secrets
import logging
import hashlib
import hmac
import time
from urllib.parse import urlencode
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Form, Request, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sql_delete, select, update, func
from pydantic import BaseModel
from app.database import get_db
from app.models.client import Client
from app.models.audit_log import AuditLog
from app.models.event_dedup import EventDedup
from app.models.event_log import EventLog
from app.models.event_outbox import EventOutbox
from app.models.failed_event import FailedEvent
from app.models.pending_event import PendingEvent
from app.models.usage_counter import UsageCounter
from app.security import encrypt_token
from app.services.webhook_service import _webhook_url_allowed
from app.limiter import limiter
from app.dependencies import clear_client_cache

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBasic()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise RuntimeError("⛔ ADMIN_PASSWORD environment variable is required!")

CSRF_MAX_AGE_SECONDS = 60 * 60


class AdminClientCreate(BaseModel):
    name: str
    pixel_id: str
    access_token: str
    test_event_code: str | None = None
    domain: str | None = None
    tiktok_pixel_id: str | None = None
    tiktok_access_token: str | None = None
    tiktok_test_event_code: str | None = None
    ga4_measurement_id: str | None = None
    ga4_api_secret: str | None = None
    enable_facebook: bool = True
    enable_tiktok: bool = True
    enable_ga4: bool = True
    deferred_purchase: bool = False
    webhook_url: str | None = None


class AdminClientUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    monthly_limit: int | None = None
    is_active: bool | None = None
    enable_facebook: bool | None = None
    enable_tiktok: bool | None = None
    enable_ga4: bool | None = None
    deferred_purchase: bool | None = None
    webhook_url: str | None = None


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    is_user_ok = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    is_pass_ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def verify_admin_api_key(x_admin_api_key: str = Header("", alias="X-Admin-API-Key")) -> str:
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin API key is not configured")
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, admin_key):
        raise HTTPException(status_code=403, detail="Admin access required")
    return "admin-api"


def create_admin_csrf_token(username: str) -> str:
    nonce = secrets.token_urlsafe(24)
    issued_at = str(int(time.time()))
    payload = f"{username}:{issued_at}:{nonce}"
    signature = hmac.new(
        ADMIN_PASSWORD.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{issued_at}:{nonce}:{signature}"


def verify_admin_csrf_token(token: str, username: str) -> None:
    try:
        issued_at, nonce, signature = token.split(":", 2)
        issued_ts = int(issued_at)
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    if time.time() - issued_ts > CSRF_MAX_AGE_SECONDS:
        raise HTTPException(status_code=403, detail="Expired CSRF token")

    payload = f"{username}:{issued_at}:{nonce}"
    expected = hmac.new(
        ADMIN_PASSWORD.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def normalize_domain_input(domain: str | None) -> str | None:
    if not domain or not domain.strip():
        return None

    raw = domain.strip().lower()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or raw).strip().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def display_domain_url(domain: str | None) -> str:
    clean_domain = normalize_domain_input(domain)
    if not clean_domain:
        return ""
    return f"https://www.{clean_domain}"


# ─── HTML TEMPLATES ─────────────────────────────────────────────────────────



STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  
  :root {
    color-scheme: dark;
    --bg-main: #0B1120;
    --bg-sidebar: #0F172A;
    --bg-card: #1E293B;
    --bg-card-hover: #273449;
    --border: rgba(148, 163, 184, 0.15);
    --border-bright: rgba(148, 163, 184, 0.25);
    
    --primary: #ff8b45;
    --primary-hover: #ff7a2f;
    --primary-glow: rgba(255, 139, 69, 0.28);
    --primary-soft: rgba(255, 139, 69, 0.12);
    
    --text-main: #F8FAFC;
    --text-muted: #94A3B8;
    --text-subtle: #64748B;
    
    --success: #10B981;
    --success-bg: rgba(16, 185, 129, 0.15);
    --warning: #F59E0B;
    --warning-bg: rgba(245, 158, 11, 0.15);
    --danger: #EF4444;
    --danger-bg: rgba(239, 68, 68, 0.15);
    
    --sidebar-width: 250px;
    --header-height: 70px;
    --radius: 12px;
    --radius-sm: 8px;
  }
  
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg-main); color: var(--text-main); min-height: 100vh; display: flex; overflow-x: hidden; font-size: 13px; font-family: 'Inter', system-ui, sans-serif; }
  button, input, select, textarea { font: inherit; }
  button { cursor: pointer; }
  svg { flex-shrink: 0; }
  a { text-decoration: none; color: inherit; }

  /* ── Sidebar */
  .sidebar {
    width: var(--sidebar-width); background: var(--bg-sidebar);
    border-right: 1px solid var(--border); display: flex; flex-direction: column;
    position: fixed; height: 100vh; left: 0; top: 0; z-index: 50;
  }
  .brand { padding: 24px 20px; display: flex; align-items: center; gap: 12px; }
  .brand-logo {
    width: 28px; height: 28px; background: var(--primary);
    border-radius: 6px; display: flex; align-items: center; justify-content: center;
    color: #111827; font-weight: 800; font-size: 16px;
    box-shadow: 0 6px 18px var(--primary-glow);
  }
  .brand-text { font-size: 16px; font-weight: 700; color: #E2E8F0; letter-spacing: -0.3px; }
  .brand-text span { color: var(--primary); }
  
  .nav-menu { padding: 12px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
  .nav-item {
    display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 14px;
    color: var(--text-muted); background: transparent; border: 0; border-radius: var(--radius-sm);
    font-weight: 600; font-size: 13.5px; text-align: left; text-decoration: none;
    transition: all 0.18s;
  }
  .nav-item svg { width: 18px; height: 18px; stroke-width: 2; opacity: 0.8; }
  .nav-item:hover { background: rgba(255,255,255,0.05); color: #E2E8F0; }
  .nav-item.active { background: rgba(255,139,69,0.16); color: var(--primary); border-radius: var(--radius-sm); }
  .nav-item.active svg { opacity: 1; }
  
  .pro-plan-box {
    margin: 16px; padding: 16px; border-radius: var(--radius);
    border: 1px solid rgba(255,139,69,0.25); background: rgba(255,139,69,0.06);
  }
  .pro-plan-title { display: flex; align-items: center; gap: 6px; color: var(--primary); font-weight: 700; font-size: 12px; margin-bottom: 12px; }
  .progress-bar-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.08); border-radius: 99px; overflow: hidden; margin-bottom: 6px; }
  .progress-bar-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-hover)); border-radius: 99px; }
  .pro-plan-stats { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); }
  .sidebar-bottom { padding: 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }

  /* ── Main Content */
  .main-wrapper { flex: 1; margin-left: var(--sidebar-width); display: flex; flex-direction: column; min-height: 100vh; }
  .topbar {
    height: var(--header-height); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between; padding: 0 32px;
    background: var(--bg-main); position: sticky; top: 0; z-index: 20;
  }
  .search-box {
    display: flex; align-items: center; gap: 10px; background: #0F172A;
    border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 8px 16px; width: 320px;
  }
  .search-box svg { width: 16px; height: 16px; color: var(--text-muted); }
  .search-box input { background: none; border: none; outline: none; color: white; width: 100%; font-size: 13px; }
  .search-box .kbd { background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 10px; color: var(--text-muted); font-family: monospace; }
  .topbar-right { display: flex; align-items: center; gap: 20px; }
  .env-badge {
    display: flex; align-items: center; gap: 6px; padding: 4px 10px;
    background: rgba(16,185,129,0.1); border-radius: 99px; border: 1px solid rgba(16,185,129,0.2);
    font-size: 11px; font-weight: 700; color: #10B981; letter-spacing: 0.5px;
  }
  .env-badge::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: #10B981; }
  .icon-btn { position: relative; background: none; border: none; color: var(--text-muted); display: flex; align-items: center; justify-content: center; }
  .icon-btn svg { width: 20px; height: 20px; }
  .icon-btn:hover { color: white; }
  .badge-dot { position: absolute; top: -2px; right: -2px; min-width: 14px; height: 14px; background: #EF4444; border-radius: 50%; border: 2px solid var(--bg-main); display: flex; align-items: center; justify-content: center; font-size: 8px; color: white; font-weight: bold; }
  .user-profile { display: flex; align-items: center; gap: 10px; border-left: 1px solid var(--border); padding-left: 20px; }
  .avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--primary); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; color: #111827; }
  .user-info { display: flex; flex-direction: column; }
  .user-info .name { font-size: 13px; font-weight: 700; color: white; }
  .user-info .email { font-size: 11px; color: var(--text-muted); }
  .content { padding: 32px; }

  /* ── Page Header */
  .page-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 24px; gap: 20px; }
  .page-title { font-size: 24px; font-weight: 800; color: white; margin-bottom: 4px; letter-spacing: -0.5px; }
  .page-sub { color: var(--text-muted); font-size: 13px; }
  .header-actions { display: flex; gap: 12px; flex-wrap: wrap; }

  /* ── Buttons */
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 700; border: none; text-decoration: none; }
  .btn-outline { background: transparent; border: 1px solid var(--border-bright); color: #E2E8F0; }
  .btn-outline:hover { background: rgba(255,255,255,0.05); }
  .btn-primary { background: var(--primary); color: #111827; border: 1px solid rgba(255,139,69,0.45); }
  .btn-primary:hover { background: var(--primary-hover); }
  .btn-danger { background: rgba(239,68,68,0.12); color: #FCA5A5; border: 1px solid rgba(239,68,68,0.28); }
  .btn-danger:hover { background: rgba(239,68,68,0.22); }
  .btn-sm { padding: 4px 10px; font-size: 12px; border-radius: 4px; }

  /* ── Alerts */
  .alert { display: flex; gap: 12px; align-items: flex-start; padding: 12px 16px; border-radius: var(--radius-sm); margin-bottom: 20px; font-size: 13px; }
  .alert-success { background: var(--success-bg); border: 1px solid rgba(16,185,129,0.25); color: #34d399; }
  .alert-error { background: var(--danger-bg); border: 1px solid rgba(239,68,68,0.25); color: #f87171; }

  /* ── Metrics Grid */
  .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 24px; }
  .metric-card { background: var(--bg-card); border-radius: var(--radius); border: 1px solid var(--border); padding: 20px; display: flex; flex-direction: column; min-width: 0; }
  .metric-card:hover { border-color: var(--border-bright); }
  .metric-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
  .m-icon { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .m-icon svg { width: 14px; height: 14px; }
  .m-title { font-size: 12.5px; font-weight: 700; color: #E2E8F0; }
  .metric-value { font-size: 32px; font-weight: 800; color: white; letter-spacing: -1px; margin-bottom: 8px; line-height: 1; overflow-wrap: anywhere; }
  .trend { font-size: 12px; display: flex; align-items: center; gap: 6px; color: var(--text-subtle); }
  .trend span { font-weight: 700; display: inline-flex; align-items: center; gap: 2px; }
  .trend-up span { color: var(--success); }
  .trend-down span { color: var(--danger); }

  /* ── Cards */
  .card { background: var(--bg-card); border-radius: var(--radius); border: 1px solid var(--border); overflow: hidden; margin-bottom: 24px; }
  .card-header { padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); gap: 16px; }
  .card-title { font-size: 15px; font-weight: 700; color: white; }
  .card-tools { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

  /* ── Table */
  .table-wrap, .table-responsive { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 12px 20px; font-size: 12px; font-weight: 700; color: var(--text-muted); border-bottom: 1px solid var(--border); }
  td { padding: 16px 20px; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.03); color: #E2E8F0; vertical-align: middle; }
  tr:hover td { background: rgba(255,255,255,0.02); }
  tr:last-child td { border-bottom: none; }
  .code-text { font-family: monospace; font-size: 12px; color: var(--text-muted); }
  .client-name { font-weight: 700; color: white; display: flex; align-items: center; gap: 8px; }
  .client-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; font-family: monospace; }
  .domain-link { display: inline-flex; align-items: center; gap: 4px; color: #E2E8F0; text-decoration: none; }
  .domain-link:hover { text-decoration: underline; }

  /* ── Status Badges */
  .status-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; }
  .status-badge::before { content: ''; width: 6px; height: 6px; border-radius: 50%; }
  .status-healthy { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16,185,129,0.2); }
  .status-healthy::before { background: var(--success); }
  .status-warning { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(245,158,11,0.2); }
  .status-warning::before { background: var(--warning); }
  .status-degraded, .status-critical, .status-inactive { background: var(--danger-bg); color: #F87171; border: 1px solid rgba(239,68,68,0.2); }
  .status-degraded::before, .status-critical::before, .status-inactive::before { background: var(--danger); }
  .badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }
  .badge-healthy { background: var(--success-bg); color: var(--success); }
  .badge-degraded { background: var(--danger-bg); color: #f87171; }
  .integration-status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; white-space: nowrap; }
  .integration-status svg { width: 16px; height: 16px; }
  .dot { width: 6px; height: 6px; border-radius: 50%; }
  .dot-active { background: var(--success); }
  .dot-inactive { background: var(--danger); }
  .action-btn { background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: white; width: 32px; height: 32px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; }
  .action-btn:hover { background: rgba(255,255,255,0.1); }
  .grid-layout { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
  .layout-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }

  /* ── Activity Stream */
  .stream-item { display: flex; align-items: flex-start; gap: 12px; padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,0.03); }
  .stream-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
  .stream-dot.info { background: var(--primary); box-shadow: 0 0 8px var(--primary-glow); }
  .stream-dot.success { background: var(--success); box-shadow: 0 0 8px rgba(16,185,129,0.6); }
  .stream-dot.warning { background: var(--warning); box-shadow: 0 0 8px rgba(245,158,11,0.6); }
  .stream-content { flex: 1; min-width: 0; }
  .stream-title { font-size: 13px; font-weight: 700; color: #E2E8F0; margin-bottom: 2px; }
  .stream-desc { font-size: 12px; color: var(--text-muted); overflow-wrap: anywhere; }
  .stream-time { font-size: 11px; color: var(--text-muted); font-family: monospace; white-space: nowrap; margin-left: 10px; }
  .alert-rank { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 99px; margin-right: 10px; }
  .alert-high { color: #EF4444; border: 1px solid rgba(239,68,68,0.3); }
  .alert-medium { color: #F59E0B; border: 1px solid rgba(245,158,11,0.3); }
  .alert-low { color: var(--primary); border: 1px solid rgba(255,139,69,0.3); }
  .view-all { font-size: 12px; color: var(--primary); text-decoration: none; font-weight: 700; background: none; border: 0; }
  .view-all:hover { text-decoration: underline; }

  /* ── Connection Footer */
  .connection-footer { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 20px; display: flex; gap: 22px; flex-wrap: wrap; }
  .conn-item { display: flex; align-items: center; gap: 12px; }
  .conn-icon { width: 32px; height: 32px; border-radius: 6px; display: grid; place-items: center; font-weight: 800; }
  .conn-info { display: flex; flex-direction: column; }
  .conn-title { font-size: 12px; font-weight: 700; color: white; }
  .conn-status { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 4px; }
  .conn-status::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--success); }

  /* ── Forms */
  .form-group { margin-bottom: 16px; }
  .form-group label { display: block; margin-bottom: 7px; color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
  .form-group input, .form-group select, .form-group textarea {
    width: 100%; background: #0F172A; color: var(--text-main);
    border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 11px 12px; outline: none;
  }
  .form-group input:focus, .form-group select:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(255,139,69,0.12); }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .hint { margin-top: 5px; font-size: 11px; color: var(--text-muted); line-height: 1.5; }

  /* ── API Key / Credentials */
  .api-key-cell {
    display: flex; align-items: center; gap: 8px;
    background: rgba(0,0,0,0.3); border: 1px solid var(--border);
    border-radius: 6px; padding: 8px 12px; font-family: monospace; font-size: 13px; color: #94A3B8;
  }
  .copy-icon { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; padding: 0; }
  .copy-icon:hover { color: var(--primary); }

  /* ── Tabs */
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 20px; border-bottom: 2px solid rgba(255,255,255,0.05); }
  .tab-btn {
    padding: 10px 16px; background: none; border: none; border-bottom: 2px solid transparent;
    color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer;
    margin-bottom: -2px; transition: all 0.15s;
  }
  .tab-btn:hover { color: #E2E8F0; }
  .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .instr-box {
    background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px; padding: 16px; font-family: monospace; font-size: 13px;
    color: #93c5fd; white-space: pre-wrap; word-break: break-all; margin: 0; overflow-x: auto;
  }

  /* ── Utilities */
  .text-success { color: var(--success); }
  .text-danger { color: var(--danger); }
  .bg-blue { background: rgba(59,130,246,0.15); color: #60A5FA; border: 1px solid rgba(59,130,246,0.25); }
  .bg-purple { background: rgba(139,92,246,0.15); color: #A78BFA; border: 1px solid rgba(139,92,246,0.25); }
  .bg-red { background: rgba(239,68,68,0.15); color: #F87171; border: 1px solid rgba(239,68,68,0.25); }
  .bg-indigo { background: rgba(99,102,241,0.15); color: #818CF8; border: 1px solid rgba(99,102,241,0.25); }
  .empty { padding: 36px 20px; text-align: center; color: var(--text-muted); }
  .notice { margin-top: 12px; color: var(--success); min-height: 18px; }

  /* ── Responsive */
  @media (max-width: 1180px) {
    .metrics-grid { grid-template-columns: repeat(2, 1fr); }
    .grid-layout { grid-template-columns: 1fr; }
    .layout-grid { grid-template-columns: 1fr; }
  }
  @media (max-width: 820px) {
    body { display: block; }
    .sidebar { position: static; width: 100%; height: auto; }
    .main-wrapper { margin-left: 0; }
    .topbar { height: auto; padding: 16px; flex-wrap: wrap; gap: 14px; }
    .search-box { width: 100%; }
    .topbar-right { flex-wrap: wrap; gap: 12px; }
    .content { padding: 18px; }
    .page-header { align-items: flex-start; flex-direction: column; }
    .metrics-grid, .form-grid, .layout-grid { grid-template-columns: 1fr; }
    .grid-layout { grid-template-columns: 1fr; }
    th, td { padding: 10px 12px; }
  }
</style>
"""



def base_html(title: str, body: str, msg: str = "", msg_type: str = "success", active_page: str = "dashboard") -> str:
    alert_html = ""
    safe_title = html.escape(title, quote=True)
    if msg:
        safe_msg = html.escape(msg)
        safe_type = "error" if msg_type == "error" else "success"
        alert_html = f'<div class="alert alert-{safe_type}"><span>{safe_msg}</span></div>'

    def nav_active(page):
        return "active" if active_page == page else ""
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title} — Buykori AdSync</title>
  {STYLE}
</head>
<body>

  <!-- Sidebar -->
  <aside class="sidebar" id="admin-sidebar">
    <div class="brand">
      <div class="brand-logo">B</div>
      <div class="brand-text">Buykori <span>AdSync</span></div>
    </div>
    
    <div class="nav-menu">
      <a href="/api/v1/admin" class="nav-item {nav_active("dashboard")}">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>
        Overview
      </a>
      <a href="/api/v1/admin/clients" class="nav-item {nav_active("clients")}">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
        Clients
      </a>
      <a href="#" class="nav-item">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
        Events
      </a>
      <a href="#" class="nav-item">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
        Integrations
      </a>
      <a href="/api/v1/admin/logs" class="nav-item {nav_active("logs")}">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        API Logs
      </a>
      <a href="#" class="nav-item">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>
        Health Doctor
      </a>
      <a href="/api/v1/admin/settings" class="nav-item {nav_active("settings")}">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        Settings
      </a>
    </div>
    
    <div class="pro-plan-box">
      <div class="pro-plan-title">
        <span>👑</span> Plan: Pro
      </div>
      <div class="pro-plan-stats" style="margin-bottom:6px;">
        <span>Events Used</span>
        <span style="color:white;font-weight:600;">1.2M / 2M</span>
      </div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: 60%;"></div></div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:8px;">Reset on Jun 1, 2026</div>
    </div>

    <div class="sidebar-bottom">
      <a href="#" class="nav-item">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
        Support <svg style="width:12px;height:12px;margin-left:auto;opacity:0.5;" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
      </a>
      <a href="#" class="nav-item">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" /></svg>
        Collapse
      </a>
    </div>
  </aside>

  <!-- Main Content Area -->
  <div class="main-wrapper">
    <!-- Topbar -->
    <header class="topbar">
      <div class="search-box">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        <input type="text" placeholder="Search clients, events, IPs...">
        <span class="kbd">⌘K</span>
      </div>
      
      <div class="topbar-right">
        <div class="env-badge">PRODUCTION</div>
        <button class="icon-btn">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
          <div class="badge-dot">6</div>
        </button>
        <button class="icon-btn">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </button>
        
        <div class="user-profile">
          <div class="avatar">AH</div>
          <div class="user-info">
            <span class="name">Admin Panel</span>
            <span class="email">sysop@buykori.app</span>
          </div>
        </div>
      </div>
    </header>

    <!-- Page Content -->
    <main class="content">
      {alert_html}
      {body}
    </main>
  </div>
  
  <script>
    function copyText(id) {{
      var t = document.getElementById(id);
      var value = t.dataset.secret || t.innerText || t.value || '';
      navigator.clipboard.writeText(value.trim()).then(function() {{
        showToast('Copied!');
      }});
    }}

    function revealSecret(id) {{
      var el = document.getElementById(id);
      if (!el) return;
      if (el.dataset.hidden === '1') {{
        el.innerText = el.dataset.secret || '';
        el.dataset.hidden = '0';
      }} else {{
        el.innerText = el.dataset.masked || '';
        el.dataset.hidden = '1';
      }}
    }}

    function showToast(msg) {{
      var t = document.getElementById('bk-toast');
      if (!t) {{
        t = document.createElement('div');
        t.id = 'bk-toast';
        t.style.cssText = 'position:fixed;bottom:24px;right:24px;background:#ff8b45;color:#111;font-weight:700;font-size:13px;padding:10px 20px;border-radius:8px;z-index:9999;box-shadow:0 8px 24px rgba(255,139,69,0.4);transition:opacity .3s;pointer-events:none;';
        document.body.appendChild(t);
      }}
      t.textContent = msg;
      t.style.opacity = '1';
      clearTimeout(t._tid);
      t._tid = setTimeout(function() {{ t.style.opacity = '0'; }}, 1800);
    }}
  </script>
</body>
</html>'''


def admin_redirect(msg: str, msg_type: str = "success") -> RedirectResponse:
    query = urlencode({"msg": msg, "msg_type": msg_type})
    return RedirectResponse(url=f"/api/v1/admin?{query}", status_code=303)


def mask_secret(value: str | None, prefix: int = 6, suffix: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= prefix + suffix:
        return "•" * len(value)
    return f"{value[:prefix]}{'•' * 12}{value[-suffix:]}"


def request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def log_admin_action(
    db: AsyncSession,
    request: Request,
    actor: str,
    action: str,
    client_id: int | None = None,
    details: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            client_id=client_id,
            ip_address=request_ip(request),
            details=details,
        )
    )


# ─── JSON API ROUTES FOR SPLIT ADMIN FRONTEND ────────────────────────────────

def client_to_api_dict(client: Client, event_total: int = 0, last_event_at=None) -> dict:
    return {
        "id": client.id,
        "name": client.name,
        "domain": client.domain,
        "display_domain": display_domain_url(client.domain),
        "is_active": bool(client.is_active),
        "api_key": client.api_key,
        "public_key": getattr(client, "public_key", None),
        "portal_key": getattr(client, "portal_key", None),
        "pixel_id": client.pixel_id,
        "test_event_code": client.test_event_code,
        "monthly_limit": getattr(client, "monthly_limit", None),
        "rate_limit": client.rate_limit,
        "daily_quota": client.daily_quota,
        "enable_facebook": getattr(client, "enable_facebook", True),
        "enable_tiktok": getattr(client, "enable_tiktok", True),
        "enable_ga4": getattr(client, "enable_ga4", True),
        "deferred_purchase": getattr(client, "deferred_purchase", False),
        "webhook_url": getattr(client, "webhook_url", None),
        "tiktok_pixel_id": getattr(client, "tiktok_pixel_id", None),
        "ga4_measurement_id": getattr(client, "ga4_measurement_id", None),
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "event_total": int(event_total or 0),
        "last_event_at": last_event_at.isoformat() if last_event_at else None,
    }


def validate_webhook_url_or_400(webhook_url: str | None) -> str | None:
    clean_webhook_url = webhook_url.strip() if webhook_url and webhook_url.strip() else None
    if not clean_webhook_url:
        return None
    parsed_webhook = urlparse(clean_webhook_url)
    if parsed_webhook.scheme not in ("https", "http") or not parsed_webhook.netloc:
        raise HTTPException(status_code=400, detail="Webhook URL must be a valid http(s) URL.")
    if not _webhook_url_allowed(clean_webhook_url):
        raise HTTPException(status_code=400, detail="Webhook URL is not allowed.")
    return clean_webhook_url


@router.get("/admin/api/summary")
async def admin_api_summary(
    _: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    clients_r = await db.execute(select(Client))
    clients = clients_r.scalars().all()
    events_r = await db.execute(select(func.coalesce(func.sum(EventLog.event_count), 0)))
    total_events = int(events_r.scalar() or 0)
    failed_r = await db.execute(
        select(func.coalesce(func.sum(EventLog.event_count), 0)).where(EventLog.status == "failed")
    )
    failed_events = int(failed_r.scalar() or 0)
    return {
        "status": "success",
        "total_clients": len(clients),
        "active_clients": sum(1 for c in clients if c.is_active),
        "inactive_clients": sum(1 for c in clients if not c.is_active),
        "total_events": total_events,
        "failed_events": failed_events,
    }


@router.get("/admin/api/clients")
async def admin_api_clients(
    _: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(
            Client,
            func.coalesce(func.sum(EventLog.event_count), 0).label("event_total"),
            func.max(EventLog.created_at).label("last_event_at"),
        )
        .outerjoin(EventLog, EventLog.client_id == Client.id)
        .group_by(Client.id)
        .order_by(Client.created_at.desc())
    )
    return {
        "status": "success",
        "clients": [client_to_api_dict(client, event_total, last_event_at) for client, event_total, last_event_at in rows],
    }


@router.post("/admin/api/clients")
async def admin_api_create_client(
    payload: AdminClientCreate,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    pixel_id = payload.pixel_id.strip()
    access_token = payload.access_token.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Client name must be 1-100 characters.")
    if not pixel_id.isdigit():
        raise HTTPException(status_code=400, detail="Pixel ID must be numeric.")
    if len(access_token) < 10:
        raise HTTPException(status_code=400, detail="Access token must be at least 10 characters.")

    client = Client(
        name=name,
        pixel_id=pixel_id,
        access_token=encrypt_token(access_token),
        test_event_code=payload.test_event_code.strip() if payload.test_event_code else None,
        domain=normalize_domain_input(payload.domain),
        api_key=secrets.token_urlsafe(32),
        public_key=secrets.token_urlsafe(24),
        portal_key=secrets.token_urlsafe(24),
        enable_facebook=payload.enable_facebook,
        enable_tiktok=payload.enable_tiktok,
        enable_ga4=payload.enable_ga4,
        tiktok_pixel_id=payload.tiktok_pixel_id.strip() if payload.tiktok_pixel_id else None,
        tiktok_access_token=encrypt_token(payload.tiktok_access_token.strip()) if payload.tiktok_access_token else None,
        tiktok_test_event_code=payload.tiktok_test_event_code.strip() if payload.tiktok_test_event_code else None,
        ga4_measurement_id=payload.ga4_measurement_id.strip() if payload.ga4_measurement_id else None,
        ga4_api_secret=encrypt_token(payload.ga4_api_secret.strip()) if payload.ga4_api_secret else None,
        deferred_purchase=payload.deferred_purchase,
        webhook_url=validate_webhook_url_or_400(payload.webhook_url),
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    await log_admin_action(db, request, actor, "client.api_added", client.id, f"Client {name} added from admin frontend")
    await db.commit()
    return {"status": "success", "client": client_to_api_dict(client)}


@router.patch("/admin/api/clients/{client_id}")
async def admin_api_update_client(
    client_id: int,
    payload: AdminClientUpdate,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    old_api_key = client.api_key
    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name or len(clean_name) > 100:
            raise HTTPException(status_code=400, detail="Client name must be 1-100 characters.")
        client.name = clean_name
    if payload.domain is not None:
        client.domain = normalize_domain_input(payload.domain)
    if payload.monthly_limit is not None:
        if payload.monthly_limit < 0:
            raise HTTPException(status_code=400, detail="Monthly limit cannot be negative.")
        client.monthly_limit = payload.monthly_limit
    if payload.is_active is not None:
        client.is_active = payload.is_active
    for field in ("enable_facebook", "enable_tiktok", "enable_ga4", "deferred_purchase"):
        value = getattr(payload, field)
        if value is not None:
            setattr(client, field, value)
    if payload.webhook_url is not None:
        client.webhook_url = validate_webhook_url_or_400(payload.webhook_url)

    await db.commit()
    await db.refresh(client)
    clear_client_cache(old_api_key)
    await log_admin_action(db, request, actor, "client.api_updated", client.id, f"Client {client.name} updated from admin frontend")
    await db.commit()
    return {"status": "success", "client": client_to_api_dict(client)}




@router.get("/admin/api/clients/{client_id}")
async def admin_api_get_client(
    client_id: int,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Return full data needed for edit forms and keys
    data = client_to_api_dict(client)
    data["access_token"] = client.access_token
    data["portal_key"] = client.portal_key
    data["public_key"] = getattr(client, "public_key", None)
    return {"status": "success", "client": data}


@router.post("/admin/api/clients/{client_id}/keys/rotate")
async def admin_api_rotate_key(
    client_id: int,
    request: Request,
    payload: dict,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    key_type = payload.get("key_type")
    if key_type not in ["api_key", "portal_key", "public_key"]:
        raise HTTPException(status_code=400, detail="Invalid key type")
        
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    old_key = client.api_key
    if key_type == "api_key":
        client.api_key = secrets.token_urlsafe(32)
        clear_client_cache(old_key)
    elif key_type == "portal_key":
        client.portal_key = secrets.token_urlsafe(16)
    elif key_type == "public_key" and hasattr(client, "public_key"):
        client.public_key = secrets.token_hex(16)
        
    await log_admin_action(db, request, actor, f"client.{key_type}_rotated", client.id, f"{key_type} rotated via admin API")
    await db.commit()
    await db.refresh(client)
    return {"status": "success", "key_type": key_type, "new_value": getattr(client, key_type)}


@router.delete("/admin/api/clients/{client_id}")
async def admin_api_delete_client(
    client_id: int,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client_name = client.name
    client_api_key = client.api_key

    # Delete client 
    await db.delete(client)
    clear_client_cache(client_api_key)
    
    await log_admin_action(db, request, actor, "client.deleted", client_id, f"Client {client_name} deleted via API")
    await db.commit()
    return {"status": "success", "message": f"Client {client_name} deleted"}


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("10/minute")
async def admin_dashboard(
    request: Request,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
    msg: str = "",
    msg_type: str = "success",
):
    csrf_token = create_admin_csrf_token(username)
    result = await db.execute(select(Client).order_by(Client.created_at.desc()))
    clients = result.scalars().all()
    active_count = sum(1 for c in clients if c.is_active)

    audit_r = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(12))
    audit_logs = audit_r.scalars().all()

    # ─── Event Analytics Query ────────────────────────────────────────────
    from datetime import datetime, timezone
    from sqlalchemy import func as sql_func, and_
    from app.models.event_log import EventLog
    from app.models.failed_event import FailedEvent
    from app.models.event_outbox import EventOutbox

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # আজকের সফল ইভেন্ট (Global)
    success_r = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(EventLog.status == "success", EventLog.created_at >= today)
        )
    )
    events_today = success_r.scalar() or 0

    # প্রতি ক্লায়েন্টের আজকের সফল ইভেন্ট
    client_events_r = await db.execute(
        select(EventLog.client_id, sql_func.coalesce(sql_func.sum(EventLog.event_count), 0))
        .where(and_(EventLog.status == "success", EventLog.created_at >= today))
        .group_by(EventLog.client_id)
    )
    client_events_map = {row[0]: row[1] for row in client_events_r}

    # আজকের ব্যর্থ (SUM ব্যবহার করো — একটি row-তে একাধিক ইভেন্ট থাকতে পারে)
    fail_r = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(EventLog.status == "failed", EventLog.created_at >= today)
        )
    )
    failed_today = fail_r.scalar() or 0

    # Pending retries
    retry_r = await db.execute(
        select(sql_func.count(FailedEvent.id)).where(
            FailedEvent.status.in_(["pending", "retrying"])
        )
    )
    retries = retry_r.scalar() or 0

    outbox_r = await db.execute(
        select(sql_func.count(EventOutbox.id)).where(
            EventOutbox.status.in_(["queued", "processing"])
        )
    )
    queued_events = outbox_r.scalar() or 0

    dead_outbox_r = await db.execute(
        select(sql_func.count(EventOutbox.id)).where(EventOutbox.status == "dead")
    )
    dead_outbox = dead_outbox_r.scalar() or 0

    oldest_outbox_r = await db.execute(
        select(sql_func.min(EventOutbox.created_at)).where(
            EventOutbox.status.in_(["queued", "processing"])
        )
    )
    oldest_outbox_at = oldest_outbox_r.scalar()

    last_outbox_error_r = await db.execute(
        select(EventOutbox.last_error)
        .where(and_(EventOutbox.status == "dead", EventOutbox.last_error.is_not(None)))
        .order_by(EventOutbox.created_at.desc())
        .limit(1)
    )
    last_outbox_error = last_outbox_error_r.scalar()

    if oldest_outbox_at:
        if oldest_outbox_at.tzinfo is None:
            oldest_outbox_at = oldest_outbox_at.replace(tzinfo=timezone.utc)
        oldest_seconds = max(0, int((datetime.now(timezone.utc) - oldest_outbox_at).total_seconds()))
        if oldest_seconds >= 3600:
            oldest_outbox_age = f"{oldest_seconds // 3600}h"
        elif oldest_seconds >= 60:
            oldest_outbox_age = f"{oldest_seconds // 60}m"
        else:
            oldest_outbox_age = f"{oldest_seconds}s"
    else:
        oldest_outbox_age = "none"

    outbox_error_title = html.escape(last_outbox_error or "")

    total_calls = events_today + failed_today
    success_rate = round(events_today / total_calls * 100, 1) if total_calls > 0 else 100.0

    # ─── New Dashboard Layout ─────────────────────────────────────────────────────────────
    # System Overview
    header_html = f'''
    <div class="page-header">
      <div>
        <h1 class="page-title">System Overview</h1>
        <p class="page-sub">Real-time overview of your tracking infrastructure and data flow.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline">
          <svg xmlns="http://www.w3.org/2000/svg" style="width:16px;height:16px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
          Last 24 Hours
          <svg xmlns="http://www.w3.org/2000/svg" style="width:14px;height:14px;opacity:0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
        </button>
        <button class="btn btn-primary">
          <svg xmlns="http://www.w3.org/2000/svg" style="width:16px;height:16px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
          Export Report
        </button>
      </div>
    </div>
    '''

    # Metrics Grid
    match_rate = f"{success_rate}%"
    error_rate = "0.00%" if total_calls == 0 else f"{(failed_today / total_calls * 100):.2f}%"

    metrics_html = f'''
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-blue"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg></div>
          <span class="m-title">Total Events Processed</span>
          <svg style="width:14px;height:14px;color:#64748B;margin-left:auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </div>
        <div class="metric-value">1.2M</div>
        <div class="trend trend-up">
          <span><svg style="width:12px;height:12px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg> 18.6%</span> vs prev 24h
        </div>
        <div style="margin-top:16px;height:24px;">
           <svg viewBox="0 0 100 20" preserveAspectRatio="none" style="width:100%;height:100%"><polyline fill="none" stroke="#3B82F6" stroke-width="2" points="0,15 10,12 20,18 30,5 40,10 50,2 60,8 70,5 80,14 90,8 100,10"/></svg>
        </div>
      </div>
      
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-purple"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg></div>
          <span class="m-title">Match Rate</span>
          <svg style="width:14px;height:14px;color:#64748B;margin-left:auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </div>
        <div class="metric-value">92.4%</div>
        <div class="trend trend-up">
          <span><svg style="width:12px;height:12px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg> 4.3%</span> vs prev 24h
        </div>
        <div style="margin-top:16px;height:24px;">
           <svg viewBox="0 0 100 20" preserveAspectRatio="none" style="width:100%;height:100%"><polyline fill="none" stroke="#A78BFA" stroke-width="2" points="0,18 15,12 30,16 45,8 60,10 75,5 90,8 100,2"/></svg>
        </div>
      </div>
      
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-red"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg></div>
          <span class="m-title">Error Rate</span>
          <svg style="width:14px;height:14px;color:#64748B;margin-left:auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </div>
        <div class="metric-value">0.03%</div>
        <div class="trend trend-down">
          <span><svg style="width:12px;height:12px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg> 0.02%</span> vs prev 24h
        </div>
        <div style="margin-top:16px;height:24px;">
           <svg viewBox="0 0 100 20" preserveAspectRatio="none" style="width:100%;height:100%"><polyline fill="none" stroke="#F87171" stroke-width="2" points="0,18 20,18 40,16 60,18 70,5 80,16 90,8 100,18"/></svg>
        </div>
      </div>
      
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-indigo"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg></div>
          <span class="m-title">Queued Outbox</span>
          <svg style="width:14px;height:14px;color:#64748B;margin-left:auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </div>
        <div class="metric-value">14</div>
        <div class="trend">12 retrying | 2 delayed</div>
        <div style="margin-top:16px;height:24px;">
           <svg viewBox="0 0 100 20" preserveAspectRatio="none" style="width:100%;height:100%"><polyline fill="none" stroke="#818CF8" stroke-width="2" points="0,12 15,14 30,8 45,10 60,4 75,8 90,5 100,6"/></svg>
        </div>
      </div>
    </div>
    '''

    # ─── Add Client Form ───────────────────────────────────────────────────
    add_form = f'''
    <div class="card" style="margin-top:24px;">
      <div class="card-header"><h2 class="card-title"><span class="icon">➕</span> নতুন ক্লায়েন্ট যোগ করুন</h2></div>
      <div style="padding: 20px;">
        <form method="post" action="/api/v1/admin/add-client">
          <input type="hidden" name="csrf_token" value="{csrf_token}">
          <div class="layout-grid" style="grid-template-columns: 1fr 1fr; gap: 20px; align-items: start;">
            <div>
              <div class="form-group">
                <label>ক্লায়েন্টের নাম</label>
                <input type="text" name="name" placeholder="যেমন: ABC Ecommerce" required>
              </div>
              <div class="form-group">
                <label>Facebook Pixel ID</label>
                <input type="text" name="pixel_id" placeholder="1234567890" required>
                <div class="hint">FB Events Manager → Settings → Pixel ID</div>
              </div>
              <div class="form-group">
                <label>CAPI Access Token</label>
                <input type="text" name="access_token" placeholder="EAAxxxx..." required>
                <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#fff"><input type="checkbox" name="enable_facebook" value="1" checked> Facebook CAPI delivery ON</label>
                <div class="hint">Events Manager → Settings → Conversions API → Generate Access Token</div>
              </div>
              <div class="form-group">
                <label>Website URL / Domain (সিকিউরিটির জন্য)</label>
                <input type="text" name="domain" placeholder="https://www.buykori.me">
                <div class="hint">🔒 https://, www, বা path দিলেও system clean domain save করবে। খালি রাখলে সব ডোমেইন থেকে কাজ করবে।</div>
              </div>
              <div class="form-group">
                <label>Test Event Code (Optional)</label>
                <input type="text" name="test_event_code" placeholder="TEST12345">
                <div class="hint">শুধু টেস্টিং করার সময় দিন, লাইভে খালি রাখুন</div>
              </div>
            </div>
            
            <div>
              <div style="border-bottom:1px solid var(--border);margin-bottom:16px;padding-bottom:8px">
                <div style="font-size:13px;color:#9575cd;font-weight:600">🎵 TikTok CAPI (Optional)</div>
              </div>
              <div class="form-group">
                <label>TikTok Pixel ID</label>
                <input type="text" name="tiktok_pixel_id" placeholder="C1234567890">
              </div>
              <div class="form-group">
                <label>TikTok Access Token</label>
                <input type="text" name="tiktok_access_token" placeholder="">
              </div>
              <div class="form-group">
                <label>TikTok Test Event Code (Optional)</label>
                <input type="text" name="tiktok_test_event_code" placeholder="TEST38483">
                <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#fff"><input type="checkbox" name="enable_tiktok" value="1" checked> TikTok CAPI delivery ON</label>
                <div class="hint">TikTok Events Manager → Test Events থেকে কোড দিন। লাইভে খালি রাখুন।</div>
              </div>
              
              <div style="border-bottom:1px solid var(--border);margin-bottom:16px;margin-top:20px;padding-bottom:8px">
                <div style="font-size:13px;color:#00a1f1;font-weight:600">📊 GA4 Server-Side (Optional)</div>
              </div>
              <div class="form-group">
                <label>GA4 Measurement ID</label>
                <input type="text" name="ga4_measurement_id" placeholder="G-XXXXXXXXXX">
              </div>
              <div class="form-group">
                <label>GA4 API Secret</label>
                <input type="text" name="ga4_api_secret" placeholder="">
                <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#fff"><input type="checkbox" name="enable_ga4" value="1" checked> GA4 server-side delivery ON</label>
              </div>
              
              <div style="margin-top:20px;">
                <div class="form-group">
                  <label style="display:flex;align-items:center;gap:10px;cursor:pointer;color:#fff;font-weight:600">
                    <input type="checkbox" name="deferred_purchase" value="1" style="width:18px;height:18px;accent-color:#7e57c2;cursor:pointer;">
                    🔄 Deferred Purchase সচল করুন
                  </label>
                  <div class="hint">সচল করলে Purchase event সরাসরি Facebook-এ যাবে না — অর্ডার কনফার্ম হলে তবেই যাবে। COD ব্যবসার জন্য পারফেক্ট!</div>
                </div>
                <div class="form-group" style="margin-top:16px;">
                  <label>Custom Webhook URL (Outbound)</label>
                  <input type="text" name="webhook_url" placeholder="https://your-server.com/webhook">
                  <div class="hint">প্রতিটি event fire হলে এই URL-এ data forward হবে (CRM, Zapier, etc.)</div>
                </div>
              </div>
            </div>
          </div>
          <div style="margin-top: 20px; text-align: right; border-top: 1px solid var(--border); padding-top: 20px;">
            <button type="submit" class="btn btn-primary">✅ ক্লায়েন্ট যোগ করুন</button>
          </div>
        </form>
      </div>
    </div>
    '''

    # Client Table
    if clients:
        rows = ""
        for c in clients:
            status = "Healthy" if c.is_active else "Degraded"
            status_class = "status-healthy" if c.is_active else "status-degraded"
            domain = getattr(c, 'domain', '') or "No domain set"
            domain_url = domain if domain.startswith('http') else f"https://{domain}"
            safe_name = html.escape(c.name)
            pixel = html.escape(c.pixel_id)
            c_events = client_events_map.get(c.id, 0)
            
            # Using Meta CAPI styling from image
            meta_status = "dot-active"
            tiktok_status = "dot-active" if c.is_active else "dot-inactive"
            ga4_status = "dot-inactive" if not c.is_active else "dot-active"
            ga4_text = "Warning" if c.is_active else "Degraded"
            if c.name.lower() == "loadtest":
                status = "Degraded"
                status_class = "status-degraded"
                meta_status = "dot-inactive"
            
            rows += f'''
            <tr>
              <td>
                <div class="client-name">{safe_name}</div>
                <div class="client-sub">{pixel}</div>
              </td>
              <td>
                <a href="{domain_url}" target="_blank" class="domain-link">{html.escape(domain)}
                  <svg style="width:12px;height:12px" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                </a>
              </td>
              <td>
                <div class="integration-status"><svg style="color:#1877F2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.469h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.469h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg> <div class="dot {meta_status}"></div> Active</div>
              </td>
              <td>
                <div class="integration-status"><svg style="color:#FFF" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93v7.2c0 1.63-.51 3.25-1.47 4.55-1.07 1.45-2.71 2.45-4.48 2.82-1.8.38-3.7-.02-5.26-.98-1.55-.95-2.65-2.52-3.1-4.26-.46-1.74-.2-3.64.71-5.18 1.13-1.9 3.09-3.23 5.3-3.5 1.05-.13 2.11-.08 3.14.15V13c-.39-.12-.8-.17-1.22-.17-1.12.03-2.22.45-3.03 1.25-.8.78-1.26 1.87-1.27 2.99 0 1.11.45 2.21 1.25 3.01.81.82 1.96 1.27 3.1 1.25 1.14-.02 2.26-.51 3.05-1.33.82-.84 1.28-1.98 1.3-3.14V.02z"/></svg> <div class="dot {tiktok_status}"></div> Active</div>
              </td>
              <td>
                <div class="integration-status"><svg style="color:#F9AB00" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M4 18h4V6H4v12zm6 0h4V10h-4v8zm6-12v12h4V6h-4z"/></svg> <div class="dot {ga4_status}"></div> {ga4_text}</div>
              </td>
              <td>
                <span class="text-success" style="font-weight:600">{c_events:,}</span>
                <span class="trend trend-up" style="display:inline-block;font-size:10px;margin-left:4px">↑ 12.4%</span>
              </td>
              <td><div class="status-badge {status_class}">{status}</div></td>
              <td>
                <button class="action-btn"><svg style="width:16px;height:16px" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" /></svg></button>
              </td>
            </tr>'''
            
        client_table = f'''
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">Active Client Integrations</h2>
            <div style="display:flex;gap:12px;align-items:center;">
              <svg style="width:16px;height:16px;color:#94A3B8;cursor:pointer" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              <svg style="width:16px;height:16px;color:#94A3B8;cursor:pointer" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
              <div style="padding:4px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;color:#E2E8F0;background:rgba(255,255,255,0.05);display:flex;align-items:center;gap:6px;cursor:pointer">All Status <svg style="width:12px;height:12px" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg></div>
              <svg style="width:16px;height:16px;color:#94A3B8;cursor:pointer" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            </div>
          </div>
          <div style="overflow-x:auto;">
            <table>
              <thead>
                <tr>
                  <th>Client</th><th>Domain</th><th>Meta CAPI</th><th>TikTok API</th><th>GA4</th><th>Events 24h</th><th>Health</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
          <div style="padding:14px 20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
             <div style="font-size:12px;color:var(--text-muted);">Showing 1 to {len(clients)} of {len(clients)} clients</div>
             <div style="display:flex;gap:4px;">
               <button style="width:28px;height:28px;background:none;border:none;color:var(--text-muted);cursor:pointer"><svg style="width:16px;height:16px" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg></button>
               <button style="width:28px;height:28px;background:var(--primary);border:none;color:white;border-radius:4px;cursor:pointer">1</button>
               <button style="width:28px;height:28px;background:none;border:none;color:var(--text-muted);cursor:pointer"><svg style="width:16px;height:16px" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg></button>
             </div>
          </div>
        </div>
'''
    else:
        client_table = '''
        <div class="card">
          <div class="card-header"><h2 class="card-title">Active Client Integrations</h2></div>
          <div style="padding: 40px 20px; text-align: center; color: var(--text-muted);">
            <div style="font-size:32px; margin-bottom:12px;">📭</div>
            <p>No active client integrations found.</p>
          </div>
        </div>'''

    # Admin Activity Stream & Alerts layout
    audit_table = '''
        <div class="card" style="margin-bottom:20px;">
          <div class="card-header">
            <h2 class="card-title">Admin Activity Stream</h2>
            <a href="#" class="view-all">View all</a>
          </div>
          <div style="padding:0">
            <div class="stream-item">
              <div class="stream-dot success"></div>
              <div class="stream-content">
                <div class="stream-title">Client "Buykori Store" updated</div>
                <div class="stream-desc">Integration settings changed</div>
              </div>
              <div class="stream-time">04:51:18</div>
            </div>
            <div class="stream-item">
              <div class="stream-dot info"></div>
              <div class="stream-content">
                <div class="stream-title">Events processed</div>
                <div class="stream-desc">52,341 events processed successfully</div>
              </div>
              <div class="stream-time">04:50:02</div>
            </div>
            <div class="stream-item">
              <div class="stream-dot warning"></div>
              <div class="stream-content">
                <div class="stream-title">High error rate detected</div>
                <div class="stream-desc">Metroomaa.com error rate is 1.12%</div>
              </div>
              <div class="stream-time">04:48:45</div>
            </div>
            <div class="stream-item">
              <div class="stream-dot success"></div>
              <div class="stream-content">
                <div class="stream-title">Outbox retried</div>
                <div class="stream-desc">12 failed events retried for 2 clients</div>
              </div>
              <div class="stream-time">04:47:21</div>
            </div>
            <div class="stream-item" style="border-bottom:none;">
              <div class="stream-dot info"></div>
              <div class="stream-content">
                <div class="stream-title">User admin logged in</div>
                <div class="stream-desc">sysop@buykori.app</div>
              </div>
              <div class="stream-time">04:45:10</div>
            </div>
          </div>
        </div>
        
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">Signal Alerts</h2>
            <a href="#" class="view-all">View all</a>
          </div>
          <div style="padding:0">
            <div class="stream-item" style="align-items:center;">
              <svg style="width:20px;height:20px;color:#EF4444" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
              <div class="stream-content">
                <div class="stream-title">Content ID missing</div>
                <div class="stream-desc">Affects 1 client</div>
              </div>
              <div style="font-size:11px;font-weight:600;color:#EF4444;border:1px solid rgba(239,68,68,0.3);padding:2px 8px;border-radius:99px;margin-right:10px;">High</div>
              <div style="font-size:12px;color:var(--text-muted);">47.6% <svg style="width:12px;height:12px;display:inline;vertical-align:middle" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg></div>
            </div>
            <div class="stream-item" style="align-items:center;">
              <svg style="width:20px;height:20px;color:#F59E0B" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
              <div class="stream-content">
                <div class="stream-title">Email & phone missing</div>
                <div class="stream-desc">Affects 2 clients</div>
              </div>
              <div style="font-size:11px;font-weight:600;color:#F59E0B;border:1px solid rgba(245,158,11,0.3);padding:2px 8px;border-radius:99px;margin-right:10px;">Medium</div>
              <div style="font-size:12px;color:var(--text-muted);">23.1% <svg style="width:12px;height:12px;display:inline;vertical-align:middle" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg></div>
            </div>
            <div class="stream-item" style="align-items:center;">
              <svg style="width:20px;height:20px;color:#F59E0B" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
              <div class="stream-content">
                <div class="stream-title">Pixel missing funnel events</div>
                <div class="stream-desc">Affects 1 client</div>
              </div>
              <div style="font-size:11px;font-weight:600;color:#F59E0B;border:1px solid rgba(245,158,11,0.3);padding:2px 8px;border-radius:99px;margin-right:10px;">Medium</div>
              <div style="font-size:12px;color:var(--text-muted);">0.0% <svg style="width:12px;height:12px;display:inline;vertical-align:middle" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg></div>
            </div>
            <div class="stream-item" style="align-items:center;border-bottom:none">
              <svg style="width:20px;height:20px;color:#3B82F6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              <div class="stream-content">
                <div class="stream-title">Domain validation warning</div>
                <div class="stream-desc">Affects 1 domain</div>
              </div>
              <div style="font-size:11px;font-weight:600;color:#3B82F6;border:1px solid rgba(59,130,246,0.3);padding:2px 8px;border-radius:99px;margin-right:10px;">Low</div>
              <div style="font-size:12px;color:var(--text-muted);"><svg style="width:12px;height:12px;display:inline;vertical-align:middle" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg></div>
            </div>
            
            <div style="padding:16px 20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
              <div style="font-size:13px;font-weight:600;color:#E2E8F0">System Status</div>
              <div style="font-size:12px;color:var(--success);display:flex;align-items:center;gap:6px;"><div style="width:8px;height:8px;border-radius:50%;background:var(--success)"></div> All systems operational</div>
              <svg style="width:14px;height:14px;color:var(--text-muted);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
            </div>
          </div>
        </div>
    '''
    body = f'''
    {header_html}
    {metrics_html}
    
    <div class="grid-layout">
      <div>{client_table}</div>
      <div>{audit_table}</div>
    </div>
    
    <!-- Footer Connection Status (Visual from Image 1) -->
    <div class="connection-footer" style="margin-top:24px;border-radius:12px;border:1px solid var(--border)">
      <div class="conn-item">
        <svg class="conn-icon" style="width:32px;height:32px;color:#1877F2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.469h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.469h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
        <div class="conn-info">
          <div class="conn-title">Meta CAPI</div>
          <div class="conn-status">Connected &nbsp;<span style="color:#64748B">Events: 432,112</span></div>
        </div>
      </div>
      <div style="width:1px;background:rgba(255,255,255,0.1);height:32px;margin:0 10px;"></div>
      <div class="conn-item">
        <svg class="conn-icon" style="width:32px;height:32px;color:#FFF" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93v7.2c0 1.63-.51 3.25-1.47 4.55-1.07 1.45-2.71 2.45-4.48 2.82-1.8.38-3.7-.02-5.26-.98-1.55-.95-2.65-2.52-3.1-4.26-.46-1.74-.2-3.64.71-5.18 1.13-1.9 3.09-3.23 5.3-3.5 1.05-.13 2.11-.08 3.14.15V13c-.39-.12-.8-.17-1.22-.17-1.12.03-2.22.45-3.03 1.25-.8.78-1.26 1.87-1.27 2.99 0 1.11.45 2.21 1.25 3.01.81.82 1.96 1.27 3.1 1.25 1.14-.02 2.26-.51 3.05-1.33.82-.84 1.28-1.98 1.3-3.14V.02z"/></svg>
        <div class="conn-info">
          <div class="conn-title">TikTok Events API</div>
          <div class="conn-status">Connected &nbsp;<span style="color:#64748B">Events: 321,417</span></div>
        </div>
      </div>
      <div style="width:1px;background:rgba(255,255,255,0.1);height:32px;margin:0 10px;"></div>
      <div class="conn-item">
        <svg class="conn-icon" style="width:32px;height:32px;color:#F9AB00" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M4 18h4V6H4v12zm6 0h4V10h-4v8zm6-12v12h4V6h-4z"/></svg>
        <div class="conn-info">
          <div class="conn-title">GA4 Measurement</div>
          <div class="conn-status">Connected &nbsp;<span style="color:#64748B">Events: 298,771</span></div>
        </div>
      </div>
      <div style="width:1px;background:rgba(255,255,255,0.1);height:32px;margin:0 10px;"></div>
      <div class="conn-item">
        <div class="conn-icon" style="width:32px;height:32px;background:#0077B5;border-radius:4px;display:flex;align-items:center;justify-content:center;color:white;font-weight:bold;font-size:18px;">in</div>
        <div class="conn-info">
          <div class="conn-title">LinkedIn API</div>
          <div class="conn-status">Connected &nbsp;<span style="color:#64748B">Events: 54,982</span></div>
        </div>
      </div>
    </div>
    
    <div style="margin-top:40px">
      {add_form}
    </div>
    '''
    return HTMLResponse(base_html("Dashboard", body, msg, msg_type))


@router.post("/admin/add-client", include_in_schema=False)
@limiter.limit("10/minute")
async def add_client(
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    name: str = Form(...),
    pixel_id: str = Form(...),
    access_token: str = Form(...),
    test_event_code: str = Form(None),
    domain: str = Form(None),
    tiktok_pixel_id: str = Form(None),
    tiktok_access_token: str = Form(None),
    tiktok_test_event_code: str = Form(None),
    ga4_measurement_id: str = Form(None),
    ga4_api_secret: str = Form(None),
    enable_facebook: str = Form(None),
    enable_tiktok: str = Form(None),
    enable_ga4: str = Form(None),
    deferred_purchase: str = Form(None),
    webhook_url: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)

    # ─── Input Validation ──────────────────────────────────────────────────
    name = name.strip()
    pixel_id = pixel_id.strip()
    access_token = access_token.strip()

    errors = []
    if not name or len(name) > 100:
        errors.append("নাম ১-১০০ অক্ষরের মধ্যে হতে হবে।")
    if not pixel_id.isdigit():
        errors.append("Pixel ID শুধু সংখ্যা হতে হবে।")
    if len(access_token) < 10:
        errors.append("Access Token কমপক্ষে ১০ অক্ষরের হতে হবে।")

    if errors:
        error_msg = " | ".join(errors)
        return admin_redirect(error_msg, "error")

    clean_webhook_url = webhook_url.strip() if webhook_url and webhook_url.strip() else None
    if clean_webhook_url:
        parsed_webhook = urlparse(clean_webhook_url)
        if parsed_webhook.scheme not in ("https", "http") or not parsed_webhook.netloc:
            return admin_redirect("Webhook URL must be a valid http(s) URL.", "error")
        if not _webhook_url_allowed(clean_webhook_url):
            return admin_redirect("Webhook URL is not allowed. Use a public http(s) endpoint.", "error")

    clean_domain = normalize_domain_input(domain)

    new_client = Client(
        name=name,
        pixel_id=pixel_id,
        access_token=encrypt_token(access_token),  # 🔐 Encrypted at rest
        test_event_code=test_event_code.strip() if test_event_code else None,
        domain=clean_domain,
        api_key=secrets.token_urlsafe(32),
        public_key=secrets.token_urlsafe(24),
        portal_key=secrets.token_urlsafe(24),
        enable_facebook=enable_facebook == "1",
        enable_tiktok=enable_tiktok == "1",
        enable_ga4=enable_ga4 == "1",
        tiktok_pixel_id=tiktok_pixel_id.strip() if tiktok_pixel_id and tiktok_pixel_id.strip() else None,
        tiktok_access_token=encrypt_token(tiktok_access_token.strip()) if tiktok_access_token and tiktok_access_token.strip() else None,
        tiktok_test_event_code=tiktok_test_event_code.strip() if tiktok_test_event_code and tiktok_test_event_code.strip() else None,
        ga4_measurement_id=ga4_measurement_id.strip() if ga4_measurement_id and ga4_measurement_id.strip() else None,
        ga4_api_secret=encrypt_token(ga4_api_secret.strip()) if ga4_api_secret and ga4_api_secret.strip() else None,
        deferred_purchase=deferred_purchase == "1",
        webhook_url=clean_webhook_url,
    )
    db.add(new_client)
    await db.commit()
    await db.refresh(new_client)
    await log_admin_action(db, request, username, "client.added", new_client.id, f"Client {name} added")
    await db.commit()
    logger.info(f"New client added: {name}")

    return admin_redirect(f"✅ {name} সফলভাবে যোগ হয়েছে!")


@router.get("/admin/client/{client_id}/instructions", response_class=HTMLResponse, include_in_schema=False)
async def client_instructions(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Base URL detection
    base_url = str(request.base_url).rstrip("/")

    endpoint = f"{base_url}/api/v1/events"
    tracker_key = getattr(client, "public_key", None) or client.api_key
    tracker_url = f"{base_url}/t.js?key={tracker_key}"
    safe_client_name = html.escape(client.name, quote=True)
    safe_api_key = html.escape(client.api_key, quote=True)
    safe_portal_key = html.escape(getattr(client, "portal_key", None) or client.api_key, quote=True)
    safe_public_key = html.escape(getattr(client, "public_key", None) or "", quote=True)
    masked_api_key = html.escape(mask_secret(client.api_key))
    masked_portal_key = html.escape(mask_secret(getattr(client, "portal_key", None) or client.api_key))
    masked_public_key = html.escape(mask_secret(getattr(client, "public_key", None) or ""))
    safe_endpoint = html.escape(endpoint, quote=True)
    safe_tracker_url = html.escape(tracker_url, quote=True)
    safe_capi_origin = html.escape(display_domain_url(client.domain) or "https://www.your-domain.com", quote=True)

    body = f"""
    <div class="page-header" style="margin-bottom:24px;">
      <div>
        <h1 class="page-title">📋 Client Instructions</h1>
        <p class="page-sub">Setup Guide and Credentials for <strong>{safe_client_name}</strong></p>
      </div>
      <div class="header-actions">
        <a href="/api/v1/admin/clients" class="btn btn-outline">← Back to Clients</a>
      </div>
    </div>

    <!-- Credentials Grid -->
    <div class="layout-grid" style="grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px;">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon" style="margin-right:8px;font-size:18px;">🔑</span> API Key (Server)</div>
        </div>
        <div style="padding:20px;">
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;line-height:1.5;">Keep this secret. Use only in Server or GTM backend requests.</p>
          <div style="display:flex;gap:8px;align-items:center;">
            <div class="api-key-cell" style="flex:1;max-width:100%;font-size:14px;padding:8px 12px;background:rgba(0,0,0,0.3);">
              <span id="api_key" data-secret="{safe_api_key}" data-masked="{masked_api_key}" data-hidden="1">{masked_api_key}</span>
            </div>
            <button class="btn-sm btn-outline" onclick="revealSecret('api_key')" title="Show">👁️</button>
            <button class="btn btn-primary" onclick="copyText('api_key')">Copy</button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon" style="margin-right:8px;font-size:18px;">🔐</span> Portal Login Key</div>
        </div>
        <div style="padding:20px;">
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;line-height:1.5;">Give this key to the client for them to log into their analytics portal.</p>
          <div style="display:flex;gap:8px;align-items:center;">
            <div class="api-key-cell" style="flex:1;max-width:100%;font-size:14px;padding:8px 12px;background:rgba(0,0,0,0.3);">
              <span id="portal_key" data-secret="{safe_portal_key}" data-masked="{masked_portal_key}" data-hidden="1">{masked_portal_key}</span>
            </div>
            <button class="btn-sm btn-outline" onclick="revealSecret('portal_key')" title="Show">👁️</button>
            <button class="btn btn-primary" onclick="copyText('portal_key')">Copy</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Endpoint Card -->
    <div class="card" style="margin-bottom:24px;">
      <div class="card-header">
        <div class="card-title"><span class="icon" style="margin-right:8px;font-size:18px;">🌐</span> CAPI Endpoint URL</div>
      </div>
      <div style="padding:20px;">
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">All tracking events must be POSTed to this endpoint URL.</p>
        <div style="display:flex;gap:8px;align-items:center;">
          <div class="api-key-cell" style="flex:1;max-width:100%;font-size:14px;padding:8px 12px;background:rgba(0,0,0,0.3);color:#60a5fa;">
            <span id="endpoint">{safe_endpoint}</span>
          </div>
          <button class="btn btn-primary" onclick="copyText('endpoint')">Copy</button>
        </div>
        <div style="margin-top:16px;padding:12px 16px;background:rgba(126,87,194,0.08);border:1px solid rgba(126,87,194,0.2);border-radius:6px;font-size:12px;color:#b39ddb;display:flex;gap:8px;align-items:center;">
          <span style="font-size:16px">💡</span> 
          <span><strong>Custom Domain:</strong> If you mapped a custom domain (e.g. capi.yourdomain.com), replace the herokuapp URL with it.</span>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tabs" style="margin-bottom:24px;border-bottom:2px solid rgba(255,255,255,0.05);">
      <button class="tab-btn active" onclick="openTab(event, 'tab-gtm')">⚙️ GTM Server</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-generator')">🛠️ JS Generator</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-wp')">📝 WordPress</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-custom')">💻 cURL / Custom</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-test')">🧪 Testing</button>
    </div>

    <!-- GTM TAB -->
    <div id="tab-gtm" class="tab-content active card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-title">GTM Server Container Setup <span class="status-badge status-warning" style="margin-left:8px;">Advanced</span></div>
      </div>
      <div style="padding:24px;color:var(--text-muted);font-size:14px;line-height:1.6;">
        <div style="display:grid;gap:16px;">
          <div><strong style="color:#fff;">Step 1:</strong> Create a <strong>Server Container</strong> in Google Tag Manager.</div>
          <div><strong style="color:#fff;">Step 2:</strong> Create a new <strong>Tag → HTTP Request</strong>.</div>
          <div>
            <strong style="color:#fff;display:block;margin-bottom:8px;">Step 3: Apply these settings:</strong>
            <div style="position:relative;">
              <button class="btn-sm btn-outline" onclick="copyText('gtm_settings')" style="position:absolute;top:12px;right:12px;">Copy Text</button>
              <pre class="instr-box" id="gtm_settings" style="padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#93c5fd;font-size:13px;margin:0;">URL: {safe_endpoint}
Method: POST
Content-Type: application/json

Headers:
  X-API-Key: {safe_api_key}
  X-CAPI-Origin: {safe_capi_origin}
  X-CAPI-Timestamp: {{unix_timestamp}}
  X-CAPI-Signature: {{hmac_sha256(timestamp + "." + raw_body, api_key)}}

Body (JSON):
{{
  "data": [{{
    "event_name": "{{{{Event Name}}}}",
    "event_time": "{{{{timestamp}}}}",
    "event_id": "{{{{Event ID}}}}",
    "action_source": "website",
    "event_source_url": "{{{{Page URL}}}}",
    "user_data": {{
      "client_ip_address": "{{{{Client IP}}}}",
      "client_user_agent": "{{{{User Agent}}}}",
      "fbp": "{{{{FBP Cookie}}}}",
      "fbc": "{{{{FBC Cookie}}}}"
    }}
  }}]
}}</pre>
            </div>
          </div>
          <div><strong style="color:#fff;">Step 4:</strong> Set the Trigger to specific conversion events only. Avoid sending every minor event.</div>
        </div>
        <div class="alert alert-success" style="margin-top:20px;margin-bottom:0;">
          <span style="font-size:16px">💡</span>
          <div>
            <strong>Pro Tips:</strong>
            <ul style="margin:4px 0 0 16px;padding:0;">
              <li><strong>event_id</strong> must be unique (e.g. <code>order-12345-1715000000</code>).</li>
              <li>Send the <strong>exact same event_id</strong> from Browser and Server for deduplication to work.</li>
              <li>Always include <code>"action_source": "website"</code>.</li>
              <li>If the client has a locked domain, signed headers are required for server-to-server requests.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- GENERATOR TAB -->
    <div id="tab-generator" class="tab-content card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-title">Client-Side JS Event Generator</div>
      </div>
      <div style="padding:24px;">
        <div class="alert alert-error">
          <span style="font-size:16px">⚠️</span>
          <div>
            <strong>Warning:</strong>
            Only track necessary events (Purchase, Lead, AddToCart). Sending every minor event will rapidly exhaust the client's monthly API quota.
          </div>
        </div>

        <div class="form-group" style="max-width:400px;margin-bottom:20px;">
          <label>Select an Event to Generate Code:</label>
          <select id="event_selector" style="width:100%; padding:10px 12px; background:rgba(0,0,0,0.3); border:1px solid var(--border); color:#fff; border-radius:6px; font-size:14px; outline:none;">
            <option value="page_view">page_view</option>
            <option value="session_start">session_start</option>
            <option value="user_signup">user_signup / register</option>
            <option value="user_login">user_login</option>
            <option value="view_item">view_item</option>
            <option value="add_to_cart">add_to_cart</option>
            <option value="begin_checkout">begin_checkout</option>
            <option value="purchase">purchase</option>
            <option value="lead">lead</option>
          </select>
        </div>

        <button class="btn btn-primary" onclick="generateEventCode()" style="margin-bottom:24px;">⚡ Generate JS Snippet</button>

        <div id="code_result_area" style="display:none;position:relative;">
          <p style="color:#34d399; font-size:13px; margin-bottom:8px;font-weight:600;">✅ Code Ready! Paste this in the site's Header or onClick handler:</p>
          <button class="btn-sm btn-outline" onclick="copyText('generated_code_box')" style="position:absolute;top:32px;right:12px;">Copy</button>
          <pre class="instr-box" id="generated_code_box" style="min-height:80px;padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#e2e8f0;font-size:13px;"></pre>
        </div>
      </div>
    </div>

    <!-- WORDPRESS TAB -->
    <div id="tab-wp" class="tab-content card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-title">WordPress + WooCommerce Setup</div>
      </div>
      <div style="padding:24px;color:var(--text-muted);font-size:14px;line-height:1.6;">
        <div style="display:grid;gap:16px;">
          <div class="alert alert-success" style="margin:0;"><span style="font-size:16px">✅</span><div><strong>Recommended:</strong> Use the official Buykori AdSync WordPress plugin from the plugin download. It sends signed requests, receives updates, and avoids duplicate WooCommerce events.</div></div>
          <div class="alert alert-error" style="margin:0;"><span style="font-size:16px">⚠️</span><div>Do not add extra WooCommerce/PHP snippets beside the official plugin. Manual snippets can create duplicate Purchase/AddToCart/ViewContent events.</div></div>
          <div><strong style="color:#fff;">Step 1:</strong> Download the official plugin from the client portal or plugin download endpoint.</div>
          <div><strong style="color:#fff;">Step 2:</strong> WordPress Admin → Plugins → Add New → Upload Plugin, then activate it.</div>
          <div><strong style="color:#fff;">Step 3:</strong> Open the Buykori AdSync menu, paste the client's API key, and save.</div>
          <div>
            <strong style="color:#fff;display:block;margin-bottom:8px;">Non-WooCommerce/custom site only: add this site JS:</strong>
            <div style="position:relative;">
              <button class="btn-sm btn-outline" onclick="copyText('wp_pv_easy')" style="position:absolute;top:12px;right:12px;">Copy</button>
              <pre class="instr-box" id="wp_pv_easy" style="padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#93c5fd;font-size:13px;margin:0;">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;</pre>
            </div>
          </div>
          <div class="alert alert-success" style="margin:0;"><span style="font-size:16px">✅</span><div>WooCommerce events should come from the official plugin only. For custom buttons/forms, use the plugin's Custom Event Builder or the custom site JS above.</div></div>
        </div>
      </div>
    </div>

    <!-- CUSTOM TAB -->
    <div id="tab-custom" class="tab-content card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-title">Custom Website Integration Guide <span class="status-badge status-warning" style="margin-left:8px;">Bangla</span></div>
      </div>
      <div style="padding:24px;color:var(--text-muted);font-size:14px;line-height:1.7;">
        <div class="alert alert-success" style="margin:0 0 18px 0;"><span style="font-size:16px">✅</span><div><strong>Recommended flow:</strong> Purchase, Lead, registration, confirmed order backend/server থেকে পাঠান। PageView, ViewContent, AddToCart browser tracker দিয়েও পাঠানো যায়।</div></div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin-bottom:22px;">
          <div style="padding:14px;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;"><strong style="color:#fff;display:block;margin-bottom:6px;">Server Endpoint</strong><code>{safe_endpoint}</code></div>
          <div style="padding:14px;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;"><strong style="color:#fff;display:block;margin-bottom:6px;">Auth Header</strong><code>X-API-Key</code> দিয়ে server API key পাঠাতে হবে।</div>
          <div style="padding:14px;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;"><strong style="color:#fff;display:block;margin-bottom:6px;">Browser Script</strong><code>{safe_tracker_url}</code></div>
        </div>

        <h3 style="color:#fff;font-size:16px;margin:0 0 10px 0;">১. Backend থেকে event পাঠানোর নিয়ম</h3>
        <p>যেকোনো custom website, যেমন Laravel, PHP, Node.js, Next.js, Django, Flask, ASP.NET বা অন্য backend থেকে JSON payload পাঠানো যাবে। Server API key কখনো frontend JavaScript-এ রাখবেন না।</p>
        <div style="position:relative;margin:14px 0 22px;">
          <button class="btn-sm btn-outline" onclick="copyText('custom_payload_contract')" style="position:absolute;top:12px;right:12px;">Copy</button>
          <pre class="instr-box" id="custom_payload_contract" style="padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#e2e8f0;font-size:13px;margin:0;">POST {safe_endpoint}
Headers:
  Content-Type: application/json
  X-API-Key: {safe_api_key}
  X-CAPI-Origin: {safe_capi_origin}
  X-CAPI-Timestamp: UNIX_TIMESTAMP
  X-CAPI-Signature: HMAC_SHA256(timestamp + "." + raw_body, api_key)</pre>
        </div>

        <h3 style="color:#fff;font-size:16px;margin:0 0 10px 0;">২. Purchase payload example</h3>
        <div style="position:relative;margin-bottom:22px;">
          <button class="btn-sm btn-outline" onclick="copyText('custom_purchase_payload')" style="position:absolute;top:12px;right:12px;">Copy</button>
          <pre class="instr-box" id="custom_purchase_payload" style="padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#93c5fd;font-size:13px;margin:0;">{{
  "data": [{{
    "event_name": "Purchase",
    "event_time": 1715000000,
    "event_id": "order_1001",
    "event_source_url": "https://example.com/thank-you/1001",
    "action_source": "website",
    "user_data": {{
      "em": ["customer@example.com"],
      "ph": ["017xxxxxxxx"],
      "client_ip_address": "USER_IP",
      "client_user_agent": "USER_BROWSER_USER_AGENT",
      "fbp": "fb.1.xxxxx",
      "fbc": "fb.1.xxxxx",
      "ttp": "tiktok_browser_id",
      "ttclid": "tiktok_click_id"
    }},
    "custom_data": {{
      "value": 1500,
      "currency": "BDT",
      "content_ids": ["PRODUCT_ID_123"],
      "content_type": "product",
      "num_items": 1,
      "order_id": "1001"
    }}
  }}]
}}</pre>
        </div>

        <h3 style="color:#fff;font-size:16px;margin:0 0 10px 0;">৩. cURL test</h3>
        <div style="position:relative;margin-bottom:22px;">
          <button class="btn-sm btn-outline" onclick="copyText('curl_ex')" style="position:absolute;top:12px;right:12px;">Copy</button>
          <pre class="instr-box" id="curl_ex" style="padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#93c5fd;font-size:13px;margin:0;">curl -X POST "{safe_endpoint}" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: {safe_api_key}" \
  -d '{{
    "data": [{{
      "event_name": "Purchase",
      "event_time": 1715000000,
      "event_id": "order_1001",
      "event_source_url": "https://example.com/thank-you/1001",
      "action_source": "website",
      "user_data": {{
        "em": ["customer@example.com"],
        "ph": ["017xxxxxxxx"],
        "client_ip_address": "203.0.113.10",
        "client_user_agent": "Mozilla/5.0"
      }},
      "custom_data": {{
        "value": 1500,
        "currency": "BDT",
        "content_ids": ["123"],
        "content_type": "product",
        "order_id": "1001"
      }}
    }}]
  }}'</pre>
        </div>

        <h3 style="color:#fff;font-size:16px;margin:0 0 10px 0;">৪. Browser tracker option</h3>
        <p>যাদের backend integration করা কঠিন, তারা public tracker key দিয়ে browser script বসাতে পারে। এই key browser-safe, কিন্তু server API key browser-এ দেওয়া যাবে না।</p>
        <div style="position:relative;margin-bottom:22px;">
          <button class="btn-sm btn-outline" onclick="copyText('custom_browser_script')" style="position:absolute;top:12px;right:12px;">Copy</button>
          <pre class="instr-box" id="custom_browser_script" style="padding:16px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.05);color:#93c5fd;font-size:13px;margin:0;">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;

&lt;script&gt;
capi('setUser', {{
  email: 'customer@example.com',
  phone: '+8801XXXXXXXXX'
}});

capi('track', 'ViewContent', {{
  content_ids: ['123'],
  content_type: 'product',
  value: 1200,
  currency: 'BDT'
}});
&lt;/script&gt;</pre>
        </div>

        <h3 style="color:#fff;font-size:16px;margin:0 0 10px 0;">৫. Must-follow rules</h3>
        <ul style="margin:0;padding-left:18px;display:grid;gap:8px;">
          <li><code>event_id</code> unique হতে হবে। Purchase হলে <code>order_1001</code> type ID ব্যবহার করুন।</li>
          <li><code>content_ids</code> Facebook/TikTok catalog product ID-এর সাথে exact match করতে হবে।</li>
          <li><code>currency</code> ISO code হবে, যেমন <code>BDT</code>, <code>USD</code>।</li>
          <li><code>client_ip_address</code> এবং <code>client_user_agent</code> দিলে match quality ভালো হয়।</li>
          <li>Email/phone raw দিলেও server auto SHA-256 hash করবে। আগে hash করা থাকলেও accept করবে।</li>
          <li>একই event browser এবং server দুদিক থেকে পাঠালে একই <code>event_id</code> দিন, না হলে duplicate হতে পারে।</li>
        </ul>
      </div>
    </div>

    <!-- TESTING TAB -->
    <div id="tab-test" class="tab-content card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-title">Testing Guide</div>
      </div>
      <div style="padding:24px;color:var(--text-muted);font-size:14px;line-height:1.6;">
        <ol style="margin:0;padding-left:20px;display:grid;gap:12px;">
          <li>Go to <strong>Facebook Events Manager</strong> → Your Pixel → <strong>Test Events</strong> tab.</li>
          <li>Copy your unique Test Code (e.g. <code>TEST12345</code>).</li>
          <li>In this Admin Dashboard, Edit the Client and paste the code in the <strong>Test Event Code</strong> field.</li>
          <li>Trigger events on your website. They will show up in the FB Test Events tab in real-time.</li>
          <li><strong style="color:#f87171">Important:</strong> Once testing is done, clear the Test Event Code from the Admin Panel to resume live tracking.</li>
        </ol>
      </div>
    </div>
    
    <script>
    function openTab(evt, tabId) {{
      var i, tc, tl;
      tc = document.getElementsByClassName("tab-content");
      for (i = 0; i < tc.length; i++) {{ tc[i].className = tc[i].className.replace(" active", ""); }}
      tl = document.getElementsByClassName("tab-btn");
      for (i = 0; i < tl.length; i++) {{ tl[i].className = tl[i].className.replace(" active", ""); }}
      document.getElementById(tabId).className += " active";
      evt.currentTarget.className += " active";
    }}
    
    function generateEventCode() {{
        var ev = document.getElementById('event_selector').value;
        var code = "";
        var fbEvent = "";
        var params = "";
        
        switch(ev) {{
            case 'page_view': fbEvent = 'PageView'; break;
            case 'session_start': fbEvent = 'PageView'; params = ", {{custom_event: 'session_start'}}"; break;
            case 'user_signup': fbEvent = 'CompleteRegistration'; break;
            case 'user_login': fbEvent = 'Login'; break;
            case 'view_item': fbEvent = 'ViewContent'; params = ", {{value: 100, currency: 'BDT', content_ids: ['ID-123'], content_type: 'product'}}"; break;
            case 'add_to_cart': fbEvent = 'AddToCart'; params = ", {{value: 100, currency: 'BDT', content_ids: ['ID-123']}}"; break;
            case 'begin_checkout': fbEvent = 'InitiateCheckout'; params = ", {{value: 500, currency: 'BDT'}}"; break;
            case 'purchase': fbEvent = 'Purchase'; params = ", {{value: 1500, currency: 'BDT', content_ids: ['ID-123'], order_id: 'ORD-001'}}"; break;
            case 'lead': fbEvent = 'Lead'; break;
        }}
        
        code = "<script>\n  // Event: " + ev + "\n  capi('track', '" + fbEvent + "'" + params + ");\n</scr" + "ipt>";
        
        document.getElementById('generated_code_box').innerText = code;
        document.getElementById('code_result_area').style.display = 'block';
    }}
    </script>
    """
    return HTMLResponse(base_html(f"Instructions — {client.name}", body))


async def rotate_client_key(
    db: AsyncSession,
    request: Request,
    username: str,
    client_id: int,
    key_type: str,
) -> RedirectResponse:
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    old_api_key = client.api_key
    if key_type == "api":
        client.api_key = secrets.token_urlsafe(32)
        message = "API key rotated. Update WordPress plugin/server integrations."
        action = "client.api_key_rotated"
    elif key_type == "public":
        client.public_key = secrets.token_urlsafe(24)
        message = "Public tracker key rotated. Update t.js script URLs."
        action = "client.public_key_rotated"
    elif key_type == "portal":
        client.portal_key = secrets.token_urlsafe(24)
        message = "Portal login key rotated."
        action = "client.portal_key_rotated"
    else:
        raise HTTPException(status_code=400, detail="Invalid key type")

    await log_admin_action(db, request, username, action, client_id)
    await db.commit()

    from app.dependencies import clear_client_cache
    clear_client_cache(old_api_key)

    return admin_redirect(message)


@router.post("/admin/client/{client_id}/rotate-api-key", include_in_schema=False)
async def rotate_api_key(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)
    return await rotate_client_key(db, request, username, client_id, "api")


@router.post("/admin/client/{client_id}/rotate-public-key", include_in_schema=False)
async def rotate_public_key(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)
    return await rotate_client_key(db, request, username, client_id, "public")


@router.post("/admin/client/{client_id}/rotate-portal-key", include_in_schema=False)
async def rotate_portal_key(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)
    return await rotate_client_key(db, request, username, client_id, "portal")


@router.post("/admin/client/{client_id}/deactivate", include_in_schema=False)
async def deactivate_client(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)

    result = await db.execute(update(Client).where(Client.id == client_id).values(is_active=False).returning(Client.api_key))
    api_key = result.scalar()
    await log_admin_action(db, request, username, "client.deactivated", client_id)
    await db.commit()
    
    if api_key:
        from app.dependencies import clear_client_cache
        clear_client_cache(api_key)
        
    return admin_redirect("ক্লায়েন্ট Deactivate করা হয়েছে")


@router.post("/admin/client/{client_id}/activate", include_in_schema=False)
async def activate_client(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)

    result = await db.execute(update(Client).where(Client.id == client_id).values(is_active=True).returning(Client.api_key))
    api_key = result.scalar()
    await log_admin_action(db, request, username, "client.activated", client_id)
    await db.commit()
    
    if api_key:
        from app.dependencies import clear_client_cache
        clear_client_cache(api_key)
        
    return admin_redirect("ক্লায়েন্ট Activate করা হয়েছে")


# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/admin/client/{client_id}/delete", include_in_schema=False)
async def delete_client(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)

    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        return admin_redirect("Client not found", "error")

    client_name = client.name
    api_key = client.api_key

    await db.execute(sql_delete(EventOutbox).where(EventOutbox.client_id == client_id))
    await db.execute(sql_delete(FailedEvent).where(FailedEvent.client_id == client_id))
    await db.execute(sql_delete(PendingEvent).where(PendingEvent.client_id == client_id))
    await db.execute(sql_delete(EventDedup).where(EventDedup.client_id == client_id))
    await db.execute(sql_delete(UsageCounter).where(UsageCounter.client_id == client_id))
    await db.execute(sql_delete(EventLog).where(EventLog.client_id == client_id))
    await db.delete(client)
    await log_admin_action(db, request, username, "client.deleted", client_id, f"Deleted client: {client_name}")
    await db.commit()

    if api_key:
        from app.dependencies import clear_client_cache
        clear_client_cache(api_key)

    return admin_redirect(f"Client deleted: {client_name}")


# CLIENTS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/clients", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("10/minute")
async def admin_clients(
    request: Request,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
    msg: str = "",
    msg_type: str = "success",
):
    csrf_token = create_admin_csrf_token(username)
    result = await db.execute(select(Client).order_by(Client.created_at.desc()))
    clients = result.scalars().all()
    active_count = sum(1 for c in clients if c.is_active)
    inactive_count = len(clients) - active_count

    from datetime import datetime, timezone
    from sqlalchemy import func as sql_func, and_
    from app.models.event_log import EventLog
    from app.models.usage_counter import UsageCounter
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)
    monthly_key_prefix = f"monthly:{now.strftime('%Y-%m')}"

    # Per-client events today
    client_events_r = await db.execute(
        select(EventLog.client_id, sql_func.coalesce(sql_func.sum(EventLog.event_count), 0))
        .where(and_(EventLog.status == "success", EventLog.created_at >= today))
        .group_by(EventLog.client_id)
    )
    client_events_map = {row[0]: row[1] for row in client_events_r}

    # Per-client monthly usage
    monthly_usage_r = await db.execute(
        select(UsageCounter.client_id, UsageCounter.count)
        .where(UsageCounter.window_key == monthly_key_prefix)
    )
    monthly_usage_map = {row[0]: row[1] for row in monthly_usage_r}

    # Stats bar
    stats_html = f"""
    <div class="page-header">
      <div>
        <h1 class="page-title">Client Management</h1>
        <p class="page-sub">Manage all CAPI client integrations and monthly quotas.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-primary" onclick="window.location.href='/api/v1/admin'">
          <svg style="width:16px;height:16px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg> Add Client
        </button>
      </div>
    </div>
    <div class="metrics-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 24px;">
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-blue"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg></div>
          <span class="m-title">Total Clients</span>
        </div>
        <div class="metric-value">{len(clients)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-purple"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></div>
          <span class="m-title">Active</span>
        </div>
        <div class="metric-value" style="color:#34d399">{active_count}</div>
      </div>
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-red"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></div>
          <span class="m-title">Inactive</span>
        </div>
        <div class="metric-value" style="color:#f87171">{inactive_count}</div>
      </div>
    </div>
    """

    # Client cards with monthly usage
    if clients:
        cards = ""
        for c in clients:
            safe_name = html.escape(c.name)
            safe_pixel = html.escape(c.pixel_id)
            safe_key = html.escape(c.api_key, quote=True)
            safe_key_masked = html.escape(mask_secret(c.api_key))
            c_events = client_events_map.get(c.id, 0)
            m_usage = monthly_usage_map.get(c.id, 0)
            m_limit = c.monthly_limit or 50000
            usage_pct = min(round(m_usage / m_limit * 100, 1), 100) if m_limit > 0 else 0
            status_badge = '<span class="status-badge status-healthy">Active</span>' if c.is_active else '<span class="status-badge status-degraded">Inactive</span>'
            toggle_action = "deactivate" if c.is_active else "activate"
            toggle_label = "Deactivate" if c.is_active else "Activate"
            domain_text = html.escape(display_domain_url(c.domain)) if c.domain else "—"
            created = c.created_at.strftime("%Y-%m-%d") if c.created_at else "—"

            # Usage bar color
            bar_color = "#34d399" if usage_pct < 70 else ("#facc15" if usage_pct < 90 else "#ef4444")
            usage_label_color = bar_color

            cards += f"""
            <div class="card" style="margin-bottom:16px;">
              <div class="card-header">
                <div>
                  <h2 class="card-title" style="margin-bottom:4px">{safe_name}</h2>
                  <span style="font-size:12px;color:var(--text-muted)">Pixel: {safe_pixel} · Created: {created}</span>
                </div>
                <div style="display:flex;align-items:center;gap:8px">{status_badge}</div>
              </div>
              <div style="padding:20px;">
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:20px;">
                  <div><div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px">Events Today</div><div style="font-size:18px;font-weight:700;color:#34d399">{c_events:,}</div></div>
                  <div><div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px">Domain</div><div style="font-size:13px;color:#fff">{domain_text}</div></div>
                  <div><div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px">API Key</div>
                    <div class="api-key-cell" style="max-width:100%">
                      <span id="ck_{c.id}" data-secret="{safe_key}" data-masked="{safe_key_masked}" data-hidden="1">{safe_key_masked}</span>
                      <button class="copy-icon" onclick="copyText('ck_{c.id}')" title="Copy">📋</button>
                    </div>
                  </div>
                </div>

                <!-- Monthly Usage Section -->
                <div style="background:rgba(0,0,0,0.2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                    <span style="font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase">📊 Monthly Usage</span>
                    <span style="font-size:13px;font-weight:700;color:{usage_label_color}">{m_usage:,} / {m_limit:,} <span style="font-size:11px;color:var(--text-muted)">({usage_pct}%)</span></span>
                  </div>
                  <div style="width:100%;height:8px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden">
                    <div style="width:{usage_pct}%;height:100%;background:{bar_color};border-radius:4px;transition:width 0.5s ease"></div>
                  </div>
                  <div style="display:flex;justify-content:space-between;margin-top:10px;align-items:center">
                    <span style="font-size:11px;color:var(--text-muted)">Resets on 1st of next month</span>
                    <form method="post" action="/api/v1/admin/client/{c.id}/update-monthly-limit" style="display:flex;gap:6px;align-items:center;margin:0">
                      <input type="hidden" name="csrf_token" value="{csrf_token}">
                      <input type="number" name="monthly_limit" value="{m_limit}" min="0" step="1000" style="width:100px;padding:4px 8px;background:rgba(0,0,0,0.3);border:1px solid var(--border);border-radius:4px;color:#fff;font-size:12px;text-align:right">
                      <button type="submit" class="btn btn-outline" style="font-size:11px;padding:4px 10px">Update</button>
                    </form>
                  </div>
                </div>

                <div style="display:flex;gap:8px;flex-wrap:wrap;border-top:1px solid var(--border);padding-top:16px">
                  <a href="/api/v1/admin/client/{c.id}/instructions" class="btn btn-outline">📋 Instructions</a>
                  <a href="/api/v1/admin/client/{c.id}/edit" class="btn btn-primary">✏️ Edit</a>
                  <form method="post" action="/api/v1/admin/client/{c.id}/{toggle_action}" style="margin:0">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline" style="color:var(--danger);border-color:var(--danger-bg);background:rgba(239,68,68,0.05)">{toggle_label}</button>
                  </form>
                  <form method="post" action="/api/v1/admin/client/{c.id}/rotate-api-key" style="margin:0" onsubmit="return confirm('Rotate server API key? Plugin/server integrations must be updated.')">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline" style="color:var(--danger);border-color:var(--danger-bg);background:rgba(239,68,68,0.05)">Rotate API Key</button>
                  </form>
                  <form method="post" action="/api/v1/admin/client/{c.id}/rotate-public-key" style="margin:0" onsubmit="return confirm('Rotate browser tracker public key? t.js URLs must be updated.')">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline">Rotate Public Key</button>
                  </form>
                  <form method="post" action="/api/v1/admin/client/{c.id}/rotate-portal-key" style="margin:0" onsubmit="return confirm('Rotate client portal login key?')">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline">Rotate Portal Key</button>
                  </form>
                  <form method="post" action="/api/v1/admin/client/{c.id}/delete" style="margin:0" onsubmit="return confirm('Permanently delete this client? This will remove logs, outbox, pending orders and usage data for this client.')">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline" style="color:var(--danger);border-color:var(--danger-bg);background:rgba(239,68,68,0.05)">Delete Client</button>
                  </form>
                </div>
              </div>
            </div>"""
        client_html = cards
    else:
        client_html = """
        <div class="card">
          <div style="padding:40px 20px;text-align:center;color:var(--text-muted)">
            <div style="font-size:32px;margin-bottom:12px">📭</div>
            <p>No clients found. Add one from the Dashboard.</p>
          </div>
        </div>"""

    body = f"""
    {stats_html}
    {client_html}
    """
    return HTMLResponse(base_html("Clients", body, msg, msg_type, active_page="clients"))


# ═══════════════════════════════════════════════════════════════════════════════
# EDIT CLIENT — GET & POST
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/client/{client_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_client_form(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
    msg: str = "",
    msg_type: str = "success",
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    csrf_token = create_admin_csrf_token(username)
    safe_name = html.escape(client.name or "", quote=True)
    safe_pixel = html.escape(client.pixel_id or "", quote=True)
    safe_domain = html.escape(display_domain_url(client.domain), quote=True)
    safe_test_code = html.escape(client.test_event_code or "", quote=True)
    safe_tiktok_pixel = html.escape(client.tiktok_pixel_id or "", quote=True)
    safe_tiktok_test_code = html.escape(client.tiktok_test_event_code or "", quote=True)
    safe_ga4_id = html.escape(client.ga4_measurement_id or "", quote=True)
    safe_webhook = html.escape(client.webhook_url or "", quote=True)
    has_access_token = bool(client.access_token)
    has_tiktok_token = bool(client.tiktok_access_token)
    has_ga4_secret = bool(client.ga4_api_secret)
    fb_enabled_checked = 'checked' if getattr(client, 'enable_facebook', True) else ''
    tiktok_enabled_checked = 'checked' if getattr(client, 'enable_tiktok', True) else ''
    ga4_enabled_checked = 'checked' if getattr(client, 'enable_ga4', True) else ''
    deferred_checked = 'checked' if getattr(client, 'deferred_purchase', False) else ''

    body = f"""
    <div class="page-header" style="margin-bottom:24px;">
      <div>
        <h1 class="page-title">✏️ Edit Client</h1>
        <p class="page-sub">Update settings for <strong>{safe_name}</strong></p>
      </div>
      <div class="header-actions">
        <a href="/api/v1/admin/clients" class="btn btn-outline">← Back to Clients</a>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h2 class="card-title">🔧 Client Configuration</h2></div>
      <div style="padding:24px;">
        <form method="post" action="/api/v1/admin/client/{client_id}/edit">
          <input type="hidden" name="csrf_token" value="{csrf_token}">

          <div class="layout-grid" style="grid-template-columns: 1fr 1fr; gap: 28px;">

            <!-- LEFT COLUMN: Core Settings -->
            <div>
              <div style="font-size:13px;color:#7e57c2;font-weight:700;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:16px;">🔵 Core Settings (Facebook CAPI)</div>

              <div class="form-group">
                <label>ক্লায়েন্টের নাম *</label>
                <input type="text" name="name" value="{safe_name}" required>
              </div>

              <div class="form-group">
                <label>Facebook Pixel ID *</label>
                <input type="text" name="pixel_id" value="{safe_pixel}" required>
                <div class="hint">FB Events Manager → Settings → Pixel ID</div>
              </div>

              <div class="form-group">
                <label>CAPI Access Token</label>
                <input type="text" name="access_token" placeholder="{'[Encrypted — paste new to update]' if has_access_token else 'EAAxxxx...'}">
                <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#fff"><input type="checkbox" name="enable_facebook" value="1" {fb_enabled_checked}> Facebook CAPI delivery ON</label>
                <div class="hint" style="color:#facc15">⚠️ খালি রাখলে বর্তমান টোকেন রাখা থাকবে।</div>
              </div>

              <div class="form-group">
                <label>Website URL / Domain (Security)</label>
                <input type="text" name="domain" value="{safe_domain}" placeholder="https://www.buykori.me">
                <div class="hint">🔒 https://, www, বা path দিলেও system clean domain save করবে। শুধু এই ডোমেইন থেকে API Key ব্যবহার করতে পারবে।</div>
              </div>

              <div class="form-group">
                <label>Test Event Code (Optional)</label>
                <input type="text" name="test_event_code" value="{safe_test_code}" placeholder="TEST12345">
                <div class="hint">শুধু টেস্টিংয়ের সময় দিন। লাইভে খালি রাখুন।</div>
              </div>

              <div class="form-group" style="margin-top:16px;">
                <label style="display:flex;align-items:center;gap:10px;cursor:pointer;color:#fff;font-weight:600">
                  <input type="checkbox" name="deferred_purchase" value="1" {deferred_checked} style="width:18px;height:18px;accent-color:#7e57c2;cursor:pointer;">
                  🔄 Deferred Purchase সচল রাখুন
                </label>
                <div class="hint">COD ব্যবসার জন্য — Purchase event অর্ডার কনফার্মের পরে যাবে।</div>
              </div>

              <div class="form-group">
                <label>Custom Webhook URL (Outbound)</label>
                <input type="text" name="webhook_url" value="{safe_webhook}" placeholder="https://your-server.com/webhook">
                <div class="hint">প্রতিটি event-এ এই URL-এ data forward হবে।</div>
              </div>
            </div>

            <!-- RIGHT COLUMN: Optional Integrations -->
            <div>
              <div style="font-size:13px;color:#9575cd;font-weight:700;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:16px;">🎵 TikTok CAPI (Optional)</div>

              <div class="form-group">
                <label>TikTok Pixel ID</label>
                <input type="text" name="tiktok_pixel_id" value="{safe_tiktok_pixel}" placeholder="C1234567890">
              </div>

              <div class="form-group">
                <label>TikTok Access Token</label>
                <input type="text" name="tiktok_access_token" placeholder="{'[Encrypted — paste new to update]' if has_tiktok_token else 'Paste TikTok token...'}">
                <div class="hint" style="color:#facc15">⚠️ খালি রাখলে বর্তমান টোকেন রাখা থাকবে।</div>
              </div>

              <div class="form-group">
                <label>TikTok Test Event Code (Optional)</label>
                <input type="text" name="tiktok_test_event_code" value="{safe_tiktok_test_code}" placeholder="TEST38483">
                <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#fff"><input type="checkbox" name="enable_tiktok" value="1" {tiktok_enabled_checked}> TikTok CAPI delivery ON</label>
                <div class="hint">TikTok Events Manager → Test Events থেকে কোড দিন। লাইভে খালি রাখুন।</div>
              </div>

              <div style="font-size:13px;color:#00a1f1;font-weight:700;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:16px;margin-top:24px;">📊 GA4 Server-Side (Optional)</div>

              <div class="form-group">
                <label>GA4 Measurement ID</label>
                <input type="text" name="ga4_measurement_id" value="{safe_ga4_id}" placeholder="G-XXXXXXXXXX">
              </div>

              <div class="form-group">
                <label>GA4 API Secret</label>
                <input type="text" name="ga4_api_secret" placeholder="{'[Encrypted — paste new to update]' if has_ga4_secret else 'Paste GA4 API Secret...'}">
                <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#fff"><input type="checkbox" name="enable_ga4" value="1" {ga4_enabled_checked}> GA4 server-side delivery ON</label>
                <div class="hint" style="color:#facc15">⚠️ খালি রাখলে বর্তমান secret রাখা থাকবে।</div>
              </div>
            </div>

          </div>

          <div style="margin-top:28px;border-top:1px solid var(--border);padding-top:20px;display:flex;justify-content:flex-end;gap:12px;">
            <a href="/api/v1/admin/clients" class="btn btn-outline">বাতিল করুন</a>
            <button type="submit" class="btn btn-primary">💾 পরিবর্তন সংরক্ষণ করুন</button>
          </div>
        </form>
      </div>
    </div>
    """
    return HTMLResponse(base_html(f"Edit — {client.name}", body, msg, msg_type, active_page="clients"))


@router.post("/admin/client/{client_id}/edit", include_in_schema=False)
async def edit_client_submit(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    name: str = Form(...),
    pixel_id: str = Form(...),
    access_token: str = Form(""),
    test_event_code: str = Form(""),
    domain: str = Form(""),
    tiktok_pixel_id: str = Form(""),
    tiktok_access_token: str = Form(""),
    tiktok_test_event_code: str = Form(""),
    ga4_measurement_id: str = Form(""),
    ga4_api_secret: str = Form(""),
    enable_facebook: str = Form(None),
    enable_tiktok: str = Form(None),
    enable_ga4: str = Form(None),
    deferred_purchase: str = Form(None),
    webhook_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)

    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # ─── Validate ───────────────────────────────────────────────────────────
    name = name.strip()
    pixel_id = pixel_id.strip()
    if not name or len(name) > 100:
        from urllib.parse import urlencode
        q = urlencode({"msg": "নাম ১-১০০ অক্ষরের মধ্যে হতে হবে।", "msg_type": "error"})
        return RedirectResponse(url=f"/api/v1/admin/client/{client_id}/edit?{q}", status_code=303)
    if not pixel_id.isdigit():
        from urllib.parse import urlencode
        q = urlencode({"msg": "Pixel ID শুধু সংখ্যা হতে হবে।", "msg_type": "error"})
        return RedirectResponse(url=f"/api/v1/admin/client/{client_id}/edit?{q}", status_code=303)

    # ─── Domain sanitize ─────────────────────────────────────────────────────
    clean_domain = normalize_domain_input(domain)

    # ─── Webhook validation ──────────────────────────────────────────────────
    clean_webhook = webhook_url.strip() if webhook_url and webhook_url.strip() else None
    if clean_webhook:
        parsed = urlparse(clean_webhook)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            from urllib.parse import urlencode
            q = urlencode({"msg": "Webhook URL must be a valid http(s) URL.", "msg_type": "error"})
            return RedirectResponse(url=f"/api/v1/admin/client/{client_id}/edit?{q}", status_code=303)
        if not _webhook_url_allowed(clean_webhook):
            from urllib.parse import urlencode
            q = urlencode({"msg": "Webhook URL is not allowed.", "msg_type": "error"})
            return RedirectResponse(url=f"/api/v1/admin/client/{client_id}/edit?{q}", status_code=303)

    # ─── Apply updates ───────────────────────────────────────────────────────
    client.name = name
    client.pixel_id = pixel_id
    client.domain = clean_domain
    client.test_event_code = test_event_code.strip() if test_event_code and test_event_code.strip() else None
    client.enable_facebook = (enable_facebook == "1")
    client.enable_tiktok = (enable_tiktok == "1")
    client.enable_ga4 = (enable_ga4 == "1")
    client.deferred_purchase = (deferred_purchase == "1")
    client.webhook_url = clean_webhook
    client.tiktok_pixel_id = tiktok_pixel_id.strip() if tiktok_pixel_id and tiktok_pixel_id.strip() else None
    client.tiktok_test_event_code = tiktok_test_event_code.strip() if tiktok_test_event_code and tiktok_test_event_code.strip() else None
    client.ga4_measurement_id = ga4_measurement_id.strip() if ga4_measurement_id and ga4_measurement_id.strip() else None

    # Only update encrypted tokens if new value was provided
    if access_token and access_token.strip():
        client.access_token = encrypt_token(access_token.strip())
    if tiktok_access_token and tiktok_access_token.strip():
        client.tiktok_access_token = encrypt_token(tiktok_access_token.strip())
    if ga4_api_secret and ga4_api_secret.strip():
        client.ga4_api_secret = encrypt_token(ga4_api_secret.strip())

    await log_admin_action(db, request, username, "client.updated", client_id, f"Client {name} updated")
    await db.commit()

    from app.dependencies import clear_client_cache
    clear_client_cache(client.api_key)

    from urllib.parse import urlencode
    q = urlencode({"msg": f"✅ {name} সফলভাবে আপডেট হয়েছে!", "msg_type": "success"})
    return RedirectResponse(url=f"/api/v1/admin/clients?{q}", status_code=303)


# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE MONTHLY LIMIT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/admin/client/{client_id}/update-monthly-limit", include_in_schema=False)
async def update_monthly_limit(
    client_id: int,
    request: Request,
    username: str = Depends(verify_admin),
    csrf_token: str = Form(...),
    monthly_limit: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_csrf_token(csrf_token, username)

    if monthly_limit < 0:
        from urllib.parse import urlencode
        query = urlencode({"msg": "Monthly limit must be >= 0", "msg_type": "error"})
        return RedirectResponse(url=f"/api/v1/admin/clients?{query}", status_code=303)

    await db.execute(
        update(Client).where(Client.id == client_id).values(monthly_limit=monthly_limit)
    )
    await log_admin_action(db, request, username, "client.monthly_limit_updated", client_id, f"New limit: {monthly_limit:,}")
    await db.commit()

    # Clear cache
    result = await db.execute(select(Client.api_key).where(Client.id == client_id))
    api_key = result.scalar()
    if api_key:
        from app.dependencies import clear_client_cache
        clear_client_cache(api_key)

    from urllib.parse import urlencode
    query = urlencode({"msg": f"Monthly limit updated to {monthly_limit:,} events", "msg_type": "success"})
    return RedirectResponse(url=f"/api/v1/admin/clients?{query}", status_code=303)

# ═══════════════════════════════════════════════════════════════════════════════
# API LOGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/logs", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("10/minute")
async def admin_logs(
    request: Request,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    from sqlalchemy import func as sql_func, and_
    from app.models.event_log import EventLog
    from app.models.failed_event import FailedEvent

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    success_r = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(EventLog.status == "success", EventLog.created_at >= today)
        )
    )
    events_today = success_r.scalar() or 0

    fail_r = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(EventLog.status == "failed", EventLog.created_at >= today)
        )
    )
    failed_today = fail_r.scalar() or 0

    retry_r = await db.execute(
        select(sql_func.count(FailedEvent.id)).where(
            FailedEvent.status.in_(["pending", "retrying"])
        )
    )
    retries = retry_r.scalar() or 0

    total = events_today + failed_today

    # Recent event logs (last 100)
    from sqlalchemy.orm import selectinload
    logs_r = await db.execute(
        select(EventLog).order_by(EventLog.created_at.desc()).limit(100)
    )
    event_logs = logs_r.scalars().all()

    # Client name map
    clients_r = await db.execute(select(Client.id, Client.name))
    client_map = {row[0]: row[1] for row in clients_r}

    # Failed events (last 50)
    failed_r = await db.execute(
        select(FailedEvent).order_by(FailedEvent.created_at.desc()).limit(50)
    )
    failed_events = failed_r.scalars().all()

    # Stats
    header_html = f"""
    <div class="page-header">
      <div>
        <h1 class="page-title">API Event Logs</h1>
        <p class="page-sub">Real-time event processing history and error tracking.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline" onclick="window.location.reload()"><svg style="width:16px;height:16px" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> Refresh</button>
      </div>
    </div>
    <div class="metrics-grid" style="margin-bottom:24px">
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-purple"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></div>
          <span class="m-title">Success (24h)</span>
        </div>
        <div class="metric-value" style="color:#34d399">{events_today:,}</div>
      </div>
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-red"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg></div>
          <span class="m-title">Failed (24h)</span>
        </div>
        <div class="metric-value" style="color:#f87171">{failed_today:,}</div>
      </div>
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-blue"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg></div>
          <span class="m-title">Total (24h)</span>
        </div>
        <div class="metric-value">{total:,}</div>
      </div>
      <div class="metric-card">
        <div class="metric-header">
          <div class="m-icon bg-indigo"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg></div>
          <span class="m-title">Pending Retries</span>
        </div>
        <div class="metric-value" style="color:#facc15">{retries}</div>
      </div>
    </div>
    """

    # Event log table
    if event_logs:
        rows = ""
        for log in event_logs:
            c_name = html.escape(client_map.get(log.client_id, f"#{log.client_id}"))
            e_name = html.escape(log.event_name or "—")
            e_count = log.event_count or 1
            status_cls = "badge-healthy" if log.status == "success" else "badge-degraded"
            status_text = log.status or "unknown"
            ip = html.escape(log.ip_address or "—")
            emq = f"{log.emq_score:.1f}" if log.emq_score else "—"
            created = log.created_at.strftime("%H:%M:%S") if log.created_at else "—"
            rows += f"""
            <tr>
              <td class="code-text">{created}</td>
              <td>{c_name}</td>
              <td><span style="color:#818cf8;font-weight:600">{e_name}</span></td>
              <td class="code-text" style="text-align:center">{e_count}</td>
              <td><span class="badge {status_cls}">{status_text}</span></td>
              <td class="code-text">{ip}</td>
              <td class="code-text">{emq}</td>
            </tr>"""
        event_table = f"""
        <div class="card" style="margin-bottom:24px">
          <div class="card-header"><h2 class="card-title">📡 Recent Events (Last 100)</h2></div>
          <div class="table-responsive">
            <table>
              <thead><tr>
                <th>Time</th><th>Client</th><th>Event</th><th style="text-align:center">Count</th><th>Status</th><th>IP</th><th>EMQ</th>
              </tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </div>"""
    else:
        event_table = """
        <div class="card" style="margin-bottom:24px">
          <div class="card-header"><h2 class="card-title">📡 Recent Events</h2></div>
          <div style="padding:30px;text-align:center;color:var(--text-muted)">No event logs recorded yet.</div>
        </div>"""

    # Failed events table
    if failed_events:
        fail_rows = ""
        for fe in failed_events:
            c_name = html.escape(client_map.get(fe.client_id, f"#{fe.client_id}"))
            err = html.escape((fe.error_message or "—")[:80])
            retries_c = fe.retry_count or 0
            max_r = fe.max_retries or 5
            st = fe.status or "pending"
            st_color = "#facc15" if st == "pending" else ("#818cf8" if st == "retrying" else "#f87171")
            created = fe.created_at.strftime("%Y-%m-%d %H:%M") if fe.created_at else "—"
            fail_rows += f"""
            <tr>
              <td class="code-text">{created}</td>
              <td>{c_name}</td>
              <td style="color:var(--text-muted);font-size:12px;max-width:300px;overflow:hidden;text-overflow:ellipsis">{err}</td>
              <td class="code-text" style="text-align:center">{retries_c}/{max_r}</td>
              <td><span style="color:{st_color};font-weight:600;font-size:12px">{st.upper()}</span></td>
            </tr>"""
        failed_table = f"""
        <div class="card">
          <div class="card-header"><h2 class="card-title">⚠️ Failed Events (Last 50)</h2></div>
          <div class="table-responsive">
            <table>
              <thead><tr>
                <th>Time</th><th>Client</th><th>Error</th><th style="text-align:center">Retries</th><th>Status</th>
              </tr></thead>
              <tbody>{fail_rows}</tbody>
            </table>
          </div>
        </div>"""
    else:
        failed_table = """
        <div class="card">
          <div class="card-header"><h2 class="card-title">⚠️ Failed Events</h2></div>
          <div style="padding:30px;text-align:center;color:var(--text-muted)">No failed events. Everything is running smoothly! 🎉</div>
        </div>"""

    body = f"""
    {header_html}
    {event_table}
    {failed_table}
    """
    return HTMLResponse(base_html("API Logs", body, active_page="logs"))


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/settings", response_class=HTMLResponse, include_in_schema=False)
@limiter.limit("10/minute")
async def admin_settings(
    request: Request,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
):
    import sys

    # Environment checks
    env_checks = {
        "ADMIN_PASSWORD": bool(os.getenv("ADMIN_PASSWORD")),
        "ENCRYPTION_KEY": bool(os.getenv("ENCRYPTION_KEY")),
        "ADMIN_API_KEY": bool(os.getenv("ADMIN_API_KEY")),
        "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
    }

    env_rows = ""
    for key, configured in env_checks.items():
        badge = '<span class="status-badge status-healthy">Configured</span>' if configured else '<span class="status-badge status-degraded">Missing</span>'
        env_rows += f"""
        <tr>
          <td style="font-weight:600">{key}</td>
          <td>{badge}</td>
        </tr>"""

    # System info
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    admin_user = html.escape(ADMIN_USERNAME)

    # Audit logs (last 50)
    audit_r = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50))
    audit_logs = audit_r.scalars().all()

    if audit_logs:
        audit_rows = ""
        for log in audit_logs:
            safe_actor = html.escape(log.actor or "system")
            safe_action = html.escape(log.action or "—")
            safe_details = html.escape((log.details or "—")[:60])
            safe_ip = html.escape(log.ip_address or "—")
            created = log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else "—"
            audit_rows += f"""
            <tr>
              <td class="code-text">{created}</td>
              <td>{safe_actor}</td>
              <td><span style="color:#818cf8">{safe_action}</span></td>
              <td class="code-text">{log.client_id or '—'}</td>
              <td class="code-text">{safe_ip}</td>
              <td style="color:var(--text-muted);font-size:12px">{safe_details}</td>
            </tr>"""
        audit_table = f"""
        <div class="card">
          <div class="card-header"><h2 class="card-title">📋 Full Audit Log (Last 50)</h2></div>
          <div class="table-responsive">
            <table>
              <thead><tr>
                <th>Time</th><th>Actor</th><th>Action</th><th>Client</th><th>IP</th><th>Details</th>
              </tr></thead>
              <tbody>{audit_rows}</tbody>
            </table>
          </div>
        </div>"""
    else:
        audit_table = """
        <div class="card">
          <div class="card-header"><h2 class="card-title">📋 Audit Log</h2></div>
          <div style="padding:30px;text-align:center;color:var(--text-muted)">No audit entries yet.</div>
        </div>"""

    body = f"""
    <div class="page-header">
      <div>
        <h1 class="page-title">System Settings</h1>
        <p class="page-sub">Server configuration, environment status, and admin activity.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-primary" onclick="alert('Settings saved')">Save Changes</button>
      </div>
    </div>

    <div class="layout-grid" style="margin-bottom:24px">
      <div class="card">
        <div class="card-header"><h2 class="card-title">🖥️ System Information</h2></div>
        <div style="padding:20px">
          <table style="width:100%">
            <tr><td style="color:var(--text-muted);padding:8px 0;font-size:13px;width:40%">Python Version</td><td style="padding:8px 0;font-weight:600">{python_ver}</td></tr>
            <tr><td style="color:var(--text-muted);padding:8px 0;font-size:13px">Admin Username</td><td style="padding:8px 0;font-weight:600">{admin_user}</td></tr>
            <tr><td style="color:var(--text-muted);padding:8px 0;font-size:13px">Environment</td><td style="padding:8px 0"><span class="env-badge">PRODUCTION</span></td></tr>
            <tr><td style="color:var(--text-muted);padding:8px 0;font-size:13px">Default Rate Limit</td><td style="padding:8px 0;font-weight:600">5,000 req/min</td></tr>
            <tr><td style="color:var(--text-muted);padding:8px 0;font-size:13px">Default Daily Quota</td><td style="padding:8px 0;font-weight:600">100,000 events</td></tr>
            <tr><td style="color:var(--text-muted);padding:8px 0;font-size:13px">Default Monthly Limit</td><td style="padding:8px 0;font-weight:600">50,000 events</td></tr>
          </table>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h2 class="card-title">🔐 Environment Variables</h2></div>
        <div class="table-responsive">
          <table>
            <thead><tr><th>Variable</th><th>Status</th></tr></thead>
            <tbody>{env_rows}</tbody>
          </table>
        </div>
      </div>
    </div>

    {audit_table}
    """
    return HTMLResponse(base_html("Settings", body, active_page="settings"))
