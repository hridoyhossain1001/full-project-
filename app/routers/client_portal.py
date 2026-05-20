from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
import html
import datetime
import secrets
from typing import Optional
from sqlalchemy import and_

from app.database import get_db
from app.models.client import Client
from app.models.event_log import EventLog
from app.models.pending_event import PendingEvent
from app.routers.admin import STYLE, base_html, display_domain_url, mask_secret
from app.security import encrypt_token, decrypt_token
from app.limiter import limiter


CLIENT_STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;600;700;800&display=swap');

  :root {
    --bg-main: #060b18;
    --bg-sidebar: rgba(8, 14, 28, 0.98);
    --bg-card: rgba(13, 20, 40, 0.85);
    --bg-soft: rgba(22, 33, 62, 0.7);
    --border: rgba(148, 163, 184, 0.1);
    --border-glow: rgba(255, 139, 69, 0.28);
    --primary: #ff8b45;
    --primary-hover: #ffae6b;
    --primary-glow: rgba(255, 139, 69, 0.22);
    --violet: #8b5cf6;
    --violet-glow: rgba(139, 92, 246, 0.25);
    --cyan: #06b6d4;
    --text-main: #e2eaf8;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    --accent: #10b981;
    --accent-glow: rgba(16, 185, 129, 0.25);
    --danger: #f87171;
    --danger-glow: rgba(248, 113, 113, 0.2);
    --warning: #f59e0b;
    --sidebar-w: 272px;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background: var(--bg-main);
    background-image:
      radial-gradient(ellipse at 0% 0%, rgba(255,139,69,0.12) 0%, transparent 50%),
      radial-gradient(ellipse at 100% 100%, rgba(255,190,157,0.08) 0%, transparent 50%),
      radial-gradient(ellipse at 50% 50%, rgba(6,182,212,0.04) 0%, transparent 60%);
    color: var(--text-main);
    min-height: 100vh; display: flex; overflow: hidden; line-height: 1.6; font-size: 14px;
  }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,139,69,0.28); border-radius: 99px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,139,69,0.45); }

  .sidebar {
    width: var(--sidebar-w); background: var(--bg-sidebar); border-right: 1px solid var(--border);
    display: flex; flex-direction: column; height: 100vh; z-index: 10;
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); flex-shrink: 0;
  }
  .sidebar-logo {
    display: flex; align-items: center; gap: 12px; padding: 24px 20px 20px;
    border-bottom: 1px solid var(--border); margin-bottom: 8px;
  }
  .sidebar-logo-mark {
    width: 38px; height: 38px; border-radius: 11px;
    background: #ff8b45;
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-weight: 900; font-size: 18px; font-family: 'Outfit', sans-serif;
    box-shadow: 0 0 0 1px rgba(255,139,69,0.38), 0 8px 24px rgba(255,139,69,0.25);
    flex-shrink: 0; position: relative; overflow: hidden;
  }
  .sidebar-logo-mark::after {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, transparent 60%);
  }
  .sidebar-logo-text { display: flex; flex-direction: column; line-height: 1.2; }
  .sidebar-logo-text strong { font-size: 15px; font-weight: 800; color: #fff; font-family: 'Outfit', sans-serif; letter-spacing: -0.3px; }
  .sidebar-logo-text small { font-size: 11px; color: #7c8fb5; font-weight: 500; margin-top: 1px; }

  .sidebar-menu { display: flex; flex-direction: column; gap: 2px; flex: 1; padding: 8px 10px; overflow-y: auto; }

  .nav-section-label {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-dim); padding: 12px 10px 6px;
  }
  .nav-item {
    display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px;
    color: var(--text-muted); font-size: 13.5px; font-weight: 500; border-radius: 9px;
    cursor: pointer; transition: all 0.18s ease; text-decoration: none;
    border: 1px solid transparent; background: transparent; text-align: left;
    position: relative; overflow: hidden;
  }
  .nav-item::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 3px; border-radius: 0 3px 3px 0; background: transparent; transition: background 0.18s;
  }
  .nav-item:hover { background: rgba(148,163,184,0.07); color: #cbd5e1; }
  .nav-item.active {
    background: linear-gradient(90deg, rgba(255,139,69,0.18) 0%, rgba(255,139,69,0.05) 100%);
    color: #ffd5bd; border-color: rgba(255,139,69,0.18);
  }
  .nav-item.active::before { background: linear-gradient(180deg, var(--primary), var(--primary-hover)); }
  .nav-icon { width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 15px; opacity: 0.8; color: var(--primary); border: 1px solid rgba(255,139,69,0.18); border-radius: 7px; background: rgba(255,139,69,0.08); }
  .nav-item.active .nav-icon { opacity: 1; }
  .nav-upgrade {
    background: linear-gradient(135deg, rgba(255,139,69,0.24) 0%, rgba(59,130,246,0.12) 100%) !important;
    color: #ffd5bd !important; border-color: rgba(255,139,69,0.28) !important; font-weight: 600;
  }
  .nav-upgrade:hover {
    background: linear-gradient(135deg, rgba(255,139,69,0.35) 0%, rgba(255,174,107,0.2) 100%) !important;
    color: #fff !important;
  }

  .sidebar-footer { padding: 12px 10px 16px; border-top: 1px solid var(--border); margin-top: 4px; }
  .user-card {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
    background: rgba(255,255,255,0.03); border: 1px solid var(--border); margin-bottom: 8px;
  }
  .user-avatar {
    width: 34px; height: 34px; border-radius: 50%;
    background: linear-gradient(135deg, var(--primary), #3b82f6);
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 700; color: #111827; flex-shrink: 0;
    box-shadow: 0 0 0 2px rgba(255,139,69,0.3);
  }
  .user-info { flex: 1; min-width: 0; }
  .user-name { font-size: 13px; font-weight: 600; color: #e2eaf8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .user-role { font-size: 11px; color: var(--text-dim); }
  .user-status {
    width: 8px; height: 8px; border-radius: 50%; background: #10b981; flex-shrink: 0;
    box-shadow: 0 0 0 2px rgba(16,185,129,0.25); animation: pulse-dot 2.5s ease infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { box-shadow: 0 0 0 2px rgba(16,185,129,0.25); }
    50% { box-shadow: 0 0 0 4px rgba(16,185,129,0.12); }
  }

  .main-content { flex: 1; height: 100vh; overflow-y: auto; padding: 0 28px 60px; min-width: 0; }
  .content-wrapper { max-width: 1180px; margin: 0 auto; width: 100%; }

  .client-topbar {
    position: sticky; top: 0; z-index: 8; min-height: 68px;
    margin: 0 -28px 32px; padding: 0 28px; border-bottom: 1px solid var(--border);
    background: rgba(6,11,24,0.88); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .client-topbar-title { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }
  .client-topbar-actions { display: flex; align-items: center; gap: 8px; }
  .status-pill {
    display: flex; align-items: center; gap: 6px;
    border: 1px solid rgba(16,185,129,0.25); background: rgba(16,185,129,0.08); color: #6ee7b7;
    border-radius: 999px; padding: 5px 12px; font-size: 11px; font-weight: 700;
  }
  .status-pill::before {
    content: ''; width: 6px; height: 6px; border-radius: 50%; background: #10b981;
    display: inline-block; animation: pulse-dot 2s infinite;
  }
  .topbar-btn {
    border: 1px solid var(--border); background: rgba(255,255,255,0.04); color: var(--text-muted);
    border-radius: 999px; padding: 7px 14px; font-size: 12px; font-weight: 600;
    text-decoration: none; transition: all 0.2s; display: flex; align-items: center; gap: 5px;
  }
  .topbar-btn:hover { background: rgba(255,139,69,0.1); border-color: rgba(255,139,69,0.3); color: #ffd5bd; }

  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }
  .page-title { font-size: 26px; font-weight: 800; color: #fff; letter-spacing: -0.5px; font-family: 'Outfit', sans-serif; line-height: 1.2; }
  .page-sub { color: var(--text-muted); font-size: 13.5px; margin-top: 5px; }

  .card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 22px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.04);
    margin-bottom: 20px; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  }
  .card-title {
    font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 18px;
    display: flex; align-items: center; gap: 8px; line-height: 1.35; font-family: 'Outfit', sans-serif;
  }
  .card-title .icon {
    width: 30px; height: 30px; border-radius: 8px; background: rgba(255,139,69,0.12);
    display: inline-flex; align-items: center; justify-content: center; font-size: 15px; flex-shrink: 0; color: var(--primary);
  }

  .stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 22px; }
  .stat-box {
    background: rgba(255,255,255,0.025); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px 20px; position: relative; overflow: hidden;
    transition: border-color 0.2s, transform 0.2s;
  }
  .stat-box:hover { border-color: rgba(255,139,69,0.25); transform: translateY(-1px); }
  .stat-box::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,139,69,0.42), transparent);
  }
  .stat-box .num { font-size: 30px; font-weight: 800; color: #fff; line-height: 1.1; font-family: 'Outfit', sans-serif; }
  .stat-box .lbl { font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; margin-top: 6px; }
  .stat-box .stat-icon { position: absolute; right: 16px; top: 16px; font-size: 22px; opacity: 0.2; }

  .client-table { width: 100%; border-collapse: separate; border-spacing: 0; text-align: left; min-width: 720px; }
  .client-table th { padding: 11px 14px; font-size: 11px; color: var(--text-dim); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02); }
  .client-table td { padding: 13px 14px; font-size: 13px; border-bottom: 1px solid rgba(148,163,184,0.06); vertical-align: middle; transition: background 0.15s; }
  .client-table tr:hover td { background: rgba(255,139,69,0.035); }
  .client-table tr:last-child td { border-bottom: none; }
  .card:has(.client-table) { overflow-x: auto; }

  .badge { padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; display: inline-flex; align-items: center; gap: 4px; }
  .badge-success { background: rgba(16,185,129,0.12); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.22); }
  .badge-error { background: rgba(248,113,113,0.1); color: #fca5a5; border: 1px solid rgba(248,113,113,0.22); }

  .btn-sm { padding: 7px 14px; font-size: 12px; border-radius: 8px; border: 1px solid transparent; cursor: pointer; font-weight: 600; transition: all 0.18s ease; display: inline-flex; align-items: center; justify-content: center; gap: 5px; font-family: 'Inter', sans-serif; }
  .btn-primary { background: linear-gradient(135deg, var(--primary), var(--primary-hover)); color: #111827; box-shadow: 0 4px 14px rgba(255,139,69,0.28); }
  .btn-primary:hover { background: linear-gradient(135deg, var(--primary-hover), var(--primary)); transform: translateY(-1px); box-shadow: 0 6px 20px rgba(255,139,69,0.4); }
  .btn-danger { background: rgba(248,113,113,0.1); color: #fca5a5; border-color: rgba(248,113,113,0.22); }
  .btn-danger:hover { background: rgba(248,113,113,0.18); color: #fff; border-color: rgba(248,113,113,0.4); }
  .btn-info { background: rgba(255,139,69,0.12); color: #ffd5bd; border-color: rgba(255,139,69,0.22); }
  .btn-info:hover { background: rgba(255,139,69,0.2); border-color: rgba(255,139,69,0.4); }
  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 10px 20px; border-radius: 9px; background: linear-gradient(135deg, var(--primary), var(--primary-hover));
    color: #111827; font-weight: 700; font-size: 14px; border: none; cursor: pointer; text-decoration: none;
    transition: all 0.2s; box-shadow: 0 4px 14px rgba(255,139,69,0.28); font-family: 'Inter', sans-serif;
  }
  .btn:hover { background: linear-gradient(135deg, var(--primary-hover), var(--primary)); transform: translateY(-1px); box-shadow: 0 8px 24px rgba(255,139,69,0.4); }

  .copy-btn {
    background: rgba(255,139,69,0.15); color: #ffd5bd; border: 1px solid rgba(255,139,69,0.3);
    border-radius: 7px; padding: 5px 12px; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: all 0.18s ease; float: right; margin-top: 16px; margin-right: 6px;
    position: relative; z-index: 10; font-family: 'Inter', sans-serif;
  }
  .copy-btn:hover { background: rgba(255,139,69,0.28); border-color: rgba(255,139,69,0.5); transform: translateY(-1px); }

  .instr-box {
    background: rgba(2,8,22,0.9); border: 1px solid rgba(148,163,184,0.12); border-radius: 10px; padding: 14px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.7;
    color: #bfdbfe; white-space: pre-wrap; word-break: break-all; margin-top: 8px;
  }

  .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 0; overflow-x: auto; }
  .tab-btn {
    background: transparent; border: none; border-bottom: 2px solid transparent;
    color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer; padding: 10px 14px;
    border-radius: 0; transition: all 0.18s; white-space: nowrap; margin-bottom: -1px; font-family: 'Inter', sans-serif;
  }
  .tab-btn:hover { color: #cbd5e1; }
  .tab-btn.active { color: #ff8b45; border-bottom-color: #ff8b45; }

  .inner-tab-content { display: none; animation: fadeIn 0.25s ease; }
  .inner-tab-content.active { display: block; }
  .tab-pane { display: none; animation: fadeIn 0.28s ease; }
  .tab-pane.active { display: block; }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

  .form-group { margin-bottom: 18px; }
  .form-group label { display: block; font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 7px; }
  .form-group input { width: 100%; padding: 11px 14px; background: rgba(0,0,0,0.35); border: 1px solid var(--border); border-radius: 9px; color: #fff; font-size: 14px; outline: none; transition: border-color 0.18s, box-shadow 0.18s; font-family: 'Inter', sans-serif; }
  .form-group input:focus { border-color: rgba(255,139,69,0.5); box-shadow: 0 0 0 3px rgba(255,139,69,0.12); }

  .alert { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 10px; font-size: 13px; font-weight: 500; margin-bottom: 16px; }
  .alert-error { background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.25); color: #fca5a5; }
  .alert-success { background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25); color: #6ee7b7; }

  .hamburger { display: none; flex-direction: column; justify-content: center; gap: 5px; background: rgba(13,20,40,0.9); border: 1px solid var(--border); border-radius: 9px; cursor: pointer; padding: 9px; position: fixed; top: 14px; left: 14px; z-index: 200; backdrop-filter: blur(12px); }
  .hamburger span { display: block; width: 20px; height: 2px; background: #a0aec0; border-radius: 2px; transition: all 0.3s; }
  .sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65); z-index: 99; backdrop-filter: blur(4px); }
  .sidebar-overlay.open { display: block; }

  @media (max-width: 768px) {
    body { overflow: auto; }
    .hamburger { display: flex; }
    .sidebar { position: fixed; left: -290px; top: 0; height: 100vh; width: 270px; z-index: 100; transition: left 0.28s cubic-bezier(0.4,0,0.2,1); overflow-y: auto; }
    .sidebar.open { left: 0; box-shadow: 8px 0 40px rgba(0,0,0,0.6); }
    .main-content { height: auto; min-height: 100vh; padding: 0 14px 24px; }
    .client-topbar { margin: 0 -14px 22px; padding: 0 14px 0 60px; }
    .client-topbar-actions .topbar-btn { display: none; }
    .content-wrapper { max-width: 100%; }
    .header { margin-bottom: 18px; }
    .page-title { font-size: 20px; }
    .stat-row { grid-template-columns: 1fr 1fr; gap: 10px; }
    .stat-box .num { font-size: 24px; }
    .card { padding: 14px; border-radius: 12px; }
    .client-table td, .client-table th { padding: 9px 10px; font-size: 12px; }
    .tabs { gap: 2px; }
    .tab-btn { font-size: 12px; padding: 8px 10px; }
  }
  @media (max-width: 480px) {
    .stat-row { grid-template-columns: 1fr; }
    .main-content { padding: 60px 12px 20px; }
    .client-topbar { margin: 0 -12px 20px; padding-left: 56px; }
  }
</style>
"""

def client_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Buykori AdSync</title>
  <meta name="description" content="Buykori AdSync Client Portal — Manage your server-side event delivery.">
  {CLIENT_STYLE}
</head>
<body>
  <button class="hamburger" id="hamburger" onclick="toggleSidebar()" aria-label="Open menu">
    <span></span><span></span><span></span>
  </button>
  <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-logo">
      <div class="sidebar-logo-mark">B</div>
      <div class="sidebar-logo-text">
        <strong>Buykori AdSync</strong>
        <small>Client Portal</small>
      </div>
    </div>
    <nav class="sidebar-menu">
      <span class="nav-section-label">Overview</span>
      <a class="nav-item active" onclick="switchTab('tab-dashboard', this)"><span class="nav-icon">📊</span> Dashboard</a>
      <a class="nav-item" onclick="switchTab('tab-analytics', this)"><span class="nav-icon">📈</span> Analytics</a>
      <span class="nav-section-label">Events</span>
      <a class="nav-item" onclick="switchTab('tab-event-log', this)"><span class="nav-icon">📋</span> Event Log</a>
      <a class="nav-item" onclick="switchTab('tab-delay-purchase', this)"><span class="nav-icon">⏳</span> Pending Purchases</a>
      <span class="nav-section-label">Tools</span>
      <a class="nav-item" onclick="switchTab('tab-settings', this)"><span class="nav-icon">🔗</span> Campaign Builder</a>
      <a class="nav-item" onclick="switchTab('tab-settings', this)"><span class="nav-icon">⚙️</span> Setup Guide</a>
      <span class="nav-section-label">Account</span>
      <a class="nav-item nav-upgrade" onclick="alert('Coming soon. Please contact the admin for updates.')"><span class="nav-icon">⚡</span> Upgrade Plan</a>
    </nav>
    <div class="sidebar-footer">
      <div class="user-card">
        <div class="user-avatar">U</div>
        <div class="user-info">
          <div class="user-name">{title}</div>
          <div class="user-role">Store Owner</div>
        </div>
        <div class="user-status"></div>
      </div>
      <a href="/client/logout" class="nav-item" style="color:var(--danger);"><span class="nav-icon">🚪</span> Logout</a>
    </div>
  </aside>
  <main class="main-content">
    <header class="client-topbar">
      <div class="client-topbar-title">&#x26A1; Tracking Command Center</div>
      <div class="client-topbar-actions">
        <span class="status-pill">Production Ready</span>
        <a class="topbar-btn" href="/api/v1/plugin/download">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Download Plugin
        </a>
      </div>
    </header>
    <div class="content-wrapper">
      {body}
    </div>
  </main>
  <script>
    function switchTab(tabId, el) {{
      var tabs = document.getElementsByClassName('tab-pane');
      for (var i = 0; i < tabs.length; i++) {{ tabs[i].classList.remove('active'); }}
      var navs = document.getElementsByClassName('nav-item');
      for (var i = 0; i < navs.length; i++) {{ navs[i].classList.remove('active'); }}
      document.getElementById(tabId).classList.add('active');
      if (el) el.classList.add('active');
      var sidebar = document.getElementById('sidebar');
      if (sidebar && sidebar.classList.contains('open')) {{ toggleSidebar(); }}
    }}
    function toggleSidebar() {{
      var sidebar = document.getElementById('sidebar');
      var overlay = document.getElementById('sidebar-overlay');
      sidebar.classList.toggle('open');
      overlay.classList.toggle('open');
    }}
    function copyText(id) {{
      var t = document.getElementById(id);
      var textToCopy = t.dataset.secret || t.innerText || t.value;
      navigator.clipboard.writeText(textToCopy);
      var eventTarget = event.target;
      var origText = eventTarget.innerText;
      eventTarget.innerText = 'Copied!';
      setTimeout(() => eventTarget.innerText = origText, 1500);
    }}
    function escapeHtml(value) {{
      return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch) {{
        return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch];
      }});
    }}
    function revealSecret(id) {{
      var t = document.getElementById(id);
      if (!t || !t.dataset.secret) return;
      var hidden = t.dataset.hidden !== '0';
      t.innerText = hidden ? t.dataset.secret : t.dataset.masked;
      t.dataset.hidden = hidden ? '0' : '1';
    }}
    function openInnerTab(evt, tabId) {{
      var i, tc, tl;
      tc = document.getElementsByClassName('inner-tab-content');
      for (i = 0; i < tc.length; i++) {{ tc[i].className = tc[i].className.replace(' active', ''); }}
      tl = document.getElementsByClassName('tab-btn');
      for (i = 0; i < tl.length; i++) {{ tl[i].className = tl[i].className.replace(' active', ''); }}
      document.getElementById(tabId).className += ' active';
      evt.currentTarget.className += ' active';
    }}
    function convertUTCToLocal() {{
      document.querySelectorAll('.local-time[data-utc]').forEach(function(el) {{
        var utc = el.getAttribute('data-utc');
        if (!utc) return;
        try {{
          var d = new Date(utc);
          var opts = {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }};
          el.textContent = d.toLocaleString('en-GB', opts).replace(',', '');
        }} catch(e) {{}}
      }});
    }}
    document.addEventListener('DOMContentLoaded', convertUTCToLocal);
  </script>
</body>
</html>"""


router = APIRouter(tags=["Client Portal"])

def get_client_from_cookie(request: Request) -> Optional[str]:
    """Cookie থেকে encrypted session token পড়ে decrypt করে API key রিটার্ন করে।"""
    encrypted = request.cookies.get("client_session")
    if not encrypted:
        return None
    try:
        return decrypt_token(encrypted, allow_legacy_plaintext=False)
    except Exception:
        return None


async def get_client_from_portal_session(request: Request, db: AsyncSession) -> Optional[Client]:
    session_value = get_client_from_cookie(request)
    if not session_value:
        return None

    if session_value.startswith("client:"):
        try:
            _, client_id, session_secret = session_value.split(":", 2)
            result = await db.execute(select(Client).where(Client.id == int(client_id)))
            client = result.scalar_one_or_none()
            expected_secret = getattr(client, "portal_key", None) if client else None
            if client and expected_secret and secrets.compare_digest(session_secret, expected_secret):
                return client
            return None
        except (TypeError, ValueError):
            return None

    # Backward compatibility for old cookies that stored the API key directly.
    result = await db.execute(select(Client).where(Client.api_key == session_value))
    return result.scalar_one_or_none()

@router.get("/client", response_class=HTMLResponse, include_in_schema=False)
async def client_login_page(request: Request):
    api_key = get_client_from_cookie(request)
    if api_key:
        return RedirectResponse(url="/client/dashboard", status_code=303)

    body = """
    <style>
      body { justify-content: center; align-items: center; }
      .login-bg { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
      .login-blob { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.12; animation: float-blob 10s ease-in-out infinite alternate; }
      @keyframes float-blob { from { transform: translate(0,0) scale(1); } to { transform: translate(30px,-20px) scale(1.08); } }
      .login-wrap { position: relative; z-index: 1; width: 100%; max-width: 420px; padding: 24px 16px; }
      .login-logo { text-align: center; margin-bottom: 32px; }
      .login-logo-mark { width: 56px; height: 56px; border-radius: 16px; background: #ff8b45; display: inline-flex; align-items: center; justify-content: center; font-size: 26px; font-weight: 900; color: #fff; font-family: 'Outfit', sans-serif; box-shadow: 0 0 0 1px rgba(255,139,69,0.38), 0 12px 40px rgba(255,139,69,0.35); margin-bottom: 16px; }
      .login-logo h1 { font-size: 22px; font-weight: 800; color: #fff; font-family: 'Outfit', sans-serif; letter-spacing: -0.5px; margin: 0 0 6px; }
      .login-logo p { font-size: 13px; color: #7c8fb5; }
      .login-card { background: rgba(13,20,40,0.88); border: 1px solid rgba(148,163,184,0.1); border-radius: 18px; padding: 32px 28px; box-shadow: 0 24px 64px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05); backdrop-filter: blur(20px); }
      .login-label { display: block; font-size: 12px; font-weight: 700; color: #7c8fb5; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 8px; }
      .login-input { width: 100%; padding: 13px 14px; background: rgba(0,0,0,0.4); border: 1px solid rgba(148,163,184,0.12); border-radius: 10px; color: #fff; font-size: 14px; outline: none; transition: border-color 0.2s, box-shadow 0.2s; font-family: 'Inter', sans-serif; margin-bottom: 20px; }
      .login-input:focus { border-color: rgba(255,139,69,0.5); box-shadow: 0 0 0 3px rgba(255,139,69,0.15); }
      .login-btn { width: 100%; padding: 13px; background: linear-gradient(135deg, #ff8b45 0%, #ffae6b 100%); color: #111827; font-size: 15px; font-weight: 700; border: none; border-radius: 10px; cursor: pointer; font-family: 'Outfit', sans-serif; box-shadow: 0 6px 24px rgba(255,139,69,0.35); transition: all 0.2s; }
      .login-btn:hover { background: linear-gradient(135deg, #ffae6b 0%, #ff8b45 100%); transform: translateY(-1px); box-shadow: 0 10px 32px rgba(255,139,69,0.45); }
      .login-footer { text-align: center; margin-top: 20px; font-size: 12px; color: #475569; }
    </style>
    <div class="login-bg">
      <div class="login-blob" style="width:500px;height:500px;top:-200px;left:-150px;background:#ff8b45;"></div>
      <div class="login-blob" style="width:400px;height:400px;bottom:-150px;right:-100px;background:#ffae6b;animation-delay:-4s;"></div>
      <div class="login-blob" style="width:300px;height:300px;top:50%;left:60%;background:#06b6d4;animation-delay:-7s;"></div>
    </div>
    <div class="login-wrap">
      <div class="login-logo">
        <div class="login-logo-mark">B</div>
        <h1>Buykori AdSync</h1>
        <p>Sign in to your Client Portal</p>
      </div>
      <div class="login-card">
        <form action="/client/login" method="post" autocomplete="off">
          <label class="login-label" for="api_key_input">Portal Login Key</label>
          <input class="login-input" type="password" id="api_key_input" name="api_key" required placeholder="Paste your Portal Login Key here…" autocomplete="off">
          <button type="submit" class="login-btn">Sign In to Dashboard &rarr;</button>
        </form>
      </div>
      <div class="login-footer">&copy; Buykori AdSync &mdash; Secure Server-Side Tracking</div>
    </div>
    """
    return HTMLResponse(client_html("Client Login", body))

@router.post("/client/login", include_in_schema=False)
@limiter.limit("5/minute")
async def client_login(request: Request, response: Response, api_key: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(or_(Client.portal_key == api_key, Client.api_key == api_key))
    )
    client = result.scalar_one_or_none()
    portal_key = getattr(client, "portal_key", None) if client else None
    portal_key_ok = bool(portal_key) and secrets.compare_digest(portal_key, api_key)
    legacy_api_key_ok = bool(client and not portal_key) and secrets.compare_digest(client.api_key, api_key)

    if not client or not client.is_active or not (portal_key_ok or legacy_api_key_ok):
        body = """
        <style>
          body { justify-content: center; align-items: center; }
          .err-wrap { position: relative; z-index: 1; width: 100%; max-width: 400px; padding: 24px 16px; text-align: center; }
          .err-card { background: rgba(13,20,40,0.88); border: 1px solid rgba(248,113,113,0.2); border-radius: 16px; padding: 32px 24px; box-shadow: 0 24px 64px rgba(0,0,0,0.45); backdrop-filter: blur(20px); margin-bottom: 16px; }
          .err-icon { font-size: 48px; margin-bottom: 16px; }
          .err-title { font-size: 18px; font-weight: 800; color: #fca5a5; font-family: 'Outfit', sans-serif; margin-bottom: 8px; }
          .err-sub { font-size: 13px; color: #7c8fb5; margin-bottom: 24px; }
          .err-btn { display: inline-flex; align-items: center; gap: 6px; padding: 11px 28px; border-radius: 10px; background: rgba(255,255,255,0.06); color: #e2eaf8; border: 1px solid rgba(255,255,255,0.1); font-size: 14px; font-weight: 600; text-decoration: none; transition: all 0.2s; }
          .err-btn:hover { background: rgba(255,255,255,0.1); }
        </style>
        <div class="err-wrap">
          <div class="err-card">
            <div class="err-icon">🔐</div>
            <div class="err-title">Access Denied</div>
            <div class="err-sub">Invalid or inactive Portal Login Key. Please check your key and try again.</div>
            <a href="/client" class="err-btn">&larr; Back to Login</a>
          </div>
        </div>
        """
        return HTMLResponse(client_html("Login Failed", body), status_code=401)

    redirect = RedirectResponse(url="/client/dashboard", status_code=303)
    redirect.set_cookie(
        key="client_session",
        value=encrypt_token(f"client:{client.id}:{getattr(client, 'portal_key', None) or client.api_key}"),
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
    client = await get_client_from_portal_session(request, db)
    if not client:
        return RedirectResponse(url="/client", status_code=303)

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
        utc_iso = log.created_at.replace(tzinfo=datetime.timezone.utc).isoformat() if log.created_at else ""
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span class="badge badge-success">✅ Success</span>'
            if log.status == "success"
            else '<span class="badge badge-error">❌ Failed</span>'
        )
        dashboard_logs_html += f"""
        <tr>
          <td class="local-time" data-utc="{utc_iso}" style="color:var(--text-muted);font-size:12px">{time_str}</td>
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
        utc_iso = log.created_at.replace(tzinfo=datetime.timezone.utc).isoformat() if log.created_at else ""
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span class="badge badge-success">✅ Success</span>'
            if log.status == "success"
            else '<span class="badge badge-error">❌ Failed</span>'
        )
        purchase_logs_html += f"""
        <tr>
          <td class="local-time" data-utc="{utc_iso}" style="color:var(--text-muted);font-size:12px">{time_str}</td>
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
        utc_iso = log.created_at.replace(tzinfo=datetime.timezone.utc).isoformat() if log.created_at else ""
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span class="badge badge-success">✅ Success</span>'
            if log.status == "success"
            else '<span class="badge badge-error">❌ Failed</span>'
        )
        all_logs_html += f"""
        <tr>
          <td class="local-time" data-utc="{utc_iso}" style="color:var(--text-muted);font-size:12px">{time_str}</td>
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
        <button class="btn-sm btn-danger" onclick="cancelSelected()" style="font-size:12px;">❌ Cancel Selected</button>
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
    if "x-forwarded-proto" in request.headers:
        scheme = request.headers.get("x-forwarded-proto")
        host = request.headers.get("host", "localhost")
        gateway_origin = f"{scheme}://{host}"
    else:
        gateway_origin = base_url
    endpoint = f"{base_url}/api/v1/events"
    tracker_key = getattr(client, "public_key", None) or client.api_key
    tracker_url = f"{gateway_origin}/t.js?key={tracker_key}"
    safe_client_name = html.escape(client.name, quote=True)
    safe_api_key = html.escape(client.api_key, quote=True)
    masked_api_key = html.escape(mask_secret(client.api_key))
    safe_endpoint = html.escape(endpoint, quote=True)
    safe_tracker_url = html.escape(tracker_url, quote=True)
    safe_capi_origin = html.escape(display_domain_url(client.domain) or "https://www.your-domain.com", quote=True)

    # Instructions body (Reused from admin.py)
    instructions_html = f"""
    <div class="card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">🔑</span> আপনার API Key</div>
      <p style="color:#888;font-size:13px;margin-bottom:10px">এই Key-টি গোপন রাখুন। কখনো Browser/JS-এ পাবলিকলি রাখবেন না। শুধু সার্ভার বা GTM থেকে ব্যবহার করুন।</p>
      <button class="copy-btn" onclick="copyText('api_key')">Copy</button>
      <button class="copy-btn" onclick="revealSecret('api_key')" style="margin-right:6px">Show</button>
      <div class="instr-box" id="api_key" data-secret="{safe_api_key}" data-masked="{masked_api_key}" data-hidden="1">{masked_api_key}</div>
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
      <button class="tab-btn active" onclick="openInnerTab(event, 'tab-easy')">🚀 Easy Setup</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-generator')">🛠️ Event Generator</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-gtm')">⚙️ GTM Server</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-wp')">📝 WordPress</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-custom')">💻 Custom</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-test')">🧪 Testing</button>
    </div>

    <!-- GENERATOR TAB -->
    <div id="tab-generator" class="inner-tab-content card" style="margin-bottom:20px">
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
    <div id="tab-easy" class="inner-tab-content active card" style="margin-bottom:20px">
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
    <div id="tab-wp" class="inner-tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">📝</span> WordPress Setup (সবচেয়ে সহজ নিয়ম)</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
                <!-- ★ Plugin Download Section ★ -->
        <div style="margin-bottom:24px;padding:20px;background:linear-gradient(135deg,rgba(79,70,229,0.12),rgba(0,230,118,0.08));border:1px solid rgba(79,70,229,0.3);border-radius:12px;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
            <span style="font-size:28px;">🔌</span>
            <div>
              <strong style="color:#fff;font-size:16px;">Buykori AdSync WordPress Plugin</strong><br>
              <span style="color:#aaa;font-size:13px;">সবচেয়ে সহজ পদ্ধতি — ইন্সটল করুন, API Key বসান, ব্যাস!</span>
            </div>
          </div>
          <a href="/api/v1/plugin/download" class="btn" style="display:inline-flex;align-items:center;gap:8px;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600;font-size:14px;border:none;cursor:pointer;transition:background 0.2s;" onmouseover="this.style.background='#4338ca'" onmouseout="this.style.background='#4f46e5'">
            ⬇️ Download Plugin (.zip)
          </a>
          <div style="margin-top:14px;font-size:13px;color:#aaa;line-height:1.8">
            <strong style="color:#00e676">ইন্সটল করার ধাপ:</strong><br>
            <strong style="color:#fff">১.</strong> উপরের বাটনে ক্লিক করে ZIP ফাইলটি ডাউনলোড করুন।<br>
            <strong style="color:#fff">২.</strong> WordPress Admin → <code>Plugins → Add New → Upload Plugin</code> এ যান।<br>
            <strong style="color:#fff">৩.</strong> ডাউনলোড করা ZIP ফাইলটি আপলোড করুন এবং <strong style="color:#fff">Activate</strong> দিন।<br>
            <strong style="color:#fff">৪.</strong> বাম মেনু থেকে <code>Buykori AdSync</code> এ গিয়ে আপনার <strong style="color:#4f46e5">API Key</strong> পেস্ট করে Save দিন।<br>
            <strong style="color:#00e676">🎉 ব্যাস! সব ইভেন্ট অটোমেটিক ট্র্যাক হওয়া শুরু হবে!</strong>
          </div>
          <div style="margin-top:12px;padding:10px 14px;background:rgba(0,230,118,0.06);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:12px;color:#aaa;line-height:1.8">
            ✅ PageView, ViewContent, AddToCart, Checkout, Purchase — সব অটো ট্র্যাক<br>
            ✅ Lead, Search, ViewCart, RemoveFromCart, AddPaymentInfo সাপোর্ট<br>
            ✅ SHA-256 PII হ্যাশিং ও কুকি ক্যাপচার বিল্ট-ইন<br>
            ✅ Deferred Purchase (COD) সাপোর্ট<br>
            ✅ Custom Event Builder বিল্ট-ইন
          </div>
        </div>

        <div style="margin-bottom:20px;padding:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:8px;text-align:center;font-size:13px;color:#888;">
          <span style="color:#aaa">Non-WooCommerce/custom site হলে শুধু নিচের site JS ব্যবহার করুন। WooCommerce store হলে official plugin-ই ব্যবহার করবেন।</span>
        </div>

        <div style="margin:12px 0;padding:12px;background:rgba(255,82,82,0.08);border:1px solid rgba(255,82,82,0.25);border-radius:8px;color:#ffb4b4;font-size:13px;line-height:1.7;">
          ⚠️ Old manual WooCommerce snippets removed. Plugin active থাকা অবস্থায় extra snippet দিলে Purchase/AddToCart/ViewContent duplicate হতে পারে।
        </div>
        <p><strong style="color:#fff">Custom site JS:</strong> WordPress ছাড়া custom website হলে head/footer অংশে এই script দিন।</p>
        <button class="copy-btn" onclick="copyText('wp_pv_easy')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_pv_easy">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;</div>
        <div style="margin-top:16px;padding:14px;background:rgba(0,230,118,0.05);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#00e676">✅ Clean setup:</strong><br>
          WooCommerce tracking = official plugin. Custom/non-Woo page tracking = site JS. Old ecommerce snippet আর দরকার নেই।
        </div>
      </div>
    </div>
    """

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
      <button class="tab-btn active" onclick="openInnerTab(event, 'tab-easy')">🚀 Easy Setup</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-generator')">🛠️ Event Generator</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-gtm')">⚙️ GTM Server</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-wp')">📝 WordPress</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-custom')">💻 Custom</button>
      <button class="tab-btn" onclick="openInnerTab(event, 'tab-test')">🧪 Testing</button>
    </div>

    <!-- GENERATOR TAB -->
    <div id="tab-generator" class="inner-tab-content card" style="margin-bottom:20px">
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
    <div id="tab-easy" class="inner-tab-content active card" style="margin-bottom:20px">
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
    <div id="tab-wp" class="inner-tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">📝</span> WordPress Setup (সবচেয়ে সহজ নিয়ম)</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
                <!-- ★ Plugin Download Section ★ -->
        <div style="margin-bottom:24px;padding:20px;background:linear-gradient(135deg,rgba(79,70,229,0.12),rgba(0,230,118,0.08));border:1px solid rgba(79,70,229,0.3);border-radius:12px;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
            <span style="font-size:28px;">🔌</span>
            <div>
              <strong style="color:#fff;font-size:16px;">Buykori AdSync WordPress Plugin</strong><br>
              <span style="color:#aaa;font-size:13px;">সবচেয়ে সহজ পদ্ধতি — ইন্সটল করুন, API Key বসান, ব্যাস!</span>
            </div>
          </div>
          <a href="/api/v1/plugin/download" class="btn" style="display:inline-flex;align-items:center;gap:8px;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600;font-size:14px;border:none;cursor:pointer;transition:background 0.2s;" onmouseover="this.style.background='#4338ca'" onmouseout="this.style.background='#4f46e5'">
            ⬇️ Download Plugin (.zip)
          </a>
          <div style="margin-top:14px;font-size:13px;color:#aaa;line-height:1.8">
            <strong style="color:#00e676">ইন্সটল করার ধাপ:</strong><br>
            <strong style="color:#fff">১.</strong> উপরের বাটনে ক্লিক করে ZIP ফাইলটি ডাউনলোড করুন।<br>
            <strong style="color:#fff">২.</strong> WordPress Admin → <code>Plugins → Add New → Upload Plugin</code> এ যান।<br>
            <strong style="color:#fff">৩.</strong> ডাউনলোড করা ZIP ফাইলটি আপলোড করুন এবং <strong style="color:#fff">Activate</strong> দিন।<br>
            <strong style="color:#fff">৪.</strong> বাম মেনু থেকে <code>Buykori AdSync</code> এ গিয়ে আপনার <strong style="color:#4f46e5">API Key</strong> পেস্ট করে Save দিন।<br>
            <strong style="color:#00e676">🎉 ব্যাস! সব ইভেন্ট অটোমেটিক ট্র্যাক হওয়া শুরু হবে!</strong>
          </div>
          <div style="margin-top:12px;padding:10px 14px;background:rgba(0,230,118,0.06);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:12px;color:#aaa;line-height:1.8">
            ✅ PageView, ViewContent, AddToCart, Checkout, Purchase — সব অটো ট্র্যাক<br>
            ✅ Lead, Search, ViewCart, RemoveFromCart, AddPaymentInfo সাপোর্ট<br>
            ✅ SHA-256 PII হ্যাশিং ও কুকি ক্যাপচার বিল্ট-ইন<br>
            ✅ Deferred Purchase (COD) সাপোর্ট<br>
            ✅ Custom Event Builder বিল্ট-ইন
          </div>
        </div>

        <div style="margin-bottom:20px;padding:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:8px;text-align:center;font-size:13px;color:#888;">
          <span style="color:#aaa">Non-WooCommerce/custom site হলে শুধু নিচের site JS ব্যবহার করুন। WooCommerce store হলে official plugin-ই ব্যবহার করবেন।</span>
        </div>

        <div style="margin:12px 0;padding:12px;background:rgba(255,82,82,0.08);border:1px solid rgba(255,82,82,0.25);border-radius:8px;color:#ffb4b4;font-size:13px;line-height:1.7;">
          ⚠️ Old manual WooCommerce snippets removed. Plugin active থাকা অবস্থায় extra snippet দিলে Purchase/AddToCart/ViewContent duplicate হতে পারে।
        </div>
        <p><strong style="color:#fff">Custom site JS:</strong> WordPress ছাড়া custom website হলে head/footer অংশে এই script দিন।</p>
        <button class="copy-btn" onclick="copyText('wp_pv_easy')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_pv_easy">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;</div>
        <div style="margin-top:16px;padding:14px;background:rgba(0,230,118,0.05);border:1px solid rgba(0,230,118,0.15);border-radius:8px;font-size:13px;color:#aaa;line-height:1.9">
          <strong style="color:#00e676">✅ Clean setup:</strong><br>
          WooCommerce tracking = official plugin. Custom/non-Woo page tracking = site JS. Old ecommerce snippet আর দরকার নেই।
        </div>
      </div>
    </div>

    <!-- CUSTOM TAB -->
    <div id="tab-custom" class="inner-tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">💻</span> Custom Website Integration Guide</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <div style="margin-bottom:16px;padding:14px;background:rgba(0,230,118,0.06);border:1px solid rgba(0,230,118,0.18);border-radius:8px;color:#b7f7cf;">
          <strong style="color:#00e676">Recommended:</strong> Purchase, Lead, registration, confirmed order backend/server থেকে পাঠান। PageView, ViewContent, AddToCart browser tracker দিয়েও পাঠানো যায়।
        </div>

        <p><strong style="color:#fff">১. Backend API endpoint</strong></p>
        <p style="color:#888;font-size:13px;margin-bottom:8px">যেকোনো custom website backend থেকে নিচের endpoint-এ JSON POST করুন। Server API key কখনো frontend JavaScript-এ রাখবেন না।</p>
        <button class="copy-btn" onclick="copyText('custom_endpoint_contract')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="custom_endpoint_contract">POST {safe_endpoint}
Headers:
  Content-Type: application/json
  X-API-Key: {safe_api_key}
  X-CAPI-Origin: {safe_capi_origin}
  X-CAPI-Timestamp: UNIX_TIMESTAMP
  X-CAPI-Signature: HMAC_SHA256(timestamp + "." + raw_body, api_key)</div>

        <br>
        <p><strong style="color:#fff">২. Purchase payload example</strong></p>
        <button class="copy-btn" onclick="copyText('custom_purchase_payload')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="custom_purchase_payload">{{
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
}}</div>

        <br>
        <p><strong style="color:#fff">৩. cURL test</strong></p>
        <button class="copy-btn" onclick="copyText('custom_curl')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="custom_curl">curl -X POST "{safe_endpoint}" \
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
  }}'</div>

        <br>
        <p><strong style="color:#fff">৪. Browser tracker option</strong></p>
        <p style="color:#888;font-size:13px;margin-bottom:8px">Backend না থাকলে public tracker key দিয়ে browser script ব্যবহার করা যাবে।</p>
        <button class="copy-btn" onclick="copyText('custom_browser_script')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="custom_browser_script">&lt;script src="{safe_tracker_url}" defer&gt;&lt;/script&gt;

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
&lt;/script&gt;</div>

        <div style="margin-top:16px;padding:14px;background:rgba(255,171,0,0.06);border:1px solid rgba(255,171,0,0.2);border-radius:8px;font-size:13px;color:#ffda7a;line-height:1.9">
          <strong>Must-follow rules:</strong><br>
          • <code>event_id</code> unique রাখুন। Purchase হলে order ID ব্যবহার করুন।<br>
          • <code>content_ids</code> Facebook/TikTok catalog product ID-এর সাথে exact match করতে হবে।<br>
          • Email/phone raw দিলেও server auto SHA-256 hash করবে।<br>
          • Same event browser + server দুদিক থেকে পাঠালে same <code>event_id</code> দিন।
        </div>
      </div>
    </div>
    """

    body = f"""
    <div class="header">
        <div>
            <h1 class="page-title">👋 Welcome, {safe_client_name}</h1>
            <p class="page-sub">আপনার Buykori AdSync Dashboard — সব ঠিকঠাক চলছে</p>
        </div>
    </div>

    <!-- TAB: DASHBOARD -->
    <div id="tab-dashboard" class="tab-pane active">
        <div class="stat-row">
          <div class="stat-box" style="border-color:rgba(59,130,246,0.2);">
            <div class="stat-icon">⚡</div>
            <div class="num" style="background:linear-gradient(135deg,#60a5fa,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{success_count}</div>
            <div class="lbl">Successful Events Today</div>
          </div>
          <div class="stat-box" style="border-color:{'rgba(16,185,129,0.25)' if success_rate > 90 else 'rgba(245,158,11,0.25)'}">
            <div class="stat-icon">{'✅' if success_rate > 90 else '⚠️'}</div>
            <div class="num" style="color:{'#10b981' if success_rate > 90 else '#f59e0b'}">{success_rate}%</div>
            <div class="lbl">Delivery Success Rate</div>
          </div>
          <div class="stat-box" style="border-color:rgba(248,113,113,0.2);">
            <div class="stat-icon">❌</div>
            <div class="num" style="color:#f87171;">{failed_count}</div>
            <div class="lbl">Failed Events Today</div>
          </div>
          <div class="stat-box" style="border-color:rgba(139,92,246,0.2);">
            <div class="stat-icon">📦</div>
            <div class="num" style="color:#a78bfa;">{total}</div>
            <div class="lbl">Total Events Today</div>
          </div>
        </div>

        <div class="card" style="margin-bottom:20px;border-color:rgba(16,185,129,0.2);">
          <div class="card-title">
            <span class="icon" style="background:rgba(16,185,129,0.12);">🩺</span>
            Signal Health Doctor
          </div>
          <div id="signal-doctor-panel" style="color:var(--text-muted);font-size:13px;padding:12px 0;">Loading signal health...</div>
        </div>

        <div class="card" style="margin-bottom:20px;">
          <div class="card-title">
            <span class="icon" style="background:rgba(99,102,241,0.12);">📈</span>
            গত ৭ দিনের ইভেন্ট ট্র্যাফিক
          </div>
          <canvas id="eventsChart" height="110"></canvas>
        </div>

        <div class="card" style="margin-bottom:20px;">
          <div class="card-title">
            <span class="icon" style="background:rgba(6,182,212,0.12);">📋</span>
            Recent Event Log
            <span style="margin-left:auto;font-size:11px;font-weight:500;color:var(--text-dim);background:rgba(255,255,255,0.04);border:1px solid var(--border);padding:3px 10px;border-radius:999px;">Last 15 events</span>
          </div>
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
          <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:20px;margin-top:20px;">
            <h4 style="color:#fff;margin:0 0 16px 0;font-size:14px;">Campaign Performance (UTM)</h4>
            <div style="overflow-x:auto;">
              <table class="client-table">
                <thead><tr><th>Source</th><th>Campaign</th><th>View</th><th>Cart</th><th>Checkout</th><th>Purchase</th><th>Revenue</th></tr></thead>
                <tbody id="campaign-performance-body">
                  <tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:20px">Loading...</td></tr>
                </tbody>
              </table>
            </div>
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

        <!-- CAMPAIGN URL BUILDER -->
        <div class="card" style="margin-bottom:24px;border:1px solid rgba(0,230,118,0.22);">
          <div class="card-title"><span class="icon">🔗</span> Campaign URL Builder</div>

          <div style="display:grid;grid-template-columns:1.2fr 0.8fr;gap:20px;">
            <div>
              <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Landing/Product URL</label>
              <input type="text" id="campaign-url-base" value="{safe_capi_origin}" placeholder="https://your-site.com/product/item" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;margin-bottom:12px;">

              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div>
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Platform</label>
                  <select id="campaign-platform" onchange="updateCampaignMedium()" style="width:100%;padding:10px 12px;background:#111827;border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                    <option value="facebook">Facebook</option>
                    <option value="tiktok">TikTok</option>
                    <option value="google">Google</option>
                    <option value="instagram">Instagram</option>
                    <option value="youtube">YouTube</option>
                    <option value="email">Email</option>
                    <option value="whatsapp">WhatsApp</option>
                  </select>
                </div>
                <div>
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Medium</label>
                  <input type="text" id="campaign-medium" value="paid_social" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                </div>
              </div>
            </div>

            <div>
              <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Campaign Name</label>
              <input type="text" id="campaign-name" placeholder="eid_sale_tshirt" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;margin-bottom:12px;">

              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div>
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Content</label>
                  <input type="text" id="campaign-content" placeholder="video_1" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                </div>
                <div>
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Term</label>
                  <input type="text" id="campaign-term" placeholder="optional" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                </div>
              </div>
            </div>
          </div>

          <div id="campaign-builder-output" class="instr-box" style="margin-top:14px;word-break:break-all;color:#cbd5e1;">Generated campaign URL will appear here</div>
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px;">
            <button type="button" class="btn-sm btn-primary" onclick="generateCampaignUrl()" style="font-size:12px;">Generate URL</button>
            <button type="button" class="copy-btn" onclick="copyText('campaign-builder-output')">Copy</button>
            <span id="campaign-builder-status" style="font-size:12px;color:#94a3b8;"></span>
          </div>
        </div>

        <!-- UPDATE CONFIGURATION FORM -->
        <div class="card" style="margin-bottom:24px;border:1px solid rgba(79,70,229,0.3);">
          <div class="card-title"><span class="icon">⚙️</span> আপনার Integration Settings আপডেট করুন</div>

          <form action="/client/settings/update" method="post">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">

              <!-- LEFT: Facebook & General -->
              <div>
                <div style="font-size:12px;color:#7e57c2;font-weight:700;text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:8px;margin-bottom:16px;">🔵 Facebook CAPI</div>

                <div style="margin-bottom:14px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Facebook Pixel ID</label>
                  <input type="text" name="pixel_id" value="{html.escape(client.pixel_id or '', quote=True)}" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                </div>

                <div style="margin-bottom:14px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">CAPI Access Token</label>
                  <input type="text" name="access_token" placeholder="{'[Encrypted — paste new to update]' if client.access_token else 'Paste token...'}" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                  <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#cbd5e1;font-size:13px;"><input type="checkbox" name="enable_facebook" value="1" {'checked' if getattr(client, 'enable_facebook', True) else ''}> Facebook CAPI delivery ON</label>
                  <div style="font-size:11px;color:#facc15;margin-top:4px;">⚠️ খালি রাখলে আগের টোকেন থাকবে।</div>
                </div>

                <div style="margin-bottom:14px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">Test Event Code (FB Testing)</label>
                  <input type="text" name="test_event_code" value="{html.escape(client.test_event_code or '', quote=True)}" placeholder="TEST12345" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                  <div style="font-size:11px;color:#94a3b8;margin-top:4px;">FB Events Manager থেকে কোড নিয়ে এখানে দিন। লাইভে খালি রাখুন।</div>
                </div>
              </div>

              <!-- RIGHT: TikTok & GA4 -->
              <div>
                <div style="font-size:12px;color:#9575cd;font-weight:700;text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:8px;margin-bottom:16px;">🎵 TikTok CAPI</div>

                <div style="margin-bottom:14px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">TikTok Pixel ID</label>
                  <input type="text" name="tiktok_pixel_id" value="{html.escape(client.tiktok_pixel_id or '', quote=True)}" placeholder="C1234567890" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                </div>

                <div style="margin-bottom:20px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">TikTok Access Token</label>
                  <input type="text" name="tiktok_access_token" placeholder="{'[Encrypted — paste new to update]' if client.tiktok_access_token else 'Paste TikTok token...'}" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                  <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#cbd5e1;font-size:13px;"><input type="checkbox" name="enable_tiktok" value="1" {'checked' if getattr(client, 'enable_tiktok', True) else ''}> TikTok CAPI delivery ON</label>
                  <div style="font-size:11px;color:#facc15;margin-top:4px;">⚠️ খালি রাখলে আগের টোকেন থাকবে।</div>
                </div>

                <div style="margin-bottom:14px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">TikTok Test Event Code (TikTok Testing)</label>
                  <input type="text" name="tiktok_test_event_code" value="{html.escape(client.tiktok_test_event_code or '', quote=True)}" placeholder="TEST38483" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                  <div style="font-size:11px;color:#94a3b8;margin-top:4px;">TikTok Events Manager থেকে টেস্ট কোড নিয়ে এখানে দিন। লাইভে খালি রাখুন।</div>
                </div>

                <div style="font-size:12px;color:#00a1f1;font-weight:700;text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:8px;margin-bottom:16px;margin-top:20px;">📊 GA4 Server-Side</div>

                <div style="margin-bottom:14px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">GA4 Measurement ID</label>
                  <input type="text" name="ga4_measurement_id" value="{{client.ga4_measurement_id or ''}}" placeholder="G-XXXXXXXXXX" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                </div>

                <div style="margin-bottom:20px;">
                  <label style="display:block;font-size:13px;color:#a8b3c7;margin-bottom:6px;">GA4 API Secret</label>
                  <input type="text" name="ga4_api_secret" placeholder="{'[Encrypted — paste new to update]' if client.ga4_api_secret else 'Paste GA4 API Secret...'}" style="width:100%;padding:10px 12px;background:rgba(0,0,0,0.35);border:1px solid rgba(148,163,184,0.18);border-radius:8px;color:#fff;font-size:13px;outline:none;">
                  <label style="display:flex;align-items:center;gap:8px;margin-top:10px;color:#cbd5e1;font-size:13px;"><input type="checkbox" name="enable_ga4" value="1" {'checked' if getattr(client, 'enable_ga4', True) else ''}> GA4 server-side delivery ON</label>
                  <div style="font-size:11px;color:#facc15;margin-top:4px;">⚠️ খালি রাখলে আগের secret থাকবে।</div>
                </div>

                <div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:16px;">
                  <button type="submit" class="btn-sm btn-primary" style="padding:10px 24px;font-size:14px;">💾 Settings সংরক্ষণ করুন</button>
                </div>
              </form>
            </div>

            <!-- RIGHT: Quick Info Box -->
            <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(79,70,229,0.15);border-radius:12px;padding:20px;height:fit-content;">
              <h4 style="color:#fff;margin:0 0 16px 0;font-size:14px;">💡 জানা দরকার</h4>
              <div style="font-size:13px;color:#94a3b8;line-height:1.9;">
                <div style="margin-bottom:12px;padding:10px;background:rgba(79,70,229,0.08);border-radius:8px;border-left:3px solid #4f46e5;">
                  <strong style="color:#a5b4fc;">Facebook CAPI:</strong><br>
                  আপনার FB Pixel ID এবং CAPI Token সঠিক থাকলে ইভেন্টগুলো Facebook-এ যাবে।
                </div>
                <div style="margin-bottom:12px;padding:10px;background:rgba(149,117,205,0.08);border-radius:8px;border-left:3px solid #9575cd;">
                  <strong style="color:#ce93d8;">TikTok CAPI:</strong><br>
                  TikTok Pixel ID এবং Access Token দিলে ইভেন্ট TikTok-এও যাবে।
                </div>
                <div style="margin-bottom:12px;padding:10px;background:rgba(0,161,241,0.08);border-radius:8px;border-left:3px solid #00a1f1;">
                  <strong style="color:#7dd3fc;">GA4 Server-Side:</strong><br>
                  Measurement ID এবং API Secret দিলে GA4-তেও ডেটা যাবে।
                </div>
                <div style="padding:10px;background:rgba(250,204,21,0.06);border-radius:8px;border-left:3px solid #facc15;">
                  <strong style="color:#fde68a;">Test Event Code:</strong><br>
                  শুধু টেস্টিং করার সময় এই কোড দিন। লাইভে অবশ্যই খালি রাখুন!
                </div>
              </div>
            </div>
          </div>
        </div>

        {instructions_html}
        


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
              <textarea id="validate-payload" style="width:100%;height:120px;padding:10px;background:#111827;color:var(--accent);border:1px solid var(--border);border-radius:8px;font-family:monospace;font-size:11px;resize:vertical;" placeholder='{{"event_name":"Purchase","event_time":1234567890,"user_data":{{"em":["test@example.com"]}},"custom_data":{{"value":1500,"currency":"BDT"}}}}'></textarea>
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

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>

<script>
    function slugifyUtm(value) {{
      return String(value || '')
        .trim()
        .toLowerCase()
        .replace(/\\s+/g, '_')
        .replace(/[^a-z0-9_.-]/g, '')
        .replace(/_+/g, '_')
        .replace(/^_+|_+$/g, '');
    }}

    function updateCampaignMedium() {{
      var platformEl = document.getElementById('campaign-platform');
      var mediumEl = document.getElementById('campaign-medium');
      if (!platformEl || !mediumEl) return;
      if (platformEl.value === 'google' || platformEl.value === 'youtube') {{
        mediumEl.value = 'cpc';
      }} else if (platformEl.value === 'email') {{
        mediumEl.value = 'email';
      }} else if (platformEl.value === 'whatsapp') {{
        mediumEl.value = 'message';
      }} else {{
        mediumEl.value = 'paid_social';
      }}
    }}

    function generateCampaignUrl() {{
      var baseEl = document.getElementById('campaign-url-base');
      var platformEl = document.getElementById('campaign-platform');
      var mediumEl = document.getElementById('campaign-medium');
      var campaignEl = document.getElementById('campaign-name');
      var contentEl = document.getElementById('campaign-content');
      var termEl = document.getElementById('campaign-term');
      var outputEl = document.getElementById('campaign-builder-output');
      var statusEl = document.getElementById('campaign-builder-status');
      if (!baseEl || !platformEl || !mediumEl || !campaignEl || !outputEl || !statusEl) return;

      var rawUrl = baseEl.value.trim();
      if (!rawUrl) {{
        statusEl.style.color = '#ff8a80';
        statusEl.innerText = 'Landing URL দিন।';
        return;
      }}
      if (!/^https?:\\/\\//i.test(rawUrl)) {{
        rawUrl = 'https://' + rawUrl;
      }}

      var source = slugifyUtm(platformEl.value);
      var medium = slugifyUtm(mediumEl.value);
      var campaign = slugifyUtm(campaignEl.value);
      var content = slugifyUtm(contentEl ? contentEl.value : '');
      var term = slugifyUtm(termEl ? termEl.value : '');
      if (!campaign) {{
        statusEl.style.color = '#ff8a80';
        statusEl.innerText = 'Campaign name দিন।';
        return;
      }}

      try {{
        var url = new URL(rawUrl);
        url.searchParams.set('utm_source', source || 'unknown');
        url.searchParams.set('utm_medium', medium || 'paid_social');
        url.searchParams.set('utm_campaign', campaign);
        if (content) url.searchParams.set('utm_content', content);
        if (term) url.searchParams.set('utm_term', term);
        outputEl.innerText = url.toString();
        statusEl.style.color = '#00e676';
        statusEl.innerText = 'Ready. এই link campaign/ad destination URL হিসেবে ব্যবহার করুন।';
      }} catch (e) {{
        statusEl.style.color = '#ff8a80';
        statusEl.innerText = 'Valid URL দিন, যেমন https://example.com/product/item';
      }}
    }}

    var ctx = document.getElementById('eventsChart').getContext('2d');
    new Chart(ctx, {{
      type: 'line',
      data: {{
        labels: {labels_json},
        datasets: [
          {{
            label: 'Success',
            data: {success_json},
            borderColor: '#00e676',
            backgroundColor: 'rgba(0, 230, 118, 0.1)',
            fill: true,
            tension: 0.4,
            borderWidth: 2,
            pointRadius: 4,
            pointBackgroundColor: '#00e676',
          }},
          {{
            label: 'Failed',
            data: {failed_json},
            borderColor: '#ff5252',
            backgroundColor: 'rgba(255, 82, 82, 0.1)',
            fill: true,
            tension: 0.4,
            borderWidth: 2,
            pointRadius: 4,
            pointBackgroundColor: '#ff5252',
          }}
        ]
      }},
      options: {{
        responsive: true,
        plugins: {{
          legend: {{
            labels: {{ color: '#94a3b8', font: {{ family: 'Outfit' }} }}
          }}
        }},
        scales: {{
          x: {{
            ticks: {{ color: '#64748b', font: {{ size: 11 }} }},
            grid: {{ color: 'rgba(255,255,255,0.05)' }}
          }},
          y: {{
            beginAtZero: true,
            ticks: {{ color: '#64748b', font: {{ size: 11 }} }},
            grid: {{ color: 'rgba(255,255,255,0.05)' }}
          }}
        }}
      }}
    }});
    async function cancelSelected() {{
      var cbs = document.querySelectorAll('.pending-cb:checked');
      if (cbs.length === 0) {{ showStatus('⚠️ কোনো অর্ডার সিলেক্ট করা হয়নি!', 'error'); return; }}
      if (!confirm(cbs.length + 'টি অর্ডার cancel করবেন? Facebook/TikTok/GA4-এ কিছু পাঠানো হবে না।')) return;

      var orderIds = Array.from(cbs).map(function(cb) {{ return cb.value; }});
      try {{
        var res = await fetch(BASE_API + '/events/cancel/bulk', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: JSON.stringify({{ order_ids: orderIds }})
        }});
        var data = await res.json();
        if (res.ok) {{
          showStatus('❌ ' + data.cancelled + 'টি cancel হয়েছে, ' + data.failed + 'টি ব্যর্থ।', 'success');
          orderIds.forEach(function(oid) {{
            var row = document.getElementById('row-' + oid);
            if (row) {{ row.style.opacity = '0.3'; setTimeout(function() {{ row.remove(); }}, 1200); }}
          }});
        }} else {{
          showStatus('❌ Error: ' + (data.detail || 'Unknown error'), 'error');
        }}
      }} catch(e) {{
        showStatus('❌ Network error: ' + e.message, 'error');
      }}
    }}
    </script>

<script>
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
        
        code = "<script>\\n  // Event: " + ev + "\\n  capi('track', '" + fbEvent + "'" + params + ");\\n</scr" + "ipt>";
        
        document.getElementById('generated_code_box').innerText = code;
        document.getElementById('code_result_area').style.display = 'block';
    }}
    </script>

<script>
    // ─── Pending Orders AJAX Functions ─────────────────────────────────
    var BASE_API = '{gateway_origin}/api/v1';

    function showStatus(msg, type) {{
      var el = document.getElementById('pending-status');
      if (!el) return;
      el.style.display = 'block';
      el.style.background = type === 'success' ? 'rgba(0,230,118,0.1)' : 'rgba(255,82,82,0.1)';
      el.style.border = type === 'success' ? '1px solid rgba(0,230,118,0.2)' : '1px solid rgba(255,82,82,0.2)';
      el.style.color = type === 'success' ? '#00e676' : '#ff5252';
      el.innerText = msg;
      setTimeout(function() {{ el.style.display = 'none'; }}, 5000);
    }}

    async function confirmOrder(orderId) {{
      if (!confirm('অর্ডার ' + orderId + ' কনফার্ম করবেন? Purchase event Facebook-এ পাঠানো হবে।')) return;
      try {{
        var res = await fetch(BASE_API + '/events/confirm', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: JSON.stringify({{ order_id: orderId }})
        }});
        var data = await res.json();
        if (res.ok) {{
          showStatus('✅ ' + orderId + ' কনফার্ম হয়েছে! Facebook-এ পাঠানো হয়েছে।', 'success');
          var row = document.getElementById('row-' + orderId);
          if (row) row.style.opacity = '0.3';
          setTimeout(function() {{ if (row) row.remove(); }}, 2000);
        }} else {{
          showStatus('❌ Error: ' + (data.detail || 'Unknown error'), 'error');
        }}
      }} catch(e) {{
        showStatus('❌ Network error: ' + e.message, 'error');
      }}
    }}

    async function cancelOrder(orderId) {{
      if (!confirm('অর্ডার ' + orderId + ' ক্যান্সেল করবেন? Facebook-এ কিছু পাঠানো হবে না।')) return;
      try {{
        var res = await fetch(BASE_API + '/events/cancel', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: JSON.stringify({{ order_id: orderId }})
        }});
        var data = await res.json();
        if (res.ok) {{
          showStatus('❌ ' + orderId + ' ক্যান্সেল হয়েছে।', 'success');
          var row = document.getElementById('row-' + orderId);
          if (row) row.style.opacity = '0.3';
          setTimeout(function() {{ if (row) row.remove(); }}, 2000);
        }} else {{
          showStatus('❌ Error: ' + (data.detail || 'Unknown error'), 'error');
        }}
      }} catch(e) {{
        showStatus('❌ Network error: ' + e.message, 'error');
      }}
    }}

    function selectAllPending() {{
      var cbs = document.querySelectorAll('.pending-cb');
      var allChecked = Array.from(cbs).every(function(cb) {{ return cb.checked; }});
      cbs.forEach(function(cb) {{ cb.checked = !allChecked; }});
    }}

    async function confirmSelected() {{
      var cbs = document.querySelectorAll('.pending-cb:checked');
      if (cbs.length === 0) {{ showStatus('⚠️ কোনো অর্ডার সিলেক্ট করা হয়নি!', 'error'); return; }}
      if (!confirm(cbs.length + 'টি অর্ডার কনফার্ম করবেন?')) return;

      var orderIds = Array.from(cbs).map(function(cb) {{ return cb.value; }});
      try {{
        var res = await fetch(BASE_API + '/events/confirm/bulk', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: JSON.stringify({{ order_ids: orderIds }})
        }});
        var data = await res.json();
        if (res.ok) {{
          showStatus('✅ ' + data.confirmed + 'টি কনফার্ম হয়েছে, ' + data.failed + 'টি ব্যর্থ।', 'success');
          orderIds.forEach(function(oid) {{
            var row = document.getElementById('row-' + oid);
            if (row) {{ row.style.opacity = '0.3'; setTimeout(function() {{ row.remove(); }}, 2000); }}
          }});
        }} else {{
          showStatus('❌ Error: ' + (data.detail || 'Unknown error'), 'error');
        }}
      }} catch(e) {{
        showStatus('❌ Network error: ' + e.message, 'error');
      }}
    }}
    </script>

<script>
    // ─── Analytics Charts ─────────────────────────────────────────────────
    function renderSignalDoctor(data) {{
      var panel = document.getElementById('signal-doctor-panel');
      if (!panel || !data) return;
      var readiness = data.platform_readiness || {{}};
      var issues = data.issues || [];
      var scoreColor = data.score >= 90 ? '#00e676' : data.score >= 75 ? '#42a5f5' : data.score >= 55 ? '#ffab00' : '#ff5252';
      var html = '<div style="display:grid;grid-template-columns:180px 1fr;gap:18px;align-items:start;">' +
        '<div style="background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:10px;padding:18px;text-align:center;">' +
          '<div style="font-size:42px;line-height:1;color:' + scoreColor + ';font-weight:800;">' + Number(data.score || 0) + '</div>' +
          '<div style="font-size:12px;color:#cbd5e1;margin-top:6px;">' + escapeHtml(data.grade || '') + '</div>' +
          '<div style="font-size:11px;color:#64748b;margin-top:6px;">' + Number(data.total_events || 0).toLocaleString() + ' events checked</div>' +
        '</div>' +
        '<div>' +
          '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px;">' +
            '<div style="padding:10px;border:1px solid rgba(59,130,246,0.18);border-radius:8px;background:rgba(59,130,246,0.05);"><div style="font-size:11px;color:#93c5fd;">Facebook Ready</div><div style="font-size:20px;color:#fff;font-weight:700;">' + Number(readiness.facebook || 0) + '%</div></div>' +
            '<div style="padding:10px;border:1px solid rgba(236,72,153,0.18);border-radius:8px;background:rgba(236,72,153,0.05);"><div style="font-size:11px;color:#f9a8d4;">TikTok Ready</div><div style="font-size:20px;color:#fff;font-weight:700;">' + Number(readiness.tiktok || 0) + '%</div></div>' +
            '<div style="padding:10px;border:1px solid rgba(34,197,94,0.18);border-radius:8px;background:rgba(34,197,94,0.05);"><div style="font-size:11px;color:#86efac;">GA4 Ready</div><div style="font-size:20px;color:#fff;font-weight:700;">' + Number(readiness.ga4 || 0) + '%</div></div>' +
          '</div>';
      html += issues.slice(0, 5).map(function(issue) {{
        var color = issue.severity === 'high' || issue.severity === 'critical' ? '#ff5252' : issue.severity === 'medium' ? '#ffab00' : issue.severity === 'ok' ? '#00e676' : '#94a3b8';
        return '<div style="padding:10px 12px;border-left:3px solid ' + color + ';background:rgba(255,255,255,0.025);border-radius:8px;margin-bottom:8px;">' +
          '<div style="display:flex;justify-content:space-between;gap:12px;"><strong style="color:#fff;">' + escapeHtml(issue.title || '') + '</strong><span style="color:' + color + ';font-size:12px;">' + escapeHtml(issue.metric || '') + '</span></div>' +
          '<div style="color:#94a3b8;font-size:12px;margin-top:4px;">' + escapeHtml(issue.impact || '') + '</div>' +
          '<div style="color:#cbd5e1;font-size:12px;margin-top:4px;">Fix: ' + escapeHtml(issue.fix || '') + '</div>' +
        '</div>';
      }}).join('');
      html += '</div></div>';
      panel.innerHTML = html;
    }}

    (async function loadAnalytics() {{
      try {{
        var doctorRes = await fetch(BASE_API + '/analytics/signal-doctor?days=7', {{
          credentials: 'include'
        }});
        if (doctorRes.ok) {{
          renderSignalDoctor(await doctorRes.json());
        }}

        // Fetch overview data
        var res = await fetch(BASE_API + '/analytics/overview?days=7', {{
          credentials: 'include'
        }});
        if (!res.ok) return;
        var data = await res.json();

        // Conversion Funnel
        var fc = document.getElementById('funnel-container');
        if (fc && data.funnel) {{
          var funnelColors = ['#7e57c2','#42a5f5','#66bb6a','#ffab00','#00e676'];
          var maxCount = Math.max(...data.funnel.map(function(f) {{ return f.count; }}), 1);
          var fhtml = '';
          data.funnel.forEach(function(step, i) {{
            var width = Math.max((Number(step.count || 0) / maxCount) * 100, 5);
            var dropText = i > 0 && step.drop_off > 0 ? '<span style="color:#ff5252;font-size:11px;margin-left:8px;">↓' + Number(step.drop_off).toFixed(1) + '%</span>' : '';
            fhtml += '<div style="margin-bottom:10px;">' +
              '<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">' +
                '<span style="color:#ccc">' + escapeHtml(step.step) + dropText + '</span>' +
                '<span style="color:#fff;font-weight:600">' + Number(step.count || 0).toLocaleString() + '</span>' +
              '</div>' +
              '<div style="background:rgba(255,255,255,0.05);border-radius:6px;height:8px;overflow:hidden;">' +
                '<div style="width:' + width + '%;height:100%;background:' + funnelColors[i % 5] + ';border-radius:6px;transition:width 0.8s ease;"></div>' +
              '</div></div>';
          }});
          fc.innerHTML = fhtml;
        }}

        // Event Breakdown — Doughnut Chart
        if (data.event_breakdown && data.event_breakdown.length > 0) {{
          var bdLabels = data.event_breakdown.map(function(e) {{ return e.event_name; }});
          var bdData = data.event_breakdown.map(function(e) {{ return e.count; }});
          var bdColors = ['#7e57c2','#42a5f5','#66bb6a','#ffab00','#ff5252','#00e676','#ff7043','#ab47bc','#26c6da','#8d6e63'];
          new Chart(document.getElementById('breakdownChart'), {{
            type: 'doughnut',
            data: {{
              labels: bdLabels,
              datasets: [{{
                data: bdData,
                backgroundColor: bdColors.slice(0, bdLabels.length),
                borderWidth: 0,
              }}]
            }},
            options: {{
              responsive: true,
              plugins: {{
                legend: {{ position: 'right', labels: {{ color: '#ccc', font: {{ size: 11 }} }} }}
              }}
            }}
          }});
        }}

        // Hourly Heatmap
        var hRes = await fetch(BASE_API + '/analytics/hourly?days=7', {{
          credentials: 'include'
        }});
        if (hRes.ok) {{
          var hData = await hRes.json();
          var hLabels = hData.data.map(function(h) {{ return h.hour + ':00'; }});
          var hCounts = hData.data.map(function(h) {{ return h.count; }});
          var maxH = Math.max(...hCounts, 1);
          var hColors = hCounts.map(function(c) {{
            var intensity = Math.min(c / maxH, 1);
            return 'rgba(126,87,194,' + (0.2 + intensity * 0.8) + ')';
          }});
          new Chart(document.getElementById('hourlyChart'), {{
            type: 'bar',
            data: {{
              labels: hLabels,
              datasets: [{{
                label: 'Events',
                data: hCounts,
                backgroundColor: hColors,
                borderRadius: 4,
              }}]
            }},
            options: {{
              responsive: true,
              plugins: {{ legend: {{ display: false }} }},
              scales: {{
                x: {{ grid: {{ display: false }}, ticks: {{ color: '#666', font: {{ size: 10 }} }} }},
                y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#666' }} }}
              }}
            }}
          }});
        }}

        var cRes = await fetch(BASE_API + '/analytics/campaigns?days=30', {{
          credentials: 'include'
        }});
        var cBody = document.getElementById('campaign-performance-body');
        if (cBody && cRes.ok) {{
          var cData = await cRes.json();
          if (!cData.campaigns || cData.campaigns.length === 0) {{
            cBody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:20px">No UTM campaign data yet</td></tr>';
          }} else {{
            cBody.innerHTML = cData.campaigns.map(function(row) {{
              return '<tr>' +
                '<td>' + escapeHtml(row.source || 'direct') + '</td>' +
                '<td>' + escapeHtml(row.campaign || '(not set)') + '</td>' +
                '<td>' + Number(row.view_content || 0).toLocaleString() + '</td>' +
                '<td>' + Number(row.add_to_cart || 0).toLocaleString() + '</td>' +
                '<td>' + Number(row.initiate_checkout || 0).toLocaleString() + '</td>' +
                '<td style="color:var(--accent);font-weight:600">' + Number(row.purchase || 0).toLocaleString() + '</td>' +
                '<td style="color:var(--accent);font-weight:600">৳' + Number(row.revenue || 0).toLocaleString() + '</td>' +
              '</tr>';
            }}).join('');
          }}
        }}
      }} catch(e) {{
        console.log('Analytics load error:', e);
      }}
    }})();
    </script>

<script>
    // ─── Debug & Testing Functions ────────────────────────────────────────
    async function sendTestEvent() {{
      var evName = document.getElementById('test-event-name').value;
      var el = document.getElementById('test-result');
      el.innerHTML = '<span style="color:#ffab00">⏳ পাঠাচ্ছে...</span>';
      try {{
        var res = await fetch(BASE_API + '/debug/test-event', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: JSON.stringify({{ event_name: evName }})
        }});
        var data = await res.json();
        if (res.ok) {{
          el.innerHTML = '<span style="color:#00e676">✅ ' + escapeHtml(evName) + ' event পাঠানো হয়েছে!</span><br><span style="color:#666">ID: ' + escapeHtml(data.event_id) + '</span>';
        }} else {{
          el.innerHTML = '<span style="color:#ff5252">❌ ' + escapeHtml(data.detail || 'Error') + '</span>';
        }}
      }} catch(e) {{
        el.innerHTML = '<span style="color:#ff5252">❌ Network error</span>';
      }}
    }}

    async function validatePayload() {{
      var el = document.getElementById('validate-result');
      var raw = document.getElementById('validate-payload').value;
      if (!raw.trim()) {{ el.innerHTML = '<span style="color:#ff5252">Payload দিন!</span>'; return; }}
      try {{
        var payload = JSON.parse(raw);
        var res = await fetch(BASE_API + '/debug/validate', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: raw
        }});
        var data = await res.json();
        var emqColor = data.emq_estimate >= 7 ? '#00e676' : data.emq_estimate >= 4 ? '#ffab00' : '#ff5252';
        var html = '<div style="margin-bottom:8px;"><span style="font-size:16px;color:' + emqColor + ';font-weight:bold">EMQ: ' + data.emq_estimate + '/10</span> ';
        html += data.is_valid ? '<span style="color:#00e676">✅ Valid</span>' : '<span style="color:#ff5252">❌ Invalid</span>';
        html += '</div>';
        data.issues.forEach(function(i) {{
          var c = i.status === 'ok' ? '#00e676' : i.status === 'warning' ? '#ffab00' : '#ff5252';
          html += '<div style="color:' + c + ';margin:2px 0;">' + escapeHtml(i.message) + '</div>';
        }});
        el.innerHTML = html;
      }} catch(e) {{
        el.innerHTML = '<span style="color:#ff5252">❌ Invalid JSON: ' + escapeHtml(e.message) + '</span>';
      }}
    }}

    async function refreshLiveEvents() {{
      var el = document.getElementById('live-events');
      el.innerHTML = '<span style="color:#ffab00">Loading...</span>';
      try {{
        var res = await fetch(BASE_API + '/debug/recent?limit=20&minutes=60', {{
          credentials: 'include'
        }});
        if (!res.ok) {{ el.innerHTML = '<span style="color:#ff5252">Error loading events</span>'; return; }}
        var data = await res.json();
        if (data.events.length === 0) {{
          el.innerHTML = '<span style="color:#555">No events in the last hour</span>';
          return;
        }}
        var html = '';
        data.events.forEach(function(ev) {{
          var statusColor = ev.status === 'success' ? '#00e676' : '#ff5252';
          var ageStr = ev.age_seconds < 60 ? Math.round(ev.age_seconds) + 's ago' : Math.round(ev.age_seconds / 60) + 'm ago';
          html += '<div style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.03);display:flex;gap:12px;align-items:center;">';
          html += '<span style="color:#555;min-width:55px;">' + ageStr + '</span>';
          html += '<span style="color:' + statusColor + ';min-width:12px;">' + (ev.status === 'success' ? '●' : '○') + '</span>';
          html += '<span style="color:#ccc;min-width:120px;font-weight:600;">' + escapeHtml(ev.event_name) + '</span>';
          html += '<span style="color:#555;font-size:10px;">' + escapeHtml(ev.event_id || '') + '</span>';
          html += '</div>';
        }});
        el.innerHTML = html;
      }} catch(e) {{
        el.innerHTML = '<span style="color:#ff5252">Error: ' + escapeHtml(e.message) + '</span>';
      }}
    }}
    // Auto-load live events
    refreshLiveEvents();
    </script>
    """

    return HTMLResponse(client_html(f"Dashboard — {client.name}", body))


@router.post("/client/settings/update", include_in_schema=False)
@limiter.limit("10/minute")
async def client_settings_update(
    request: Request,
    pixel_id: str = Form(""),
    access_token: str = Form(""),
    test_event_code: str = Form(""),
    tiktok_pixel_id: str = Form(""),
    tiktok_access_token: str = Form(""),
    tiktok_test_event_code: str = Form(""),
    ga4_measurement_id: str = Form(""),
    ga4_api_secret: str = Form(""),
    enable_facebook: str = Form(None),
    enable_tiktok: str = Form(None),
    enable_ga4: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    client = await get_client_from_portal_session(request, db)
    if not client or not client.is_active:
        return RedirectResponse(url="/client", status_code=303)

    # ─── Validate Pixel ID if provided ─────────────────────────────────────
    if pixel_id and pixel_id.strip():
        if not pixel_id.strip().isdigit():
            from urllib.parse import urlencode
            q = urlencode({"settings_msg": "Pixel ID শুধু সংখ্যা হতে হবে।", "settings_type": "error"})
            return RedirectResponse(url=f"/client/dashboard?{q}#tab-settings", status_code=303)
        client.pixel_id = pixel_id.strip()

    # ─── Update non-sensitive fields always ─────────────────────────────────
    client.test_event_code = test_event_code.strip() if test_event_code and test_event_code.strip() else None
    client.enable_facebook = (enable_facebook == "1")
    client.enable_tiktok = (enable_tiktok == "1")
    client.enable_ga4 = (enable_ga4 == "1")
    client.tiktok_pixel_id = tiktok_pixel_id.strip() if tiktok_pixel_id and tiktok_pixel_id.strip() else None
    client.tiktok_test_event_code = tiktok_test_event_code.strip() if tiktok_test_event_code and tiktok_test_event_code.strip() else None
    client.ga4_measurement_id = ga4_measurement_id.strip() if ga4_measurement_id and ga4_measurement_id.strip() else None

    # ─── Only update encrypted tokens if new value provided ──────────────────
    if access_token and access_token.strip():
        client.access_token = encrypt_token(access_token.strip())
    if tiktok_access_token and tiktok_access_token.strip():
        client.tiktok_access_token = encrypt_token(tiktok_access_token.strip())
    if ga4_api_secret and ga4_api_secret.strip():
        client.ga4_api_secret = encrypt_token(ga4_api_secret.strip())

    await db.commit()

    # Clear cache so changes take effect immediately
    from app.dependencies import clear_client_cache
    clear_client_cache(client.api_key)

    from urllib.parse import urlencode
    q = urlencode({"settings_msg": "✅ Settings সফলভাবে আপডেট হয়েছে!", "settings_type": "success"})
    return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
