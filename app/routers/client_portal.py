from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
import html
import datetime
from typing import Optional
from sqlalchemy import and_

from app.database import get_db
from app.models.client import Client
from app.models.event_log import EventLog
from app.models.pending_event import PendingEvent
from app.routers.admin import STYLE, base_html
from app.security import encrypt_token, decrypt_token
from app.limiter import limiter


CLIENT_STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  :root {
    --bg-main: #0b0f19;
    --bg-sidebar: #111827;
    --bg-card: #1f2937;
    --border: rgba(255, 255, 255, 0.05);
    --primary: #6366f1;
    --primary-hover: #818cf8;
    --text-main: #f9fafb;
    --text-muted: #9ca3af;
    --accent: #10b981;
    --danger: #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
  body {
    background: var(--bg-main); color: var(--text-main); min-height: 100vh;
    display: flex; overflow: hidden;
  }
  
  /* Sidebar */
  .sidebar {
    width: 260px; background: var(--bg-sidebar); border-right: 1px solid var(--border);
    display: flex; flex-direction: column; padding: 24px 0; height: 100vh;
    z-index: 10;
  }
  .sidebar-logo {
    font-size: 20px; font-weight: 700; color: #fff; padding: 0 24px 32px 24px;
    letter-spacing: -0.5px;
  }
  .sidebar-logo span { color: var(--primary); }
  .sidebar-menu { display: flex; flex-direction: column; gap: 4px; flex: 1; padding: 0 12px; }
  .nav-item {
    display: flex; align-items: center; gap: 12px; padding: 12px 16px;
    color: var(--text-muted); font-size: 14px; font-weight: 500;
    border-radius: 8px; cursor: pointer; transition: all 0.2s ease;
    text-decoration: none;
  }
  .nav-item:hover { background: rgba(255, 255, 255, 0.05); color: #fff; }
  .nav-item.active { background: rgba(99, 102, 241, 0.1); color: var(--primary-hover); }
  .nav-icon { font-size: 18px; }
  
  /* Main Content */
  .main-content {
    flex: 1; height: 100vh; overflow-y: auto; padding: 32px;
    background-image: radial-gradient(circle at top right, rgba(99,102,241,0.05), transparent 40%);
  }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }
  .page-title { font-size: 28px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
  .page-sub { color: var(--text-muted); font-size: 14px; margin-top: 4px; }
  
  /* Tabs */
  .tab-pane { display: none; animation: fadeIn 0.3s ease; }
  .tab-pane.active { display: block; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
  
  /* Shared components */
  .card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
    padding: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    margin-bottom: 24px;
  }
  .card-title {
    font-size: 16px; font-weight: 600; color: #fff; margin-bottom: 20px;
    display: flex; align-items: center; gap: 8px;
  }
  .stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-box { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .stat-box .num { font-size: 28px; font-weight: 700; color: #fff; line-height: 1.2; }
  .stat-box .lbl { font-size: 12px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; margin-top: 4px; }
  
  .client-table { width: 100%; border-collapse: separate; border-spacing: 0; text-align: left; }
  .client-table th { padding: 12px 16px; font-size: 12px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border); }
  .client-table td { padding: 16px; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.02); }
  .client-table tr:hover td { background: rgba(255,255,255,0.02); }
  
  .badge { padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; display: inline-block; }
  .badge-success { background: rgba(16, 185, 129, 0.1); color: var(--accent); border: 1px solid rgba(16, 185, 129, 0.2); }
  .badge-error { background: rgba(239, 68, 68, 0.1); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.2); }
  
  .btn-sm { padding: 8px 12px; font-size: 12px; border-radius: 6px; border: none; cursor: pointer; font-weight: 500; transition: all 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 4px;}
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover { background: var(--primary-hover); }
  .btn-danger { background: rgba(239,68,68,0.1); color: var(--danger); border: 1px solid rgba(239,68,68,0.2); }
  .btn-danger:hover { background: var(--danger); color: #fff; }
  .btn-info { background: rgba(255,255,255,0.05); color: #fff; border: 1px solid var(--border); }
  .btn-info:hover { background: rgba(255,255,255,0.1); }
  
  .copy-btn { background: rgba(255,255,255,0.1); color: #fff; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer; float: right; margin-top: -4px;}
  .copy-btn:hover { background: var(--primary); }
  .instr-box { background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-family: monospace; font-size: 12px; color: #cbd5e1; white-space: pre-wrap; word-break: break-all; margin-top: 8px; }
  
  .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; overflow-x: auto; }
  .tab-btn { background: none; border: none; color: var(--text-muted); font-size: 14px; font-weight: 600; cursor: pointer; padding: 8px 16px; border-radius: 8px; transition: all 0.3s; white-space: nowrap; }
  .tab-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
  .tab-btn.active { color: #fff; background: rgba(99, 102, 241, 0.2); border: 1px solid rgba(99, 102, 241, 0.4); }
  .inner-tab-content { display: none; animation: fadeIn 0.3s ease; }
  .inner-tab-content.active { display: block; }
</style>
"""

def client_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Client Portal</title>
  {CLIENT_STYLE}
</head>
<body>
  <!-- Sidebar Navigation -->
  <aside class="sidebar">
    <div class="sidebar-logo">CAPI<span>Gateway</span></div>
    <nav class="sidebar-menu">
      <a class="nav-item active" onclick="switchTab('tab-dashboard', this)"><span class="nav-icon">📊</span> Dashboard</a>
      <a class="nav-item" onclick="switchTab('tab-analytics', this)"><span class="nav-icon">📈</span> Analytics</a>
      <a class="nav-item" onclick="switchTab('tab-event-log', this)"><span class="nav-icon">📋</span> Event Log</a>
      <a class="nav-item" onclick="switchTab('tab-delay-purchase', this)"><span class="nav-icon">⏳</span> Delay Purchase Event (Legacy)</a>
      <a class="nav-item" onclick="switchTab('tab-settings', this)"><span class="nav-icon">⚙️</span> Settings & Setup</a>
      <a class="nav-item" onclick="alert('Coming soon. Please contact the admin for updates.')"><span class="nav-icon">🔄</span> Update Plan</a>
    </nav>
    <div style="margin-top: auto; padding: 0 12px;">
      <a href="/client/logout" class="nav-item" style="color: var(--danger);"><span class="nav-icon">🚪</span> Logout</a>
    </div>
  </aside>

  <!-- Main Content Area -->
  <main class="main-content">
    {body}
  </main>
  
  <script>
    function switchTab(tabId, el) {{
      var tabs = document.getElementsByClassName('tab-pane');
      for (var i = 0; i < tabs.length; i++) {{ tabs[i].classList.remove('active'); }}
      var navs = document.getElementsByClassName('nav-item');
      for (var i = 0; i < navs.length; i++) {{ navs[i].classList.remove('active'); }}
      
      document.getElementById(tabId).classList.add('active');
      if (el) el.classList.add('active');
    }}
    
    function copyText(id) {{
      var t = document.getElementById(id);
      var textToCopy = t.innerText || t.value;
      navigator.clipboard.writeText(textToCopy);
      var eventTarget = event.target;
      var origText = eventTarget.innerText;
      eventTarget.innerText = 'Copied!';
      setTimeout(() => eventTarget.innerText = origText, 1500);
    }}
    
    function openInnerTab(evt, tabId) {{
      var i, tc, tl;
      tc = document.getElementsByClassName("inner-tab-content");
      for (i = 0; i < tc.length; i++) {{ tc[i].className = tc[i].className.replace(" active", ""); }}
      tl = document.getElementsByClassName("tab-btn");
      for (i = 0; i < tl.length; i++) {{ tl[i].className = tl[i].className.replace(" active", ""); }}
      document.getElementById(tabId).className += " active";
      evt.currentTarget.className += " active";
    }}
  </script>
</body>
</html>"""


router = APIRouter(tags=["Client Portal"])

def get_client_from_cookie(request: Request) -> Optional[str]:
    """Cookie থেকে encrypted session token পড়ে decrypt করে API key রিটার্ন করে।"""
    encrypted = request.cookies.get("client_session")
    if not encrypted:
        return None
    try:
        return decrypt_token(encrypted)
    except Exception:
        return None

@router.get("/client", response_class=HTMLResponse, include_in_schema=False)
async def client_login_page(request: Request):
    api_key = get_client_from_cookie(request)
    if api_key:
        return RedirectResponse(url="/client/dashboard", status_code=303)
        
    body = """
    <div class="container" style="max-width: 400px; margin-top: 100px;">
        <h1 class="page-title" style="text-align:center;">Client Portal</h1>
        <p class="page-sub" style="text-align:center;">লগিন করতে আপনার API Key ব্যবহার করুন</p>
        
        <div class="card">
            <form action="/client/login" method="post">
                <div class="form-group">
                    <label>API Key</label>
                    <input type="password" name="api_key" required placeholder="Paste your API Key here..." autocomplete="off">
                </div>
                <button type="submit" class="btn">Login to Dashboard</button>
            </form>
        </div>
    </div>
    """
    return HTMLResponse(base_html("Client Login", body))

@router.post("/client/login", include_in_schema=False)
@limiter.limit("5/minute")
async def client_login(request: Request, response: Response, api_key: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.api_key == api_key))
    client = result.scalar_one_or_none()
    
    if not client or not client.is_active:
        body = """
        <div class="container" style="max-width: 400px; margin-top: 100px;">
            <div class="alert alert-error" style="justify-content:center;">Invalid or Inactive API Key</div>
            <a href="/client" class="btn" style="text-align:center; display:block; text-decoration:none;">Try Again</a>
        </div>
        """
        return HTMLResponse(base_html("Login Failed", body), status_code=401)
        
    redirect = RedirectResponse(url="/client/dashboard", status_code=303)
    redirect.set_cookie(
        key="client_session",
        value=encrypt_token(api_key),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )
    return redirect

@router.get("/client/logout", include_in_schema=False)
async def client_logout():
    redirect = RedirectResponse(url="/client", status_code=303)
    redirect.delete_cookie("client_session")
    return redirect

@router.get("/client/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def client_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    api_key = get_client_from_cookie(request)
    if not api_key:
        return RedirectResponse(url="/client", status_code=303)
        
    result = await db.execute(select(Client).where(Client.api_key == api_key))
    client = result.scalar_one_or_none()
    if not client or not client.is_active:
        redirect = RedirectResponse(url="/client", status_code=303)
        redirect.delete_cookie("client_session")
        return redirect

    # Get today's stats
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    events_result = await db.execute(
        select(EventLog.status, func.count(EventLog.id))
        .where(EventLog.client_id == client.id)
        .where(EventLog.created_at >= today_start)
        .group_by(EventLog.status)
    )
    
    success_count = 0
    failed_count = 0
    
    for row in events_result:
        status, count = row
        if status == "success":
            success_count = count
        elif status == "failed":
            failed_count = count
            
    total = success_count + failed_count
    success_rate = round((success_count / total * 100) if total > 0 else 0, 1)

    # ─── 7-Day Chart Data ─────────────────────────────────────────────
    from sqlalchemy import cast, Date
    seven_days_ago = today_start - datetime.timedelta(days=6)
    
    chart_result = await db.execute(
        select(
            cast(EventLog.created_at, Date).label("day"),
            EventLog.status,
            func.count(EventLog.id),
        )
        .where(EventLog.client_id == client.id)
        .where(EventLog.created_at >= seven_days_ago)
        .group_by("day", EventLog.status)
        .order_by("day")
    )
    
    # Build chart data
    chart_data = {}
    for row in chart_result:
        day_str = str(row[0])
        status_val = row[1]
        count_val = row[2]
        if day_str not in chart_data:
            chart_data[day_str] = {"success": 0, "failed": 0}
        chart_data[day_str][status_val] = count_val
    
    # Fill missing days
    labels = []
    success_data = []
    failed_data = []
    for i in range(7):
        d = seven_days_ago + datetime.timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        short_label = d.strftime("%b %d")
        labels.append(short_label)
        success_data.append(chart_data.get(day_str, {}).get("success", 0))
        failed_data.append(chart_data.get(day_str, {}).get("failed", 0))
    
    import json as json_mod
    labels_json = json_mod.dumps(labels)
    success_json = json_mod.dumps(success_data)
    failed_json = json_mod.dumps(failed_data)

    # ─── Recent Event Logs (last 50) ──────────────────────────────────
    logs_result = await db.execute(
        select(EventLog)
        .where(EventLog.client_id == client.id)
        .order_by(EventLog.created_at.desc())
        .limit(50)
    )
    recent_logs = logs_result.scalars().all()

    # Dashboard Recent Events (last 15)
    dashboard_logs_html = ""
    for log in recent_logs[:15]:
        time_str = log.created_at.strftime("%b %d, %H:%M:%S") if log.created_at else "—"
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span class="badge badge-success">✅ Success</span>'
            if log.status == "success"
            else '<span class="badge badge-error">❌ Failed</span>'
        )
        dashboard_logs_html += f"""
        <tr>
          <td style="color:var(--text-muted);font-size:12px">{time_str}</td>
          <td><strong>{safe_event_name}</strong></td>
          <td style="font-family:monospace;font-size:11px;color:var(--text-muted)">{safe_event_id}</td>
          <td>{status_badge}</td>
        </tr>"""

    if not recent_logs:
        dashboard_logs_html = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:30px">এখনো কোনো ইভেন্ট লগ নেই</td></tr>'

    # Purchase Event Logs (Filter only Purchase)
    purchase_logs_html = ""
    for log in recent_logs:
        if (log.event_name or "").lower() not in ["purchase", "order_completed"]:
            continue
        time_str = log.created_at.strftime("%b %d, %H:%M:%S") if log.created_at else "—"
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span class="badge badge-success">✅ Success</span>'
            if log.status == "success"
            else '<span class="badge badge-error">❌ Failed</span>'
        )
        purchase_logs_html += f"""
        <tr>
          <td style="color:var(--text-muted);font-size:12px">{time_str}</td>
          <td><strong>{safe_event_name}</strong></td>
          <td style="font-family:monospace;font-size:11px;color:var(--text-muted)">{safe_event_id}</td>
          <td>{status_badge}</td>
        </tr>"""

    if not purchase_logs_html:
        purchase_logs_html = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:30px">কোনো Purchase ইভেন্ট নেই</td></tr>'

    # General Event Logs (All)
    all_logs_html = ""
    for log in recent_logs:
        time_str = log.created_at.strftime("%b %d, %H:%M:%S") if log.created_at else "—"
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span class="badge badge-success">✅ Success</span>'
            if log.status == "success"
            else '<span class="badge badge-error">❌ Failed</span>'
        )
        all_logs_html += f"""
        <tr>
          <td style="color:var(--text-muted);font-size:12px">{time_str}</td>
          <td><strong>{safe_event_name}</strong></td>
          <td style="font-family:monospace;font-size:11px;color:var(--text-muted)">{safe_event_id}</td>
          <td>{status_badge}</td>
        </tr>"""

    # ─── Pending Events Query (Deferred Purchase) ─────────────────────
    pending_html = ""
    if getattr(client, 'deferred_purchase', False):
        pending_result = await db.execute(
            select(PendingEvent)
            .where(and_(
                PendingEvent.client_id == client.id,
                PendingEvent.status == "pending",
            ))
            .order_by(PendingEvent.created_at.desc())
            .limit(50)
        )
        pending_events = pending_result.scalars().all()

        # Pending count
        pending_count_r = await db.execute(
            select(func.count(PendingEvent.id)).where(and_(
                PendingEvent.client_id == client.id,
                PendingEvent.status == "pending",
            ))
        )
        pending_count = pending_count_r.scalar() or 0

        # Today's confirmed
        confirmed_r = await db.execute(
            select(func.count(PendingEvent.id)).where(and_(
                PendingEvent.client_id == client.id,
                PendingEvent.status == "confirmed",
                PendingEvent.confirmed_at >= today_start,
            ))
        )
        confirmed_today = confirmed_r.scalar() or 0

        # Today's cancelled
        cancelled_r = await db.execute(
            select(func.count(PendingEvent.id)).where(and_(
                PendingEvent.client_id == client.id,
                PendingEvent.status == "cancelled",
            ))
        )
        cancelled_count = cancelled_r.scalar() or 0

        now_utc = datetime.datetime.now(datetime.timezone.utc)

        pending_rows = ""
        for pe in pending_events:
            edata = pe.event_data or {}
            cdata = edata.get("custom_data", {})
            udata = edata.get("user_data", {})
            value_str = f"৳{cdata.get('value', 0):,.0f}" if cdata.get('value') else "—"
            phone = ""
            if udata.get("ph") and isinstance(udata["ph"], list) and udata["ph"]:
                phone = udata["ph"][0][:12] + "..." if len(str(udata["ph"][0])) > 12 else str(udata["ph"][0])
            elif udata.get("em") and isinstance(udata["em"], list) and udata["em"]:
                phone = udata["em"][0][:15] + "..."
            else:
                phone = "—"
            created = pe.created_at
            if created:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=datetime.timezone.utc)
                age_sec = (now_utc - created).total_seconds()
                if age_sec < 3600:
                    age_str = f"{int(age_sec/60)}m ago"
                elif age_sec < 86400:
                    age_str = f"{int(age_sec/3600)}h ago"
                else:
                    age_str = f"{int(age_sec/86400)}d ago"
            else:
                age_str = "—"

            safe_oid = html.escape(pe.order_id)
            pending_rows += f"""
            <tr id="row-{safe_oid}">
              <td><input type="checkbox" class="pending-cb" value="{safe_oid}" style="accent-color:var(--primary);width:16px;height:16px;"></td>
              <td style="font-family:monospace;font-size:12px;color:var(--text-muted)">{safe_oid}</td>
              <td style="color:var(--accent);font-weight:600">{value_str}</td>
              <td style="color:var(--text-muted);font-size:12px">{html.escape(phone)}</td>
              <td style="color:var(--text-muted);font-size:12px">{age_str}</td>
              <td>
                <button class="btn-sm btn-info" onclick="confirmOrder('{safe_oid}')" >✅ Confirm</button>
                
                <button class="btn-sm btn-danger" onclick="cancelOrder('{safe_oid}')" >❌ Cancel</button>
              </td>
            </tr>"""

        if not pending_events:
            pending_rows = '<tr><td colspan="6" style="text-align:center;color:#555;padding:30px">কোনো pending অর্ডার নেই 🎉</td></tr>'

        pending_html = f"""
    <!-- PENDING ORDERS SECTION -->
    <div class="card" style="margin-bottom:24px;border:1px solid rgba(255,171,0,0.2);">
      <div class="card-title"><span class="icon" style="background:rgba(255,171,0,0.15)">📦</span> Pending Purchase Orders
        <span style="font-size:12px;color:#ffab00;margin-left:8px;">Deferred Purchase সচল</span>
      </div>

      <div class="stat-row" style="margin-bottom:16px;">
        <div class="stat-box" style="padding:16px;">
          <div class="num" style="color:#ffab00;font-size:24px">{pending_count}</div>
          <div class="lbl" style="font-size:11px">📦 Pending</div>
        </div>
        <div class="stat-box" style="padding:16px;">
          <div class="num" style="color:#00e676;font-size:24px">{confirmed_today}</div>
          <div class="lbl" style="font-size:11px">✅ Confirmed Today</div>
        </div>
      </div>

      <div style="display:flex;gap:10px;margin-bottom:16px;">
        <button class="btn-sm btn-info" onclick="selectAllPending()" style="font-size:12px;">☑️ Select All</button>
        <button class="btn-sm btn-info" onclick="confirmSelected()" style="font-size:12px;background:rgba(0,230,118,0.1);color:#00e676;border-color:rgba(0,230,118,0.3);">✅ Confirm Selected</button>
      </div>

      <div id="pending-status" style="display:none;padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:13px;"></div>

      <div style="overflow-x:auto;">
        <table class="client-table">
          <thead>
            <tr>
              <th style="width:30px;"></th>
              <th>Order ID</th>
              <th>Amount</th>
              <th>Customer</th>
              <th>Time</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="pending-tbody">
            {pending_rows}
          </tbody>
        </table>
      </div>
    </div>
        """

    # Base URL detection
    base_url = str(request.base_url).rstrip("/")
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost")
    gateway_origin = f"{scheme}://{host}"
    endpoint = f"{base_url}/api/v1/events"
    tracker_key = getattr(client, "public_key", None) or client.api_key
    tracker_url = f"{gateway_origin}/t.js?key={tracker_key}"
    safe_client_name = html.escape(client.name, quote=True)
    safe_api_key = html.escape(client.api_key, quote=True)
    safe_endpoint = html.escape(endpoint, quote=True)
    safe_tracker_url = html.escape(tracker_url, quote=True)

    # Instructions body (Reused from admin.py)
    instructions_html = f"""
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
        💡 <strong>Custom Domain:</strong> আপনার নিজের ডোমেইন থাকলে (যেমন: <code>ss.yourdomain.com</code>) Heroku URL-এর বদলে সেটি ব্যবহার করুন।
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="openTab(event, 'tab-easy')">🚀 Easy Setup</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-generator')">🛠️ Event Generator</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-gtm')">⚙️ GTM Server</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-wp')">📝 WordPress</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-custom')">💻 Custom</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-test')">🧪 Testing</button>
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

    <!-- EASY SETUP TAB (1-LINE TRACKER) -->
    <div id="tab-easy" class="tab-content active card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🚀</span> Easy Setup — মাত্র ১ লাইন কোড! <span style="font-size:12px;color:#00e676;margin-left:8px;">✅ সবচেয়ে সহজ</span></div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p style="color:#ccc;margin-bottom:12px;">আপনার ওয়েবসাইটের <code>&lt;head&gt;</code> বা <code>&lt;body&gt;</code>-র শেষে নিচের ১ লাইন কোড বসান। ব্যস, PageView অটো ট্র্যাক হবে!</p>
        <button class="copy-btn" onclick="copyText('easy_script')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="easy_script">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;</div>
        
        <div style="margin-top:16px;padding:14px;background:rgba(0,230,118,0.05);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#00e676">✨ এই ১ লাইনেই যা হবে:</strong><br>
          ✅ স্বয়ংক্রিয় <strong style="color:#fff">PageView</strong> ট্র্যাকিং<br>
          ✅ <code>_fbc</code> ও <code>_fbp</code> কুকি অটো ক্যাপচার<br>
          ✅ ইমেইল/ফোন SHA-256 হ্যাশিং (ব্রাউজারেই)<br>
          ✅ SPA (React/Next.js) সাপোর্ট<br>
          ✅ বট ট্রাফিক অটো ফিল্টার<br>
          ✅ অ্যাড ব্লকার বাইপাস (Custom Domain ব্যবহার করলে)<br>
          ✅ Safari ITP Cookie Extension (৬ মাস)
        </div>

        <br>
        <p><strong style="color:#fff">কাস্টম ইভেন্ট পাঠানো:</strong></p>
        <p style="color:#888;font-size:13px;margin-bottom:8px">Purchase, AddToCart, Lead ইত্যাদি ইভেন্ট পাঠাতে:</p>
        <button class="copy-btn" onclick="copyText('easy_purchase')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="easy_purchase">// Purchase event
capi('track', 'Purchase', {{
  value: 1500,
  currency: 'BDT',
  content_ids: ['SKU-123'],
  content_type: 'product'
}});

// AddToCart event
capi('track', 'AddToCart', {{
  value: 500,
  currency: 'BDT',
  content_ids: ['SKU-456']
}});

// Lead / Contact Form
capi('track', 'Lead');</div>

        <br>
        <p><strong style="color:#fff">ইউজারের তথ্য সেট করা (অপশনাল — Match Rate বাড়ায়):</strong></p>
        <button class="copy-btn" onclick="copyText('easy_user')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="easy_user">// ইউজারের তথ্য সেট করুন (অটো SHA-256 হ্যাশ হবে)
capi('setUser', {{
  email: 'user@example.com',
  phone: '+8801XXXXXXXXX',
  first_name: 'Rahim',
  city: 'Dhaka',
  country: 'BD'
}});</div>

        <div style="margin-top:16px;padding:14px;background:rgba(255,171,0,0.06);border:1px solid rgba(255,171,0,0.2);border-radius:8px;font-size:13px;color:#ffab00;line-height:1.9">
          <strong>⚡ Pro Tip — Custom Domain:</strong><br>
          অ্যাড ব্লকার ১০০% বাইপাস করতে আপনার নিজের সাবডোমেইন ব্যবহার করুন:<br>
          <code style="color:#fff">ss.yourdomain.com</code> → CNAME → <code>আপনার-heroku-app.herokuapp.com</code><br>
          তারপর স্ক্রিপ্ট ট্যাগে Heroku URL-এর বদলে <code>https://ss.yourdomain.com/t.js?key=...</code> ব্যবহার করুন।
        </div>
      </div>
    </div>

    <!-- WORDPRESS TAB (AS EASY AS 5 YEARS OLD) -->
    <div id="tab-wp" class="tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">📝</span> WordPress Setup (সবচেয়ে সহজ নিয়ম)</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p><strong style="color:#fff">ধাপ ১:</strong> আপনার WordPress ওয়েবসাইটে লগিন করুন।</p>
        <p><strong style="color:#fff">ধাপ ২:</strong> <code>WPCode</code> নামের ফ্রি প্লাগিনটি ইনস্টল এবং এক্টিভেট করুন।</p>
        <p><strong style="color:#fff">ধাপ ৩:</strong> WPCode থেকে "Header & Footer" অপশনে যান।</p>
        <p><strong style="color:#fff">ধাপ ৪:</strong> "Header" বক্সে নিচের কোডটি কপি করে পেস্ট করুন এবং Save দিন:</p>
        <button class="copy-btn" onclick="copyText('wp_pv_easy')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_pv_easy">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;</div>
        
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

    wp_remote_post('{safe_endpoint}', [
        'body' => json_encode($data),
        'headers' => [
            'Content-Type' => 'application/json',
            'X-API-Key' => '{safe_api_key}'
        ],
        'blocking' => false
    ]);
}}
?&gt;</div>
      </div>
    """

    body = f"""
    <div class="header">
        <div>
            <h1 class="page-title">👋 Welcome, {safe_client_name}</h1>
            <p class="page-sub">আপনার CAPI Dashboard</p>
        </div>
    </div>

    <!-- TAB: DASHBOARD -->
    <div id="tab-dashboard" class="tab-pane active">
        <h3 style="color:#fff; margin-bottom:12px; font-weight:600;">📊 Today's Statistics</h3>
        <div class="stat-row">
          <div class="stat-box">
            <div class="num">{success_count}</div>
            <div class="lbl">Successful Events</div>
          </div>
          <div class="stat-box">
            <div class="num" style="color: {'var(--accent)' if success_rate > 90 else 'var(--primary-hover)'};">{success_rate}%</div>
            <div class="lbl">Success Rate</div>
          </div>
        </div>

        <div class="card" style="margin-bottom:24px;">
          <div class="card-title">📈 গত ৭ দিনের ইভেন্ট</div>
          <canvas id="eventsChart" height="120"></canvas>
        </div>

        <div class="card" style="margin-bottom:24px;">
          <div class="card-title">📋 Dashboard Recent Logs</div>
          <div style="overflow-x:auto;">
            <table class="client-table">
              <thead>
                <tr>
                  <th>সময়</th>
                  <th>ইভেন্ট</th>
                  <th>Event ID</th>
                  <th>স্ট্যাটাস</th>
                </tr>
              </thead>
              <tbody>
                {dashboard_logs_html}
              </tbody>
            </table>
          </div>
        </div>
    </div>

    <!-- TAB: ANALYTICS -->
    <div id="tab-analytics" class="tab-pane">
        <div class="card" style="margin-bottom:24px;border:1px solid rgba(99,102,241,0.2);">
          <div class="card-title">📊 Advanced Analytics
            <a href="/api/v1/analytics/export?days=7" style="float:right;font-size:12px;color:var(--primary);text-decoration:none;" target="_blank">📥 CSV Export (7 Days)</a>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;">
              <h4 style="color:#fff;margin:0 0 16px 0;font-size:14px;">🔄 Conversion Funnel</h4>
              <div id="funnel-container" style="color:var(--text-muted);font-size:13px;">Loading...</div>
            </div>

            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;">
              <h4 style="color:#fff;margin:0 0 16px 0;font-size:14px;">📊 Event Breakdown</h4>
              <canvas id="breakdownChart" height="200"></canvas>
            </div>
          </div>

          <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;">
            <h4 style="color:#fff;margin:0 0 16px 0;font-size:14px;">🕐 Hourly Distribution (Last 7 Days)</h4>
            <canvas id="hourlyChart" height="80"></canvas>
          </div>
        </div>
    </div>

    <!-- TAB: EVENT LOG -->
    <div id="tab-event-log" class="tab-pane">
        <div class="card" style="margin-bottom:24px;">
          <div class="card-title">📋 Purchase Event Log (All Purchase Attempts)</div>
          <div style="overflow-x:auto;">
            <table class="client-table">
              <thead>
                <tr>
                  <th>সময়</th>
                  <th>ইভেন্ট (Purchase Only)</th>
                  <th>Event ID</th>
                  <th>স্ট্যাটাস</th>
                </tr>
              </thead>
              <tbody>
                {purchase_logs_html}
              </tbody>
            </table>
          </div>
        </div>
        
        <div class="card" style="margin-bottom:24px;">
          <div class="card-title">📋 All Other Events</div>
          <div style="overflow-x:auto;">
            <table class="client-table">
              <thead>
                <tr>
                  <th>সময়</th>
                  <th>ইভেন্ট</th>
                  <th>Event ID</th>
                  <th>স্ট্যাটাস</th>
                </tr>
              </thead>
              <tbody>
                {all_logs_html}
              </tbody>
            </table>
          </div>
        </div>
    </div>

    <!-- TAB: DELAY PURCHASE -->
    <div id="tab-delay-purchase" class="tab-pane">
        {pending_html}
    </div>

    <!-- TAB: SETTINGS & SETUP -->
    <div id="tab-settings" class="tab-pane">
        

        
        <div class="card" style="margin-bottom:24px;border:1px solid rgba(16,185,129,0.2);margin-top:24px;">
          <div class="card-title">🧪 Event Testing & Debug</div>
          
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;">
              <h4 style="color:#fff;margin:0 0 12px 0;font-size:14px;">🚀 Send Test Event</h4>
              <select id="test-event-name" style="width:100%;padding:10px;background:#111827;color:#fff;border:1px solid var(--border);border-radius:8px;margin-bottom:10px;font-size:13px;outline:none;">
                <option value="PageView">PageView</option>
                <option value="ViewContent">ViewContent</option>
                <option value="AddToCart">AddToCart</option>
                <option value="InitiateCheckout">InitiateCheckout</option>
                <option value="Purchase">Purchase</option>
                <option value="Lead">Lead</option>
                <option value="CompleteRegistration">CompleteRegistration</option>
                <option value="Search">Search</option>
              </select>
              <button class="btn-sm btn-info" onclick="sendTestEvent()" style="width:100%;padding:10px;font-size:13px;">🧪 Send Test Event</button>
              <div id="test-result" style="margin-top:10px;font-size:12px;color:var(--text-muted);"></div>
            </div>

            <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;">
              <h4 style="color:#fff;margin:0 0 12px 0;font-size:14px;">🔍 Validate Event Payload</h4>
              <textarea id="validate-payload" style="width:100%;height:120px;padding:10px;background:#111827;color:var(--accent);border:1px solid var(--border);border-radius:8px;font-family:monospace;font-size:11px;resize:vertical;" placeholder='{"event_name":"Purchase","event_time":1234567890,"user_data":{"em":["test@example.com"]},"custom_data":{"value":1500,"currency":"BDT"}}'></textarea>
              <button class="btn-sm btn-info" onclick="validatePayload()" style="width:100%;padding:10px;font-size:13px;margin-top:8px;">🔍 Validate</button>
              <div id="validate-result" style="margin-top:10px;font-size:12px;"></div>
            </div>
          </div>

          <div style="margin-top:20px;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
              <h4 style="color:#fff;margin:0;font-size:14px;">📡 Live Event Stream (Last Hour)</h4>
              <button class="btn-sm btn-info" onclick="refreshLiveEvents()">🔄 Refresh</button>
            </div>
            <div id="live-events" style="max-height:300px;overflow-y:auto;font-family:monospace;font-size:11px;color:var(--text-muted);">
              Loading...
            </div>
          </div>
        </div>
    </div>
    """

    return HTMLResponse(client_html(f"Dashboard — {client.name}", body))

