from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
import html
import datetime
from typing import Optional

from app.database import get_db
from app.models.client import Client
from app.models.event_log import EventLog
from app.routers.admin import STYLE, base_html
from app.security import encrypt_token, decrypt_token

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
async def client_login(response: Response, api_key: str = Form(...), db: AsyncSession = Depends(get_db)):
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

    log_rows_html = ""
    for log in recent_logs:
        time_str = log.created_at.strftime("%b %d, %H:%M:%S") if log.created_at else "—"
        safe_event_name = html.escape(log.event_name or "unknown")
        safe_event_id = html.escape(log.event_id or "—")
        status_badge = (
            '<span style="color:#00e676;font-weight:600">✅ Success</span>'
            if log.status == "success"
            else '<span style="color:#ff5252;font-weight:600">❌ Failed</span>'
        )
        log_rows_html += f"""
        <tr>
          <td style="color:#888;font-size:12px">{time_str}</td>
          <td><strong>{safe_event_name}</strong></td>
          <td style="font-family:monospace;font-size:11px;color:#666">{safe_event_id}</td>
          <td>{status_badge}</td>
        </tr>"""

    if not recent_logs:
        log_rows_html = '<tr><td colspan="4" style="text-align:center;color:#555;padding:30px">এখনো কোনো ইভেন্ট লগ নেই</td></tr>'

    # Base URL detection
    base_url = str(request.base_url).rstrip("/")
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost")
    gateway_origin = f"{scheme}://{host}"
    endpoint = f"{base_url}/api/v1/events"
    tracker_url = f"{gateway_origin}/t.js?key={client.api_key}"
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
        <div class="instr-box" id="wp_pv_easy">&lt;script&gt;
  (function(w,d,s,l,i){{w[l]=w[l]||function(){{(w[l].q=w[l].q||[]).push(arguments)}};
  var f=d.getElementsByTagName(s)[0],j=d.createElement(s);j.async=true;
  j.src='{safe_tracker_url}';f.parentNode.insertBefore(j,f);
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
    """

    body = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <div>
            <h1 class="page-title">👋 Welcome, {safe_client_name}</h1>
            <p class="page-sub">আপনার CAPI Dashboard এবং Setup Instructions</p>
        </div>
        <a href="/client/logout" class="btn-sm btn-danger" style="text-decoration:none;">Logout</a>
    </div>

    <!-- STATS -->
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

    <!-- 7-DAY CHART -->
    <div class="card" style="margin-bottom:24px;">
      <div class="card-title"><span class="icon">📈</span> গত ৭ দিনের ইভেন্ট</div>
      <canvas id="eventsChart" height="120"></canvas>
    </div>

    <!-- RECENT EVENT LOGS -->
    <div class="card" style="margin-bottom:24px;">
      <div class="card-title"><span class="icon">📋</span> সর্বশেষ ইভেন্ট লগ (সর্বোচ্চ ৫০টি)</div>
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
            {log_rows_html}
          </tbody>
        </table>
      </div>
    </div>
    
    <div style="margin-top:40px;">
        <h3 style="color:#fff; margin-bottom:16px; font-weight:600;">📋 Setup Instructions</h3>
        {instructions_html}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
    <script>
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
    </script>

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
    
    return HTMLResponse(base_html(f"Dashboard — {client.name}", body))
