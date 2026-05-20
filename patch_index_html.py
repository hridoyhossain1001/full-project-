import os
import re

file_path = 'admin-portal/index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update CSS
css_additions = """
    /* Modals & Tabs */
    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 99; display: none; align-items: center; justify-content: center; padding: 20px; }
    .modal { background: var(--bg-card); width: 100%; max-width: 720px; border-radius: var(--radius); border: 1px solid var(--border); box-shadow: 0 24px 48px rgba(0,0,0,0.4); max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; }
    .modal-header { padding: 20px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
    .modal-title { font-size: 18px; font-weight: 700; color: white; }
    .modal-close { background: none; border: none; color: var(--text-muted); font-size: 24px; cursor: pointer; }
    .modal-close:hover { color: white; }
    .modal-body { padding: 24px; overflow-y: auto; flex: 1; }
    
    .tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 24px; border-bottom: 2px solid rgba(255,255,255,0.05); }
    .tab-btn { padding: 10px 16px; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer; margin-bottom: -2px; transition: all 0.15s; }
    .tab-btn:hover { color: #E2E8F0; }
    .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    
    .api-key-cell { display: flex; align-items: center; gap: 8px; background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; font-family: monospace; font-size: 13px; color: #94A3B8; margin-bottom: 16px; }
    .api-key-cell span { flex: 1; word-break: break-all; }
    .copy-icon { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; padding: 0; }
    .copy-icon:hover { color: var(--primary); }
    
    .instr-box { background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 16px; font-family: monospace; font-size: 13px; color: #93c5fd; white-space: pre-wrap; word-break: break-all; margin: 0 0 16px 0; overflow-x: auto; }
    
    .btn-sm { padding: 4px 10px; font-size: 12px; border-radius: 4px; }
"""

# Insert CSS before </style>
content = content.replace("</style>", css_additions + "\n  </style>")

# 2. HTML Additions
html_additions = """
  <!-- Client Management Modal -->
  <div id="modalOverlay" class="modal-overlay" onclick="if(event.target===this) closeClientModal()">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-title" id="modalTitle">Manage Client</div>
        <button class="modal-close" onclick="closeClientModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="tabs">
          <button class="tab-btn active" onclick="switchModalTab('edit')">Settings</button>
          <button class="tab-btn" onclick="switchModalTab('keys')">API Keys</button>
          <button class="tab-btn" onclick="switchModalTab('instructions')">Instructions</button>
          <button class="tab-btn" onclick="switchModalTab('danger')">Danger Zone</button>
        </div>
        
        <div id="tab-edit" class="tab-content active form-card" style="padding:0">
          <div class="form-grid">
            <div class="field"><label>Name</label><input id="editName"></div>
            <div class="field"><label>Domain</label><input id="editDomain"></div>
            <div class="field"><label>Monthly Limit</label><input type="number" id="editLimit" placeholder="Optional"></div>
            <div class="field" style="display:flex;align-items:center;gap:12px;padding-top:20px;">
              <input type="checkbox" id="editActive" style="width:16px;height:16px">
              <label style="margin:0">Active Status</label>
            </div>
          </div>
          <h3 style="margin:24px 0 12px;font-size:14px;color:white">Integrations</h3>
          <div class="form-grid">
            <div class="field" style="display:flex;align-items:center;gap:12px;">
              <input type="checkbox" id="editFb" style="width:16px;height:16px">
              <label style="margin:0">Meta CAPI</label>
            </div>
            <div class="field" style="display:flex;align-items:center;gap:12px;">
              <input type="checkbox" id="editTiktok" style="width:16px;height:16px">
              <label style="margin:0">TikTok Events</label>
            </div>
            <div class="field" style="display:flex;align-items:center;gap:12px;">
              <input type="checkbox" id="editGa4" style="width:16px;height:16px">
              <label style="margin:0">GA4 Measurement</label>
            </div>
            <div class="field" style="display:flex;align-items:center;gap:12px;">
              <input type="checkbox" id="editDeferred" style="width:16px;height:16px">
              <label style="margin:0">Deferred Purchase</label>
            </div>
          </div>
          <div style="margin-top:24px;display:flex;gap:12px">
            <button class="btn btn-primary" onclick="saveClientEdit()">Save Changes</button>
            <span id="editMsg" class="notice" style="margin-top:8px"></span>
          </div>
        </div>
        
        <div id="tab-keys" class="tab-content">
          <p style="color:var(--text-muted);margin-bottom:16px">Manage authentication keys for this client. Rotating keys will immediately invalidate existing connections.</p>
          
          <label style="color:white;font-weight:700;font-size:13px;display:block;margin-bottom:8px">API Key (Data Ingestion)</label>
          <div class="api-key-cell">
            <span id="keyApi" data-hidden="1">••••••••••••••••</span>
            <button class="copy-icon" onclick="revealSecret('keyApi')" title="Reveal">👁️</button>
            <button class="copy-icon" onclick="copyText('keyApi')" title="Copy">📋</button>
          </div>
          <button class="btn btn-outline btn-sm" style="margin-bottom:24px" onclick="rotateKey('api_key')">Rotate API Key</button>
          
          <label style="color:white;font-weight:700;font-size:13px;display:block;margin-bottom:8px">Portal Key (Dashboard Access)</label>
          <div class="api-key-cell">
            <span id="keyPortal" data-hidden="1">••••••••••••••••</span>
            <button class="copy-icon" onclick="revealSecret('keyPortal')" title="Reveal">👁️</button>
            <button class="copy-icon" onclick="copyText('keyPortal')" title="Copy">📋</button>
          </div>
          <button class="btn btn-outline btn-sm" style="margin-bottom:24px" onclick="rotateKey('portal_key')">Rotate Portal Key</button>
          
          <label style="color:white;font-weight:700;font-size:13px;display:block;margin-bottom:8px">Access Token (Meta)</label>
          <div class="api-key-cell">
            <span id="keyToken" data-hidden="1">••••••••••••••••</span>
            <button class="copy-icon" onclick="revealSecret('keyToken')" title="Reveal">👁️</button>
            <button class="copy-icon" onclick="copyText('keyToken')" title="Copy">📋</button>
          </div>
        </div>
        
        <div id="tab-instructions" class="tab-content">
          <p style="color:var(--text-muted);margin-bottom:16px">Share these endpoints and snippets with the client for integration.</p>
          
          <label style="color:white;font-weight:700;font-size:13px;display:block;margin-bottom:8px">API Endpoint</label>
          <div class="api-key-cell">
            <span id="instrEndpoint">https://api.buykori.app/api/v1/track</span>
            <button class="copy-icon" onclick="copyText('instrEndpoint')" title="Copy">📋</button>
          </div>
          
          <label style="color:white;font-weight:700;font-size:13px;display:block;margin-bottom:8px">cURL Example</label>
          <div class="instr-box" id="instrCurl"></div>
          <button class="btn btn-outline btn-sm" onclick="copyText('instrCurl')">Copy Example</button>
          
          <div style="margin-top:24px">
            <label style="color:white;font-weight:700;font-size:13px;display:block;margin-bottom:8px">Client Portal Link</label>
            <div class="api-key-cell">
              <span id="instrPortal">https://buykori.app/portal</span>
              <button class="copy-icon" onclick="copyText('instrPortal')" title="Copy">📋</button>
            </div>
            <p style="font-size:11px;color:var(--text-muted)">The client will need their Portal Key to login.</p>
          </div>
        </div>
        
        <div id="tab-danger" class="tab-content">
          <div style="padding:20px;border:1px solid rgba(239,68,68,0.3);border-radius:8px;background:rgba(239,68,68,0.05)">
            <h3 style="color:#F87171;margin-bottom:8px;font-size:15px">Delete Client</h3>
            <p style="color:var(--text-muted);margin-bottom:16px;font-size:13px">Once you delete a client, there is no going back. All events, logs, and authentication keys will be permanently destroyed.</p>
            <button class="btn btn-danger" onclick="deleteClient()">I understand, delete this client</button>
          </div>
        </div>
        
      </div>
    </div>
  </div>
"""

content = content.replace("</body>", html_additions + "\n</body>")

# 3. JS Additions
js_additions = """
    // Modal Functions
    let currentClientId = null;

    function showToast(msg) {
      let t = document.getElementById('bk-toast');
      if (!t) {
        t = document.createElement('div');
        t.id = 'bk-toast';
        t.style.cssText = 'position:fixed;bottom:24px;right:24px;background:#ff8b45;color:#111;font-weight:700;font-size:13px;padding:10px 20px;border-radius:8px;z-index:9999;box-shadow:0 8px 24px rgba(255,139,69,0.4);transition:opacity .3s;pointer-events:none;';
        document.body.appendChild(t);
      }
      t.textContent = msg;
      t.style.opacity = '1';
      clearTimeout(t._tid);
      t._tid = setTimeout(() => { t.style.opacity = '0'; }, 1800);
    }

    function copyText(id) {
      const el = document.getElementById(id);
      const val = el.dataset.secret || el.innerText || el.value || '';
      navigator.clipboard.writeText(val.trim()).then(() => showToast('Copied!'));
    }

    function revealSecret(id) {
      const el = document.getElementById(id);
      if (!el) return;
      if (el.dataset.hidden === '1') {
        el.innerText = el.dataset.secret || '';
        el.dataset.hidden = '0';
      } else {
        el.innerText = '••••••••••••••••';
        el.dataset.hidden = '1';
      }
    }

    function switchModalTab(tab) {
      document.querySelectorAll('.modal-body .tab-btn').forEach(b => b.classList.toggle('active', b.innerText.toLowerCase().includes(tab) || b.getAttribute('onclick').includes(tab)));
      document.querySelectorAll('.modal-body .tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-' + tab));
    }

    function closeClientModal() {
      document.getElementById('modalOverlay').style.display = 'none';
      currentClientId = null;
    }

    async function openClientModal(id) {
      currentClientId = id;
      document.getElementById('modalOverlay').style.display = 'flex';
      switchModalTab('edit');
      $("editMsg").textContent = "Loading...";
      
      try {
        const res = await api(`/admin/api/clients/${id}`);
        const c = res.client;
        
        // Populate Edit
        $("editName").value = c.name || "";
        $("editDomain").value = c.domain || "";
        $("editLimit").value = c.monthly_limit || "";
        $("editActive").checked = !!c.is_active;
        $("editFb").checked = !!c.enable_facebook;
        $("editTiktok").checked = !!c.enable_tiktok;
        $("editGa4").checked = !!c.enable_ga4;
        $("editDeferred").checked = !!c.deferred_purchase;
        $("editMsg").textContent = "";
        
        // Populate Keys
        $("keyApi").dataset.secret = c.api_key || "";
        $("keyApi").innerText = "••••••••••••••••";
        $("keyApi").dataset.hidden = "1";
        
        $("keyPortal").dataset.secret = c.portal_key || "";
        $("keyPortal").innerText = "••••••••••••••••";
        $("keyPortal").dataset.hidden = "1";
        
        $("keyToken").dataset.secret = c.access_token || "";
        $("keyToken").innerText = "••••••••••••••••";
        $("keyToken").dataset.hidden = "1";
        
        // Populate Instructions
        const code = `curl -X POST https://api.buykori.app/api/v1/track \\
  -H "Authorization: Bearer ${c.api_key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "event_name": "Purchase",
    "event_time": ` + Math.floor(Date.now()/1000) + `,
    "action_source": "website",
    "user_data": {
      "em": ["7b17fb0bd173f625b58636fb796407c22b3d16fc78302d79f0fd30c2fc2fc068"],
      "ph": ["254aa248acb47dd654ca3ea53f48c2c26d641d23d7e2e93a1ec56258df7674c4"],
      "client_ip_address": "192.168.1.1",
      "client_user_agent": "Mozilla/5.0..."
    },
    "custom_data": {
      "currency": "BDT",
      "value": 1500.00
    }
  }'`;
        $("instrCurl").innerText = code;
        
      } catch (e) {
        $("editMsg").textContent = "Failed to load client data.";
        $("editMsg").style.color = "var(--danger)";
      }
    }

    async function saveClientEdit() {
      if (!currentClientId) return;
      $("editMsg").textContent = "Saving...";
      $("editMsg").style.color = "var(--success)";
      
      const payload = {
        name: $("editName").value,
        domain: $("editDomain").value,
        monthly_limit: parseInt($("editLimit").value) || null,
        is_active: $("editActive").checked,
        enable_facebook: $("editFb").checked,
        enable_tiktok: $("editTiktok").checked,
        enable_ga4: $("editGa4").checked,
        deferred_purchase: $("editDeferred").checked
      };
      
      try {
        await api(`/admin/api/clients/${currentClientId}`, {
          method: "PATCH",
          body: JSON.stringify(payload)
        });
        $("editMsg").textContent = "Saved successfully!";
        loadAll();
      } catch (e) {
        $("editMsg").textContent = "Failed to save.";
        $("editMsg").style.color = "var(--danger)";
      }
    }

    async function rotateKey(keyType) {
      if (!currentClientId || !confirm(`Are you sure you want to rotate the ${keyType}? Old integrations will break immediately.`)) return;
      try {
        const res = await api(`/admin/api/clients/${currentClientId}/keys/rotate`, {
          method: "POST",
          body: JSON.stringify({ key_type: keyType })
        });
        
        let elId = keyType === 'api_key' ? 'keyApi' : 'keyPortal';
        $(elId).dataset.secret = res.new_value;
        $(elId).innerText = "••••••••••••••••";
        $(elId).dataset.hidden = "1";
        showToast(keyType + " rotated!");
        loadAll();
      } catch (e) {
        alert("Failed to rotate key");
      }
    }

    async function deleteClient() {
      if (!currentClientId) return;
      const name = $("editName").value;
      if (!confirm(`WARNING: Are you absolutely sure you want to delete "${name}"? This action cannot be undone.`)) return;
      
      try {
        await api(`/admin/api/clients/${currentClientId}`, { method: "DELETE" });
        closeClientModal();
        showToast("Client deleted");
        loadAll();
      } catch (e) {
        alert("Failed to delete client");
      }
    }
"""

content = content.replace("</script>", js_additions + "\n  </script>")

# 4. Update row action to include 'Manage'
old_action = """<td><button class="btn btn-danger" onclick="toggleClient(${client.id}, ${!client.is_active})">${client.is_active ? "Deactivate" : "Activate"}</button></td>"""
new_action = """<td>
  <div style="display:flex;gap:8px">
    <button class="btn btn-outline btn-sm" onclick="openClientModal(${client.id})">Manage</button>
    <button class="btn btn-sm ${client.is_active ? 'btn-outline' : 'btn-primary'}" onclick="toggleClient(${client.id}, ${!client.is_active})">${client.is_active ? "Deactivate" : "Activate"}</button>
  </div>
</td>"""

content = content.replace(old_action, new_action)

with open('admin-portal/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
    
print("Successfully patched index.html with Modals and Logic")
