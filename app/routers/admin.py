import os
import html
import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import get_db
from app.models.client import Client
from app.security import encrypt_token

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
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',sans-serif;background:#0f1117;color:#e0e0e0;min-height:100vh}
  .navbar{background:#1a1d27;border-bottom:1px solid #2a2d3e;padding:16px 32px;
          display:flex;align-items:center;gap:16px}
  .navbar .logo{font-size:20px;font-weight:700;color:#fff}
  .navbar .logo span{color:#6c63ff}
  .navbar .badge{background:#6c63ff22;color:#6c63ff;border:1px solid #6c63ff44;
                  padding:3px 10px;border-radius:20px;font-size:12px}
  .container{max-width:1100px;margin:40px auto;padding:0 24px}
  .page-title{font-size:28px;font-weight:700;color:#fff;margin-bottom:8px}
  .page-sub{color:#888;font-size:14px;margin-bottom:32px}
  .grid{display:grid;grid-template-columns:1fr 1.6fr;gap:24px;align-items:start}
  .card{background:#1a1d27;border:1px solid #2a2d3e;border-radius:14px;padding:28px}
  .card-title{font-size:16px;font-weight:600;color:#fff;margin-bottom:20px;
               display:flex;align-items:center;gap:8px}
  .card-title .icon{width:32px;height:32px;background:#6c63ff22;border-radius:8px;
                     display:flex;align-items:center;justify-content:center;font-size:16px}
  .form-group{margin-bottom:18px}
  label{display:block;font-size:13px;color:#aaa;margin-bottom:6px;font-weight:500}
  input[type=text],input[type=password]{width:100%;padding:10px 14px;background:#12141e;
    border:1px solid #2a2d3e;border-radius:8px;color:#e0e0e0;font-size:14px;
    transition:.2s;outline:none}
  input:focus{border-color:#6c63ff;background:#1a1d27}
  .btn{width:100%;padding:12px;background:#6c63ff;color:#fff;border:none;border-radius:8px;
       font-size:14px;font-weight:600;cursor:pointer;transition:.2s;margin-top:6px}
  .btn:hover{background:#5a52e8;transform:translateY(-1px)}
  .btn-sm{padding:7px 14px;font-size:12px;border-radius:6px;border:none;cursor:pointer;
           font-weight:600;transition:.2s}
  .btn-danger{background:#ff4d4d22;color:#ff4d4d;border:1px solid #ff4d4d44}
  .btn-danger:hover{background:#ff4d4d44}
  .btn-info{background:#6c63ff22;color:#6c63ff;border:1px solid #6c63ff44}
  .btn-info:hover{background:#6c63ff44}
  .client-table{width:100%;border-collapse:collapse}
  .client-table th{text-align:left;padding:10px 14px;font-size:12px;color:#666;
                    font-weight:600;border-bottom:1px solid #2a2d3e;text-transform:uppercase}
  .client-table td{padding:12px 14px;font-size:13px;border-bottom:1px solid #1a1d27;vertical-align:middle}
  .client-table tr:hover td{background:#ffffff05}
  .badge-active{background:#00c85322;color:#00c853;border:1px solid #00c85344;
                 padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
  .badge-inactive{background:#ff4d4d22;color:#ff4d4d;border:1px solid #ff4d4d44;
                   padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
  .api-key-cell{font-family:monospace;font-size:11px;color:#888;
                 max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .alert{padding:14px 18px;border-radius:8px;margin-bottom:20px;font-size:14px}
  .alert-success{background:#00c85322;border:1px solid #00c85344;color:#00c853}
  .alert-error{background:#ff4d4d22;border:1px solid #ff4d4d44;color:#ff4d4d}
  .stat-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px}
  .stat-box{background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;padding:16px}
  .stat-box .num{font-size:28px;font-weight:700;color:#6c63ff}
  .stat-box .lbl{font-size:12px;color:#888;margin-top:4px}
  .empty-state{text-align:center;padding:40px;color:#555}
  .empty-state .big{font-size:40px;margin-bottom:12px}
  .instr-box{background:#12141e;border:1px solid #2a2d3e;border-radius:8px;
              padding:14px;font-family:monospace;font-size:12px;color:#aaa;
              white-space:pre-wrap;word-break:break-all;margin-top:8px}
  .copy-btn{background:#2a2d3e;color:#aaa;border:none;border-radius:4px;
             padding:4px 10px;font-size:11px;cursor:pointer;float:right;margin-top:-4px}
  .copy-btn:hover{background:#3a3d4e;color:#fff}
  .hint{font-size:11px;color:#555;margin-top:5px}
</style>
"""


def base_html(title: str, body: str, msg: str = "", msg_type: str = "success") -> str:
    alert_html = ""
    if msg:
        safe_msg = html.escape(msg)
        safe_type = html.escape(msg_type)
        alert_html = f'<div class="alert alert-{safe_type}">{safe_msg}</div>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — CAPI Gateway</title>
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
</body>
</html>"""


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
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

    # আজকের সফল ইভেন্ট
    success_r = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(EventLog.status == "success", EventLog.created_at >= today)
        )
    )
    events_today = success_r.scalar() or 0

    # আজকের ব্যর্থ
    fail_r = await db.execute(
        select(sql_func.count(EventLog.id)).where(
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
    <h1 class="page-title">Dashboard</h1>
    <p class="page-sub">আপনার সকল ক্লায়েন্ট এখান থেকে ম্যানেজ করুন</p>
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
    """

    # ─── Add Client Form ───────────────────────────────────────────────────
    add_form = """
    <div class="grid">
      <div class="card">
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
            <label>Test Event Code (Optional)</label>
            <input type="text" name="test_event_code" placeholder="TEST12345">
            <div class="hint">শুধু টেস্টিং করার সময় দিন, লাইভে খালি রাখুন</div>
          </div>
          <button type="submit" class="btn">✅ ক্লায়েন্ট যোগ করুন</button>
        </form>
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
            rows += f"""
            <tr>
              <td><strong>{safe_name}</strong><br><span style="color:#555;font-size:11px">{safe_pixel}</span></td>
              <td>{status_badge}</td>
              <td class="api-key-cell" title="{safe_key}">{safe_key[:24]}...</td>
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
              <th>Name / Pixel ID</th><th>Status</th>
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

    body = stats + add_form + client_table + "</div>"
    return HTMLResponse(base_html("Dashboard", body, msg, msg_type))


@router.post("/admin/add-client", include_in_schema=False)
async def add_client(
    request: Request,
    username: str = Depends(verify_admin),
    name: str = Form(...),
    pixel_id: str = Form(...),
    access_token: str = Form(...),
    test_event_code: str = Form(None),
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
        return RedirectResponse(
            url=f"/api/v1/admin?msg={error_msg}&msg_type=error",
            status_code=303,
        )

    new_client = Client(
        name=name,
        pixel_id=pixel_id,
        access_token=encrypt_token(access_token),  # 🔐 Encrypted at rest
        test_event_code=test_event_code.strip() if test_event_code else None,
        api_key=secrets.token_urlsafe(32),
    )
    db.add(new_client)
    await db.commit()
    await db.refresh(new_client)
    logger.info(f"New client added: {name}")

    return RedirectResponse(
        url=f"/api/v1/admin?msg=✅+{name}+সফলভাবে+যোগ+হয়েছে!&msg_type=success",
        status_code=303,
    )


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

    body = f"""
    <h1 class="page-title">📋 Client Instructions</h1>
    <p class="page-sub">এই পেজটি <strong>{client.name}</strong>-কে পাঠিয়ে দিন অথবা GTM সেটআপে ব্যবহার করুন</p>

    <div class="card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🔑</span> আপনার API Key</div>
      <p style="color:#888;font-size:13px;margin-bottom:10px">এই Key-টি গোপন রাখুন। শুধু GTM Server Container-এ ব্যবহার করুন।</p>
      <button class="copy-btn" onclick="copyText('api_key')">Copy</button>
      <div class="instr-box" id="api_key">{client.api_key}</div>
    </div>

    <div class="card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🌐</span> CAPI Endpoint URL</div>
      <p style="color:#888;font-size:13px;margin-bottom:10px">GTM HTTP Request Tag-এ এই URL দিন।</p>
      <button class="copy-btn" onclick="copyText('endpoint')">Copy</button>
      <div class="instr-box" id="endpoint">{endpoint}</div>
    </div>

    <div class="card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">⚙️</span> GTM Server Container Setup</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p><strong style="color:#fff">Step 1:</strong> আপনার Google Tag Manager-এ <strong>Server Container</strong> তৈরি করুন।</p>
        <br>
        <p><strong style="color:#fff">Step 2:</strong> একটি নতুন <strong>Tag → HTTP Request</strong> তৈরি করুন।</p>
        <br>
        <p><strong style="color:#fff">Step 3:</strong> নিচের সেটিংস দিন:</p>
        <div class="instr-box" id="gtm_settings">URL: {endpoint}
Method: POST
Content-Type: application/json

Headers:
  X-API-Key: {client.api_key}

Body (JSON):
{{
  "data": [{{
    "event_name": "{{{{Event Name}}}}",
    "event_time": {{{{Unix Timestamp}}}},
    "event_id": "{{{{Event ID}}}}",
    "event_source_url": "{{{{Page URL}}}}",
    "user_data": {{
      "client_ip_address": "{{{{IP Address}}}}",
      "client_user_agent": "{{{{User Agent}}}}",
      "fbc": "{{{{_fbc cookie}}}}",
      "fbp": "{{{{_fbp cookie}}}}"
    }}
  }}]
}}</div>
        <br>
        <p><strong style="color:#fff">Step 4:</strong> Trigger — <strong>All Events</strong> বা নির্দিষ্ট ইভেন্ট সেট করুন।</p>
        <br>
        <p><strong style="color:#fff">Step 5:</strong> Facebook Events Manager-এ গিয়ে <strong>Test Events</strong> ট্যাবে চেক করুন।</p>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="icon">📌</span> Important Notes</div>
      <ul style="color:#aaa;font-size:13px;line-height:2;padding-left:20px">
        <li>প্রতিটি ইভেন্টে <strong style="color:#fff">event_id</strong> পাঠান (Deduplication-এর জন্য খুবই জরুরি)</li>
        <li>Browser Pixel এবং Server Pixel — দুটোই চালু রাখুন, একই event_id ব্যবহার করুন</li>
        <li>_fbc এবং _fbp cookie পাঠান — এতে match rate অনেক বাড়ে</li>
        <li>লাইভ যাওয়ার আগে Test Event Code দিয়ে টেস্ট করুন</li>
      </ul>
    </div>

    <br>
    <a href="/api/v1/admin" style="color:#6c63ff;font-size:14px">← Dashboard-এ ফিরে যান</a>
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
    return RedirectResponse(url="/api/v1/admin?msg=ক্লায়েন্ট+Deactivate+করা+হয়েছে&msg_type=success", status_code=303)


@router.post("/admin/client/{client_id}/activate", include_in_schema=False)
async def activate_client(
    client_id: int,
    username: str = Depends(verify_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(update(Client).where(Client.id == client_id).values(is_active=True))
    await db.commit()
    return RedirectResponse(url="/api/v1/admin?msg=ক্লায়েন্ট+Activate+করা+হয়েছে&msg_type=success", status_code=303)
