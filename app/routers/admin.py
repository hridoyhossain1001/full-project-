import os
import html
import secrets
import logging
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import get_db
from app.models.client import Client
from app.security import encrypt_token
from app.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBasic()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise RuntimeError("⛔ ADMIN_PASSWORD environment variable is required!")


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


# ─── HTML TEMPLATES ─────────────────────────────────────────────────────────

STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
  :root {
    --bg-main: #0b0c10;
    --bg-card: rgba(22, 24, 31, 0.7);
    --bg-nav: rgba(11, 12, 16, 0.8);
    --border: rgba(255, 255, 255, 0.08);
    --primary: #7e57c2;
    --primary-hover: #9575cd;
    --text-main: #e2e8f0;
    --text-muted: #94a3b8;
    --accent: #00e676;
    --danger: #ff5252;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
  body {
    background: var(--bg-main);
    color: var(--text-main);
    min-height: 100vh;
    background-image: 
      radial-gradient(circle at 15% 50%, rgba(126, 87, 194, 0.15), transparent 25%),
      radial-gradient(circle at 85% 30%, rgba(0, 230, 118, 0.1), transparent 25%);
    background-attachment: fixed;
  }
  .navbar {
    background: var(--bg-nav);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    gap: 16px;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .navbar .logo { font-size: 22px; font-weight: 700; color: #fff; letter-spacing: 0.5px; }
  .navbar .logo span { color: var(--primary); }
  .navbar .badge {
    background: rgba(126, 87, 194, 0.15);
    color: var(--primary-hover);
    border: 1px solid rgba(126, 87, 194, 0.3);
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }
  .container { max-width: 1100px; margin: 40px auto; padding: 0 24px; }
  .page-title { font-size: 32px; font-weight: 700; color: #fff; margin-bottom: 8px; letter-spacing: -0.5px; }
  .page-sub { color: var(--text-muted); font-size: 15px; margin-bottom: 36px; }
  
  .stat-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .stat-box {
    background: var(--bg-card);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
  }
  .stat-box:hover {
    transform: translateY(-4px);
    box-shadow: 0 10px 25px rgba(0,0,0,0.3);
    border-color: rgba(255,255,255,0.15);
  }
  .stat-box .num { font-size: 32px; font-weight: 700; color: var(--primary-hover); line-height: 1.2; }
  .stat-box .lbl { font-size: 13px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }
  
  .top-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 24px; align-items: stretch; margin-bottom: 24px; }
  .card {
    background: var(--bg-card);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  }
  .card-title {
    font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 24px;
    display: flex; align-items: center; gap: 10px;
  }
  .card-title .icon {
    width: 36px; height: 36px;
    background: rgba(126, 87, 194, 0.15);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
  }
  
  .form-group { margin-bottom: 20px; }
  label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 8px; font-weight: 500; }
  input[type=text], input[type=password] {
    width: 100%; padding: 12px 16px;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--border);
    border-radius: 10px; color: #fff; font-size: 14px;
    transition: all 0.3s ease; outline: none;
  }
  input:focus {
    border-color: var(--primary);
    background: rgba(0, 0, 0, 0.5);
    box-shadow: 0 0 0 3px rgba(126, 87, 194, 0.15);
  }
  .hint { font-size: 11px; color: #64748b; margin-top: 6px; }
  
  .btn {
    width: 100%; padding: 14px;
    background: linear-gradient(135deg, var(--primary), #5e35b1);
    color: #fff; border: none; border-radius: 10px;
    font-size: 15px; font-weight: 600; cursor: pointer;
    transition: all 0.3s ease; margin-top: 8px;
    box-shadow: 0 4px 15px rgba(126, 87, 194, 0.3);
  }
  .btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(126, 87, 194, 0.4);
    filter: brightness(1.1);
  }
  
  .client-table { width: 100%; border-collapse: separate; border-spacing: 0; }
  .client-table th {
    text-align: left; padding: 12px 16px; font-size: 12px; color: var(--text-muted);
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 1px solid var(--border);
  }
  .client-table td {
    padding: 16px; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.03); vertical-align: middle;
  }
  .client-table tr:hover td { background: rgba(255,255,255,0.02); }
  
  .badge-active {
    background: rgba(0, 230, 118, 0.15); color: var(--accent);
    border: 1px solid rgba(0, 230, 118, 0.3); padding: 4px 12px;
    border-radius: 20px; font-size: 12px; font-weight: 600;
  }
  .badge-inactive {
    background: rgba(255, 82, 82, 0.15); color: var(--danger);
    border: 1px solid rgba(255, 82, 82, 0.3); padding: 4px 12px;
    border-radius: 20px; font-size: 12px; font-weight: 600;
  }
  .api-key-cell {
    font-family: monospace; font-size: 12px; color: #888;
    background: rgba(0,0,0,0.3); padding: 6px 10px; border-radius: 6px;
    display: inline-flex; align-items: center; justify-content: space-between; gap: 10px;
    width: 200px;
  }
  .api-key-text {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .copy-icon {
    background: none; border: none; color: var(--primary-hover); cursor: pointer;
    font-size: 14px; transition: color 0.2s;
  }
  .copy-icon:hover { color: #fff; }
  
  .btn-sm {
    padding: 8px 16px; font-size: 13px; border-radius: 8px; border: none;
    cursor: pointer; font-weight: 600; transition: all 0.3s ease; display: inline-flex; align-items: center; justify-content: center;
  }
  .btn-danger {
    background: rgba(255, 82, 82, 0.1); color: var(--danger);
    border: 1px solid rgba(255, 82, 82, 0.2);
  }
  .btn-danger:hover { background: var(--danger); color: #fff; transform: translateY(-1px); box-shadow: 0 4px 10px rgba(255, 82, 82, 0.3); }
  
  .btn-info {
    background: rgba(126, 87, 194, 0.1); color: var(--primary-hover);
    border: 1px solid rgba(126, 87, 194, 0.2);
  }
  .btn-info:hover { background: var(--primary); color: #fff; transform: translateY(-1px); box-shadow: 0 4px 10px rgba(126, 87, 194, 0.3); }
  
  .alert { padding: 16px 20px; border-radius: 12px; margin-bottom: 24px; font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 10px; transition: opacity 0.5s ease; }
  .alert-success { background: rgba(0, 230, 118, 0.1); border: 1px solid rgba(0, 230, 118, 0.2); color: var(--accent); }
  .alert-error { background: rgba(255, 82, 82, 0.1); border: 1px solid rgba(255, 82, 82, 0.2); color: var(--danger); }
  
  .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); }
  .empty-state .big { font-size: 48px; margin-bottom: 16px; opacity: 0.5; }
  
  .instr-box {
    background: rgba(0, 0, 0, 0.4); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; font-family: monospace; font-size: 13px; color: #cbd5e1;
    white-space: pre-wrap; word-break: break-all; margin-top: 12px; position: relative;
  }
  .copy-btn {
    background: rgba(255,255,255,0.1); color: #fff; border: none; border-radius: 6px;
    padding: 6px 12px; font-size: 12px; cursor: pointer; transition: all 0.2s ease; float: right; margin-top: -4px;
  }
  .copy-btn:hover { background: var(--primary); }
  .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; overflow-x: auto; }
  .tab-btn { background: none; border: none; color: var(--text-muted); font-size: 15px; font-weight: 600; cursor: pointer; padding: 8px 16px; border-radius: 8px; transition: all 0.3s; white-space: nowrap; }
  .tab-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
  .tab-btn.active { color: #fff; background: rgba(126, 87, 194, 0.2); border: 1px solid rgba(126, 87, 194, 0.4); }
  .tab-content { display: none; animation: fadeIn 0.3s ease; }
  .tab-content.active { display: block; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
</style>
"""


def base_html(title: str, body: str, msg: str = "", msg_type: str = "success") -> str:
    alert_html = ""
    safe_title = html.escape(title, quote=True)
    if msg:
        safe_msg = html.escape(msg)
        safe_type = "error" if msg_type == "error" else "success"
        alert_html = f'<div class="alert alert-{safe_type}">{safe_msg}</div>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title} — CAPI Gateway</title>
  {STYLE}
</head>
<body>
<nav class="navbar">
  <div class="logo">CAPI<span>Gateway</span></div>
  <div class="badge">Admin Panel</div>
</nav>
<div class="container">
  {alert_html}
  {body}
</div>
<script>
function copyText(id){{
  var t = document.getElementById(id);
  navigator.clipboard.writeText(t.innerText || t.value);
  event.target.innerText = 'Copied!';
  setTimeout(()=>event.target.innerText='Copy',1500);
}}
</script>
<script>
  setTimeout(() => {{
    const alert = document.querySelector('.alert');
    if (alert) {{
      alert.style.opacity = '0';
      setTimeout(() => alert.style.display = 'none', 500);
    }}
  }}, 5000);
</script>
</body>
</html>"""


def admin_redirect(msg: str, msg_type: str = "success") -> RedirectResponse:
    query = urlencode({"msg": msg, "msg_type": msg_type})
    return RedirectResponse(url=f"/api/v1/admin?{query}", status_code=303)


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
    result = await db.execute(select(Client).order_by(Client.created_at.desc()))
    clients = result.scalars().all()
    active_count = sum(1 for c in clients if c.is_active)

    # ─── Event Analytics Query ────────────────────────────────────────────
    from datetime import datetime, timezone
    from sqlalchemy import func as sql_func, and_
    from app.models.event_log import EventLog
    from app.models.failed_event import FailedEvent

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

    total_calls = events_today + failed_today
    success_rate = round(events_today / total_calls * 100, 1) if total_calls > 0 else 100.0

    # ─── Stats ─────────────────────────────────────────────────────────────
    stats = f"""
    <div class="left-col">
      <h1 class="page-title">Dashboard</h1>
      <p class="page-sub">আপনার সকল ক্লায়েন্ট এখান থেকে ম্যানেজ করুন<br><br>
        <a href="/client" target="_blank" style="display:inline-flex;align-items:center;gap:6px;background:rgba(126,87,194,0.15);color:#9575cd;padding:6px 12px;border-radius:6px;font-size:13px;text-decoration:none;border:1px solid rgba(126,87,194,0.3);">
          <span style="font-size:14px">💻</span> Client Portal Login Page
        </a>
      </p>
      <div class="stat-row">
        <div class="stat-box"><div class="num">{len(clients)}</div><div class="lbl">Total Clients</div></div>
        <div class="stat-box"><div class="num">{active_count}</div><div class="lbl">Active Clients</div></div>
      </div>
      <div class="stat-row">
        <div class="stat-box"><div class="num" style="color:#00c853">{events_today:,}</div><div class="lbl">📊 আজকের Events</div></div>
        <div class="stat-box"><div class="num" style="color:#ff4d4d">{failed_today}</div><div class="lbl">❌ Failed Today</div></div>
      </div>
      <div class="stat-row">
        <div class="stat-box"><div class="num" style="color:#6c63ff">{success_rate}%</div><div class="lbl">✅ Success Rate</div></div>
        <div class="stat-box"><div class="num" style="color:#ffab00">{retries}</div><div class="lbl">🔄 Pending Retries</div></div>
      </div>
    </div>
    """

    # ─── Add Client Form ───────────────────────────────────────────────────
    add_form = """
    <div class="right-col">
      <div class="card" style="height: 100%;">
        <div class="card-title"><span class="icon">➕</span> নতুন ক্লায়েন্ট যোগ করুন</div>
        <form method="post" action="/api/v1/admin/add-client">
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
            <div class="hint">Events Manager → Settings → Conversions API → Generate Access Token</div>
          </div>
          <div class="form-group">
            <label>Website Domain (সিকিউরিটির জন্য)</label>
            <input type="text" name="domain" placeholder="buykori.me">
            <div class="hint">🔒 এই ডোমেইন ছাড়া অন্য কেউ API Key ব্যবহার করতে পারবে না। খালি রাখলে সব ডোমেইন থেকে কাজ করবে।</div>
          </div>
          <div class="form-group">
            <label>Test Event Code (Optional)</label>
            <input type="text" name="test_event_code" placeholder="TEST12345">
            <div class="hint">শুধু টেস্টিং করার সময় দিন, লাইভে খালি রাখুন</div>
          </div>
          <div style="border-top:1px solid var(--border);margin:16px 0;padding-top:16px">
            <div style="font-size:13px;color:#9575cd;margin-bottom:12px;font-weight:600">🎵 TikTok CAPI (Optional)</div>
          </div>
          <div class="form-group">
            <label>TikTok Pixel ID</label>
            <input type="text" name="tiktok_pixel_id" placeholder="C1234567890">
            <div class="hint">TikTok Events Manager → Pixel ID</div>
          </div>
          <div class="form-group">
            <label>TikTok Access Token</label>
            <input type="text" name="tiktok_access_token" placeholder="">
            <div class="hint">TikTok Business → Settings → Access Token</div>
          </div>
          <div style="border-top:1px solid var(--border);margin:16px 0;padding-top:16px">
            <div style="font-size:13px;color:#00a1f1;margin-bottom:12px;font-weight:600">📊 GA4 Server-Side (Optional)</div>
          </div>
          <div class="form-group">
            <label>GA4 Measurement ID</label>
            <input type="text" name="ga4_measurement_id" placeholder="G-XXXXXXXXXX">
            <div class="hint">GA4 Data Streams → Measurement ID</div>
          </div>
          <div class="form-group">
            <label>GA4 API Secret</label>
            <input type="text" name="ga4_api_secret" placeholder="">
            <div class="hint">GA4 Data Streams → Measurement Protocol API Secrets</div>
          </div>
          <button type="submit" class="btn">✅ ক্লায়েন্ট যোগ করুন</button>
        </form>
      </div>
    </div>
    """

    # ─── Client List ───────────────────────────────────────────────────────
    if clients:
        rows = ""
        for c in clients:
            status_badge = (
                '<span class="badge-active">Active</span>'
                if c.is_active
                else '<span class="badge-inactive">Inactive</span>'
            )
            toggle_action = "deactivate" if c.is_active else "activate"
            toggle_label = "❌ Deactivate" if c.is_active else "✅ Activate"
            safe_name = html.escape(c.name)
            safe_pixel = html.escape(c.pixel_id)
            safe_key = html.escape(c.api_key)
            c_events = client_events_map.get(c.id, 0)
            rows += f"""
            <tr>
              <td><strong>{safe_name}</strong><br><span style="color:#555;font-size:11px">{safe_pixel}</span></td>
              <td>{status_badge}</td>
              <td style="color:#00c853;font-weight:600;">{c_events:,}</td>
              <td>
                <div class="api-key-cell" title="{safe_key}">
                  <span class="api-key-text">{safe_key[:20]}...</span>
                  <button class="copy-icon" onclick="navigator.clipboard.writeText('{safe_key}'); this.innerText='✅'; setTimeout(()=>this.innerText='📋', 2000);" title="Copy Full API Key">📋</button>
                </div>
              </td>
              <td>
                <a href="/api/v1/admin/client/{c.id}/instructions" style="text-decoration:none">
                  <button class="btn-sm btn-info">📋 Instructions</button>
                </a>
                &nbsp;
                <form method="post" action="/api/v1/admin/client/{c.id}/{toggle_action}" style="display:inline">
                  <button type="submit" class="btn-sm btn-danger">{toggle_label}</button>
                </form>
              </td>
            </tr>"""
        client_table = f"""
        <div class="card">
          <div class="card-title"><span class="icon">👥</span> ক্লায়েন্ট তালিকা</div>
          <table class="client-table">
            <thead><tr>
              <th>Name / Pixel ID</th><th>Status</th><th>Events Today</th>
              <th>API Key</th><th>Actions</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""
    else:
        client_table = """
        <div class="card">
          <div class="empty-state">
            <div class="big">📭</div>
            <p>এখনো কোনো ক্লায়েন্ট যোগ করা হয়নি।</p>
          </div>
        </div>"""

    body = f"""
    <div class="top-grid">
      {stats}
      {add_form}
    </div>
    <div class="bottom-section">
      {client_table}
    </div>
    """
    return HTMLResponse(base_html("Dashboard", body, msg, msg_type))


@router.post("/admin/add-client", include_in_schema=False)
@limiter.limit("10/minute")
async def add_client(
    request: Request,
    username: str = Depends(verify_admin),
    name: str = Form(...),
    pixel_id: str = Form(...),
    access_token: str = Form(...),
    test_event_code: str = Form(None),
    domain: str = Form(None),
    tiktok_pixel_id: str = Form(None),
    tiktok_access_token: str = Form(None),
    ga4_measurement_id: str = Form(None),
    ga4_api_secret: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
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

    # Domain sanitize — https://, http://, trailing slash সরাও
    clean_domain = None
    if domain and domain.strip():
        clean_domain = domain.strip().lower()
        for prefix in ["https://", "http://", "www."]:
            clean_domain = clean_domain.removeprefix(prefix)
        clean_domain = clean_domain.rstrip("/")

    new_client = Client(
        name=name,
        pixel_id=pixel_id,
        access_token=encrypt_token(access_token),  # 🔐 Encrypted at rest
        test_event_code=test_event_code.strip() if test_event_code else None,
        domain=clean_domain,
        api_key=secrets.token_urlsafe(32),
        tiktok_pixel_id=tiktok_pixel_id.strip() if tiktok_pixel_id and tiktok_pixel_id.strip() else None,
        tiktok_access_token=encrypt_token(tiktok_access_token.strip()) if tiktok_access_token and tiktok_access_token.strip() else None,
        ga4_measurement_id=ga4_measurement_id.strip() if ga4_measurement_id and ga4_measurement_id.strip() else None,
        ga4_api_secret=encrypt_token(ga4_api_secret.strip()) if ga4_api_secret and ga4_api_secret.strip() else None,
    )
    db.add(new_client)
    await db.commit()
    await db.refresh(new_client)
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
    safe_client_name = html.escape(client.name, quote=True)
    safe_api_key = html.escape(client.api_key, quote=True)
    safe_endpoint = html.escape(endpoint, quote=True)

    body = f"""
    <h1 class="page-title">📋 Client Instructions</h1>
    <p class="page-sub">এই পেজটি <strong>{safe_client_name}</strong>-কে পাঠিয়ে দিন অথবা নিজেই সেটআপ করুন</p>

    <div class="card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🔑</span> আপনার API Key</div>
      <p style="color:#888;font-size:13px;margin-bottom:10px">এই Key-টি গোপন রাখুন। কখনো Browser/JS-এ পাবলিকলি রাখবেন না। শুধু সার্ভার বা GTM থেকে ব্যবহার করুন।</p>
      <button class="copy-btn" onclick="copyText('api_key')">Copy</button>
      <div class="instr-box" id="api_key">{safe_api_key}</div>
    </div>

    <div class="card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🌐</span> CAPI Endpoint URL</div>
      <p style="color:#888;font-size:13px;margin-bottom:6px">সব ইভেন্ট এই URL-এ POST করতে হবে।</p>
      <button class="copy-btn" onclick="copyText('endpoint')">Copy</button>
      <div class="instr-box" id="endpoint">{safe_endpoint}</div>
      <div style="margin-top:12px;padding:10px 14px;background:rgba(126,87,194,0.08);border:1px solid rgba(126,87,194,0.2);border-radius:8px;font-size:12px;color:#9575cd;">
        💡 <strong>Custom Domain:</strong> আপনার নিজের ডোমেইন থাকলে (যেমন: <code>capi.yourdomain.com</code>) Heroku URL-এর বদলে সেটি ব্যবহার করুন।
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="openTab(event, 'tab-gtm')">⚙️ GTM Server</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-generator')">🛠️ Event Generator</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-wp')">📝 WordPress</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-custom')">💻 Custom</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-test')">🧪 Testing</button>
    </div>

    <!-- GTM TAB -->
    <div id="tab-gtm" class="tab-content active card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">⚙️</span> GTM Server Container Setup <span style="font-size:12px;color:#00e676;margin-left:8px;">✅ Recommended</span></div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p><strong style="color:#fff">Step 1:</strong> Google Tag Manager-এ <strong>Server Container</strong> তৈরি করুন।</p><br>
        <p><strong style="color:#fff">Step 2:</strong> নতুন <strong>Tag → HTTP Request</strong> তৈরি করুন।</p><br>
        <p><strong style="color:#fff">Step 3:</strong> নিচের সেটিংস দিন:</p>
        <button class="copy-btn" onclick="copyText('gtm_settings')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="gtm_settings">URL: {safe_endpoint}
Method: POST
Content-Type: application/json

Headers:
  X-API-Key: {safe_api_key}

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
}}</div>
        <br>
        <p><strong style="color:#fff">Step 4:</strong> Trigger — <strong>All Events</strong> বা নির্দিষ্ট ইভেন্ট সেট করুন।</p>
        <div style="margin-top:12px;padding:14px;background:rgba(0,230,118,0.05);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#00e676">💡 Pro Tips:</strong><br>
          • <strong style="color:#fff">event_id</strong> অবশ্যই ইউনিক হতে হবে — যেমন: <code>order-12345-1715000000</code><br>
          • Browser Pixel ও Server Pixel-এ <strong>একই event_id</strong> পাঠান (Deduplication)<br>
          • <code>action_source: "website"</code> সবসময় রাখুন
        </div>
      </div>
    </div>

    <!-- GENERATOR TAB -->
    <div id="tab-generator" class="tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🛠️</span> Event Code Generator</div>
      
      <div style="margin-bottom:20px;padding:14px;background:rgba(255,82,82,0.1);border:1px solid rgba(255,82,82,0.3);border-radius:8px;font-size:13px;color:#ff5252;line-height:1.6">
        <strong>⚠️ সতর্কতা (Warning):</strong><br>
        দয়া করে শুধুমাত্র সেই ইভেন্টগুলোই ওয়েবসাইটে যুক্ত করুন যেগুলো আপনার ব্যবসার জন্য সত্যিই প্রয়োজন (যেমন: Purchase, AddToCart, Lead)। অপ্রয়োজনীয় ইভেন্ট যোগ করলে আপনার প্রতিদিনের ইভেন্ট লিমিট খুব দ্রুত শেষ হয়ে যাবে!
      </div>

      <div class="form-group" style="margin-bottom: 16px;">
        <label style="color:#fff; font-size:14px; margin-bottom:8px; display:block;">Select an Event to Generate Code:</label>
        <select id="event_selector" style="width:100%; padding:12px; background:rgba(0,0,0,0.4); border:1px solid var(--border); color:#fff; border-radius:8px; font-size:14px; outline:none;">
          <option value="page_view">page_view (পেজ ভিউ)</option>
          <option value="session_start">session_start (সেশন শুরু)</option>
          <option value="user_signup">user_signup / register (অ্যাকাউন্ট তৈরি)</option>
          <option value="user_login">user_login (লগইন)</option>
          <option value="user_logout">user_logout (লগআউট)</option>
          <option value="view_item">view_item (প্রোডাক্ট দেখা)</option>
          <option value="add_to_cart">add_to_cart (কার্টে যোগ করা)</option>
          <option value="remove_from_cart">remove_from_cart (কার্ট থেকে বাদ দেওয়া)</option>
          <option value="view_cart">view_cart (কার্ট দেখা)</option>
          <option value="begin_checkout">begin_checkout (চেকআউট শুরু)</option>
          <option value="purchase">purchase / order_completed (ক্রয় সম্পন্ন)</option>
          <option value="search">search (সার্চ)</option>
          <option value="form_submit">form_submit (ফর্ম জমা)</option>
          <option value="lead">lead (লিড জেনারেট)</option>
          <option value="subscription">subscription (সাবস্ক্রিপশন)</option>
          <option value="refund">refund (রিফান্ড)</option>
          <option value="error">error (এরর)</option>
          <option value="api_call">api_call (API কল)</option>
        </select>
      </div>

      <button class="btn" onclick="generateEventCode()" style="background:#00e676; color:#000; margin-bottom:20px;">⚡ Generate Code</button>

      <div id="code_result_area" style="display:none;">
        <p style="color:#00e676; font-size:13px; margin-bottom:8px;">✅ আপনার কোড রেডি! এটি ওয়েবসাইটের Header-এ বা বাটনের ক্লিকের সাথে বসান:</p>
        <button class="copy-btn" onclick="copyText('generated_code_box')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="generated_code_box" style="min-height:80px;"></div>
      </div>
    </div>

    <!-- WORDPRESS TAB -->
    <div id="tab-wp" class="tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">📝</span> WordPress Setup (সবচেয়ে সহজ নিয়ম)</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p><strong style="color:#fff">ধাপ ১:</strong> আপনার WordPress ওয়েবসাইটে লগিন করুন।</p>
        <p><strong style="color:#fff">ধাপ ২:</strong> <code>WPCode</code> নামের ফ্রি প্লাগিনটি ইনস্টল এবং এক্টিভেট করুন।</p>
        <p><strong style="color:#fff">ধাপ ৩:</strong> WPCode থেকে "Header & Footer" অপশনে যান।</p>
        <p><strong style="color:#fff">ধাপ ৪:</strong> "Header" বক্সে নিচের কোডটি কপি করে পেস্ট করুন এবং Save দিন:</p>
        <button class="copy-btn" onclick="copyText('wp_pv_easy')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_pv_easy">&lt;script&gt;
  (function(w,d,s,l,i){{w[l]=w[l]||function(){{(w[l].q=w[l].q||[]).push(arguments)}};
  var f=d.getElementsByTagName(s)[0],j=d.createElement(s);j.async=true;
  j.src='{safe_endpoint}'.replace('/api/v1/events', '/t.js?key={safe_api_key}');
  f.parentNode.insertBefore(j,f);
  }})(window,document,'script','tracker');
  tracker('track', 'PageView');
&lt;/script&gt;</div>
        
        <div style="margin-top:16px;padding:14px;background:rgba(0,230,118,0.05);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#00e676">🎉 অভিনন্দন!</strong><br>
          আপনার ওয়েবসাইটে পেজ-ভিউ ট্র্যাকিং চালু হয়ে গেছে! এখন কেউ আপনার ওয়েবসাইটে আসলে আপনি তা দেখতে পাবেন।
        </div>
        
        <br><br>
        <p><strong style="color:#fff">ধাপ ৫ (সবগুলো ইকমার্স ইভেন্ট একসাথে ট্র্যাক করতে):</strong></p>
        <p>Purchase, AddToCart, ViewContent (প্রোডাক্ট দেখা) এবং Checkout ট্র্যাক করতে WPCode-এর "Add Snippet"-এ গিয়ে "Add Your Custom Code" সিলেক্ট করুন। Code Type দিন "PHP Snippet" এবং নিচের ম্যাজিক কোডটি পেস্ট করে "Active" করে সেভ দিন। ব্যাস, আপনার পুরো স্টোর ট্র্যাকিং শুরু হয়ে যাবে!</p>
        <button class="copy-btn" onclick="copyText('wp_all_easy')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_all_easy">&lt;?php
// ১. Purchase Event
add_action('woocommerce_thankyou', 'send_capi_purchase_easy');
function send_capi_purchase_easy($order_id) {{
    $order = wc_get_order($order_id);
    send_capi_event('Purchase', $order-&gt;get_checkout_url(), $order-&gt;get_total(), "order-" . $order_id, null);
}}

// ২. ViewContent (Product View)
add_action('woocommerce_after_single_product', 'send_capi_view_content');
function send_capi_view_content() {{
    global $product;
    send_capi_event('ViewContent', get_permalink(), $product-&gt;get_price(), 'view-' . $product-&gt;get_id(), $product-&gt;get_id());
}}

// ৩. AddToCart
add_action('woocommerce_add_to_cart', 'send_capi_add_to_cart', 10, 2);
function send_capi_add_to_cart($cart_item_key, $product_id) {{
    $product = wc_get_product($product_id);
    send_capi_event('AddToCart', wc_get_cart_url(), $product-&gt;get_price(), 'cart-' . $product_id, $product_id);
}}

// ৪. InitiateCheckout
add_action('woocommerce_before_checkout_form', 'send_capi_checkout');
function send_capi_checkout() {{
    send_capi_event('InitiateCheckout', wc_get_checkout_url(), WC()-&gt;cart-&gt;get_cart_contents_total(), 'chk-' . time(), null);
}}

// Main Function to Send Data
function send_capi_event($event_name, $url, $value, $event_id, $product_id) {{
    $data = ['data' =&gt; [[
        'event_name' =&gt; $event_name,
        'event_time' =&gt; time(),
        'event_id' =&gt; $event_id,
        'event_source_url' =&gt; $url,
        'action_source' =&gt; 'website',
        'user_data' =&gt; [
            'client_ip_address' =&gt; $_SERVER['REMOTE_ADDR'] ?? '',
            'client_user_agent' =&gt; $_SERVER['HTTP_USER_AGENT'] ?? ''
        ],
        'custom_data' =&gt; [
            'value' =&gt; (float) $value,
            'currency' =&gt; get_woocommerce_currency()
        ]
    ]]];
    
    if ($product_id) {{
        $data['data'][0]['custom_data']['content_ids'] = [$product_id];
        $data['data'][0]['custom_data']['content_type'] = 'product';
    }}

    wp_remote_post('{safe_endpoint}?key={safe_api_key}', [
        'body' =&gt; json_encode($data),
        'headers' =&gt; ['Content-Type' =&gt; 'application/json'],
        'blocking' =&gt; false
    ]);
}}
?&gt;</div>
      </div>
    </div>

    <!-- CUSTOM TAB -->
    <div id="tab-custom" class="tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">💻</span> Custom Backend (cURL / Node / Laravel / Python)</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p><strong style="color:#fff">cURL Example (Purchase):</strong></p>
        <button class="copy-btn" onclick="copyText('curl_ex')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="curl_ex">curl -X POST "{safe_endpoint}" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: $CAPI_API_KEY" \\
  -d '{{
    "data": [{{
      "event_name": "Purchase",
      "event_time": 1715000000,
      "event_id": "order-12345-1715000000",
      "action_source": "website",
      "event_source_url": "https://example.com/checkout/success",
      "user_data": {{
        "client_ip_address": "192.168.1.1",
        "client_user_agent": "Mozilla/5.0...",
        "fbp": "fb.1.1715000000.1234567890",
        "fbc": "fb.1.1715000000.9876543210"
      }},
      "custom_data": {{
        "value": 150.50,
        "currency": "BDT"
      }}
    }}]
  }}'</div>
        <div style="margin-top:12px;padding:14px;background:rgba(0,230,118,0.05);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#00e676">🔒 Security:</strong><br>
          • API Key সবসময় <code>.env</code> থেকে লোড করুন — <code>$CAPI_API_KEY</code><br>
          • Email/Phone পাঠালে <strong>SHA-256 Hash</strong> করে পাঠান। IP ও UA হ্যাশ করতে হবে না।
        </div>
      </div>
    </div>

    <!-- TESTING TAB -->
    <div id="tab-test" class="tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🧪</span> Testing Guide — লাইভের আগে টেস্ট করুন</div>
      <div style="color:#aaa;font-size:14px;line-height:2">
        <p><strong style="color:#fff">Step 1:</strong> Facebook Events Manager → আপনার Pixel → <strong>Test Events</strong> ট্যাবে যান → Test Code কপি করুন।</p><br>
        <p><strong style="color:#fff">Step 2:</strong> Admin Dashboard → ক্লায়েন্ট Edit → <strong>Test Event Code</strong> ফিল্ডে Code দিন।</p><br>
        <p><strong style="color:#fff">Step 3:</strong> আপনার ওয়েবসাইট ব্রাউজ করুন বা GTM থেকে ইভেন্ট ট্রিগার করুন।</p><br>
        <p><strong style="color:#fff">Step 4:</strong> Facebook Events Manager-এর Test Events ট্যাবে রিয়েল-টাইমে ইভেন্ট দেখা যাবে।</p><br>
        <p><strong style="color:#fff">Step 5:</strong> সব ঠিক থাকলে Admin Panel থেকে Test Event Code খালি করে দিন।</p><br>
        <div style="padding:14px;background:rgba(255,82,82,0.06);border:1px solid rgba(255,82,82,0.2);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#ff5252">⚠️ Checklist:</strong><br>
          ✅ প্রতিটি ইভেন্টে ইউনিক <code>event_id</code> যাচ্ছে কিনা<br>
          ✅ Browser ও Server Pixel-এ একই <code>event_id</code> যাচ্ছে কিনা<br>
          ✅ <code>_fbp</code> ও <code>_fbc</code> কুকি পাঠানো হচ্ছে কিনা<br>
          ✅ Match Rate ৬০%+ আছে কিনা (Events Manager-এ দেখুন)
        </div>
      </div>
    </div>

    <!-- IMPORTANT NOTES -->
    <div class="card">
      <div class="card-title"><span class="icon">📌</span> Important Notes</div>
      <ul style="color:#aaa;font-size:13px;line-height:2.2;padding-left:20px">
        <li>ইউনিক <strong style="color:#fff">event_id</strong> ব্যবহার করুন — <code>order-12345-1715000000</code></li>
        <li>Browser ও Server Pixel-এ <strong>একই event_id</strong> পাঠান (Deduplication)</li>
        <li><code>_fbc</code> ও <code>_fbp</code> কুকি পাঠালে Match Rate বাড়ে</li>
        <li>API Key কখনো Client-side এ রাখবেন না — শুধু Server থেকে</li>
        <li>সবসময় <code>"action_source": "website"</code> যোগ করুন</li>
        <li>লাইভের আগে <strong>Test Event Code</strong> দিয়ে ভেরিফাই করুন</li>
      </ul>
    </div>

    <br>
    <a href="/api/v1/admin" style="color:#6c63ff;font-size:14px">← Dashboard-এ ফিরে যান</a>

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
            case 'user_logout': fbEvent = 'Logout'; params = ", {{custom_event: 'user_logout'}}"; break;
            case 'view_item': fbEvent = 'ViewContent'; params = ", {{value: 100, currency: 'BDT', content_ids: ['ID-123'], content_type: 'product'}}"; break;
            case 'add_to_cart': fbEvent = 'AddToCart'; params = ", {{value: 100, currency: 'BDT', content_ids: ['ID-123']}}"; break;
            case 'remove_from_cart': fbEvent = 'RemoveFromCart'; params = ", {{value: 100, currency: 'BDT', content_ids: ['ID-123']}}"; break;
            case 'view_cart': fbEvent = 'ViewCart'; params = ", {{value: 500, currency: 'BDT'}}"; break;
            case 'begin_checkout': fbEvent = 'InitiateCheckout'; params = ", {{value: 500, currency: 'BDT'}}"; break;
            case 'purchase': fbEvent = 'Purchase'; params = ", {{value: 1500, currency: 'BDT', content_ids: ['ID-123'], order_id: 'ORD-001'}}"; break;
            case 'search': fbEvent = 'Search'; params = ", {{search_string: 'T-shirt'}}"; break;
            case 'form_submit': fbEvent = 'Contact'; break;
            case 'lead': fbEvent = 'Lead'; break;
            case 'subscription': fbEvent = 'Subscribe'; params = ", {{value: 500, currency: 'BDT'}}"; break;
            case 'refund': fbEvent = 'Refund'; params = ", {{value: 1500, currency: 'BDT', order_id: 'ORD-001'}}"; break;
            case 'error': fbEvent = 'Error'; params = ", {{error_msg: 'Payment failed'}}"; break;
            case 'api_call': fbEvent = 'API_Call'; params = ", {{endpoint: '/pay'}}"; break;
        }}
        
        code = "<script>\\n  // Event: " + ev + "\\n  tracker('track', '" + fbEvent + "'" + params + ");\\n</scr" + "ipt>";
        
        document.getElementById('generated_code_box').innerText = code;
        document.getElementById('code_result_area').style.display = 'block';
    }}
    </script>
    """
    return HTMLResponse(base_html(f"Instructions — {client.name}", body))


@router.post("/admin/client/{client_id}/deactivate", include_in_schema=False)
async def deactivate_client(
    client_id: int,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(update(Client).where(Client.id == client_id).values(is_active=False))
    await db.commit()
    return admin_redirect("ক্লায়েন্ট Deactivate করা হয়েছে")


@router.post("/admin/client/{client_id}/activate", include_in_schema=False)
async def activate_client(
    client_id: int,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(update(Client).where(Client.id == client_id).values(is_active=True))
    await db.commit()
    return admin_redirect("ক্লায়েন্ট Activate করা হয়েছে")
