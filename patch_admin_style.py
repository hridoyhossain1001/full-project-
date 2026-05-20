#!/usr/bin/env python3
"""Patch admin.py STYLE block with buykori.app orange theme."""

NEW_STYLE = '''STYLE = """
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
"""'''

with open('app/routers/admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the STYLE variable
style_start = content.find('STYLE = """')
if style_start == -1:
    print("ERROR: Could not find STYLE = \"\"\"")
    exit(1)

# Find the closing triple quote after STYLE = """
search_from = style_start + len('STYLE = """')
style_end = content.find('"""', search_from) + 3
print(f"Found STYLE from position {style_start} to {style_end}")
print(f"Old STYLE snippet: {repr(content[style_start:style_start+30])}")
print(f"Old end snippet: {repr(content[style_end-30:style_end])}")

new_content = content[:style_start] + NEW_STYLE + content[style_end:]
with open('app/routers/admin.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("SUCCESS: STYLE block replaced!")
print(f"Old file size: {len(content)} chars")
print(f"New file size: {len(new_content)} chars")
