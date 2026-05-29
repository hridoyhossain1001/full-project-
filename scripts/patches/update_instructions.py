"""Replace client_instructions body in admin.py with final version."""
import re

filepath = r"app\routers\admin.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Find the body = f""" ... """ block inside client_instructions
# We replace from '    body = f"""' to the closing '    """' before return HTMLResponse
old_start = '    body = f"""\n    <h1 class="page-title">\U0001f4cb Client Instructions</h1>'
old_end = '    """\n    return HTMLResponse(base_html(f"Instructions — {client.name}", body))'

start_idx = content.find(old_start)
end_idx = content.find(old_end)

if start_idx == -1 or end_idx == -1:
    print("ERROR: Could not find markers!")
    print(f"start found: {start_idx != -1}")
    print(f"end found: {end_idx != -1}")
    # Debug
    for i, line in enumerate(content.split('\n')[544:550], start=545):
        print(f"  L{i}: {repr(line[:80])}")
    exit(1)

end_idx += len(old_end)

NEW_BODY = r'''    body = f"""
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
        💡 <strong>Custom Domain:</strong> আপনার নিজের ডোমেইন থাকলে (যেমন: <code>capi.yourdomain.com</code>) সেটি ব্যবহার করুন।
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="openTab(event, 'tab-gtm')">⚙️ GTM Server</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-wp')">📝 WordPress</button>
      <button class="tab-btn" onclick="openTab(event, 'tab-custom')">💻 Custom Backend</button>
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

    <!-- WORDPRESS TAB -->
    <div id="tab-wp" class="tab-content card" style="margin-bottom:20px">
      <div class="card-title"><span class="icon">📝</span> WordPress / WooCommerce Setup</div>
      <div style="color:#aaa;font-size:14px;line-height:1.8">
        <p><strong style="color:#fff">Step 1:</strong> <code>WPCode</code> প্লাগিন ইনস্টল করুন অথবা থিমের <code>functions.php</code>-এ যান।</p><br>
        <p><strong style="color:#fff">Step 2 — PageView (সব পেজে):</strong></p>
        <button class="copy-btn" onclick="copyText('wp_pv')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_pv">&lt;?php
add_action('wp_footer', 'send_capi_pageview');
function send_capi_pageview() {{
    $api_url = '{safe_endpoint}';
    $api_key = 'YOUR_API_KEY_HERE';

    $ip  = $_SERVER['REMOTE_ADDR'] ?? '';
    $ua  = $_SERVER['HTTP_USER_AGENT'] ?? '';
    $url = (isset($_SERVER['HTTPS']) ? 'https' : 'http') . "://$_SERVER[HTTP_HOST]$_SERVER[REQUEST_URI]";
    $fbp = $_COOKIE['_fbp'] ?? '';
    $fbc = $_COOKIE['_fbc'] ?? '';

    $body = json_encode(['data' =&gt; [[
        'event_name'       =&gt; 'PageView',
        'event_time'       =&gt; time(),
        'event_id'         =&gt; uniqid('pv_', true),
        'action_source'    =&gt; 'website',
        'event_source_url' =&gt; $url,
        'user_data'        =&gt; [
            'client_ip_address' =&gt; $ip,
            'client_user_agent' =&gt; $ua,
            'fbp' =&gt; $fbp, 'fbc' =&gt; $fbc,
        ],
    ]]]);

    wp_remote_post($api_url, [
        'method'   =&gt; 'POST',
        'timeout'  =&gt; 15,
        'blocking' =&gt; false,
        'headers'  =&gt; ['Content-Type' =&gt; 'application/json', 'X-API-Key' =&gt; $api_key],
        'body'     =&gt; $body,
    ]);
}}
?&gt;</div>
        <br>
        <p><strong style="color:#fff">Step 3 — WooCommerce Purchase (Thank You পেজে):</strong></p>
        <button class="copy-btn" onclick="copyText('wp_pur')" style="margin-bottom:4px">Copy</button>
        <div class="instr-box" id="wp_pur">&lt;?php
add_action('woocommerce_thankyou', 'send_capi_purchase');
function send_capi_purchase($order_id) {{
    $api_url = '{safe_endpoint}';
    $api_key = 'YOUR_API_KEY_HERE';
    $order   = wc_get_order($order_id);

    $body = json_encode(['data' =&gt; [[
        'event_name'       =&gt; 'Purchase',
        'event_time'       =&gt; time(),
        'event_id'         =&gt; 'order-' . $order_id,
        'action_source'    =&gt; 'website',
        'event_source_url' =&gt; wc_get_checkout_url(),
        'user_data' =&gt; [
            'client_ip_address' =&gt; $_SERVER['REMOTE_ADDR'] ?? '',
            'client_user_agent' =&gt; $_SERVER['HTTP_USER_AGENT'] ?? '',
            'fbp' =&gt; $_COOKIE['_fbp'] ?? '',
            'fbc' =&gt; $_COOKIE['_fbc'] ?? '',
        ],
        'custom_data' =&gt; [
            'value'    =&gt; (float) $order-&gt;get_total(),
            'currency' =&gt; get_woocommerce_currency(),
        ],
    ]]]);

    wp_remote_post($api_url, [
        'method'   =&gt; 'POST',
        'timeout'  =&gt; 15,
        'blocking' =&gt; false,
        'headers'  =&gt; ['Content-Type' =&gt; 'application/json', 'X-API-Key' =&gt; $api_key],
        'body'     =&gt; $body,
    ]);
}}
?&gt;</div>
        <div style="margin-top:12px;padding:10px 14px;background:rgba(255,171,0,0.06);border:1px solid rgba(255,171,0,0.2);border-radius:8px;font-size:12px;color:#ffab00;">
          ⚠️ API Key হার্ডকোড করবেন না। <code>wp-config.php</code>-এ <code>define('CAPI_KEY','আপনার_কী');</code> করে ব্যবহার করুন।
        </div>
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
    </script>
    """
    return HTMLResponse(base_html(f"Instructions — {client.name}", body))'''

content = content[:start_idx] + NEW_BODY + content[end_idx:]

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Successfully updated client_instructions!")
print(f"  Replaced {end_idx - start_idx} chars with {len(NEW_BODY)} chars")
