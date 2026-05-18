"""
Tracker SDK Generator — ডায়নামিক JavaScript ট্র্যাকার কোড জেনারেট করে।
প্রতি ক্লায়েন্টের API Key embed করে কাস্টমাইজড JS রিটার্ন করে।
"""


def generate_tracker_js(api_key: str, gateway_origin: str) -> str:
    """
    API Key ও Gateway URL embed করে মিনিফাইড-স্টাইল JavaScript কোড রিটার্ন করে।

    Features:
    - Auto PageView on load
    - _fbc / _fbp cookie capture
    - SHA-256 hashing (browser-native SubtleCrypto)
    - Beacon API with fetch fallback
    - Unique event_id generation
    - SPA (History API) support
    - capi('track', ...) and capi('setUser', ...) global API
    """
    return f"""(function(){{
"use strict";

/* ═══════════════════════════════════════════════════════════════════
   CAPI Gateway Tracker v1.0
   Auto-tracks PageView, captures cookies, hashes PII.
   ═══════════════════════════════════════════════════════════════════ */

var K="{api_key}";
var E="{gateway_origin}/c";
var U={{}};  // user identity store
var Q=[];   // event queue (before DOM ready)
var R=false; // ready flag
persistTtclid();

/* ─── Helpers ──────────────────────────────────────────────────── */

// UUID-like event ID generator
function uid(){{
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){{
    var r=Math.random()*16|0;
    return(c==='x'?r:(r&0x3|0x8)).toString(16);
  }});
}}

// Cookie reader
function gc(n){{
  var m=document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'));
  return m?decodeURIComponent(m[1]):null;
}}

function qp(n){{
  try{{return new URLSearchParams(location.search).get(n)||'';}}
  catch(e){{return '';}}
}}

function persistTtclid(){{
  var id=qp('ttclid');
  if(id)document.cookie='_ttclid='+encodeURIComponent(id)+'; path=/; max-age='+(90*24*60*60)+'; SameSite=Lax';
}}

// SHA-256 hash (returns promise)
function sha(s){{
  if(!s)return Promise.resolve(null);
  s=s.trim().toLowerCase();
  if(/^[a-f0-9]{{64}}$/.test(s))return Promise.resolve(s); // already hashed
  var enc=new TextEncoder().encode(s);
  return crypto.subtle.digest('SHA-256',enc).then(function(buf){{
    return Array.from(new Uint8Array(buf)).map(function(b){{
      return b.toString(16).padStart(2,'0');
    }}).join('');
  }});
}}

// Hash multiple values → array
function hashArr(arr){{
  if(!arr||!arr.length)return Promise.resolve(null);
  return Promise.all(arr.map(function(v){{return sha(v);}}));
}}

/* ─── Send Event ───────────────────────────────────────────────── */
function send(eventName, customData, userData){{
  var fbc=gc('_fbc');
  var fbp=gc('_fbp');
  var ttp=gc('_ttp');
  var ttclid=qp('ttclid')||gc('_ttclid');

  // Build user_data
  var ud={{}};
  ud.client_user_agent=navigator.userAgent;
  if(fbc)ud.fbc=fbc;
  if(fbp)ud.fbp=fbp;
  if(ttp)ud.ttp=ttp;
  if(ttclid)ud.ttclid=ttclid;

  // Merge stored user identity
  var mergedUser=Object.assign({{}},U,userData||{{}});

  // Hash PII fields, then send
  var hashJobs=[];
  var piiFields=['em','ph','fn','ln','ct','st','zp','country'];

  piiFields.forEach(function(f){{
    if(mergedUser[f]){{
      var vals=Array.isArray(mergedUser[f])?mergedUser[f]:[mergedUser[f]];
      hashJobs.push(
        hashArr(vals).then(function(hashed){{
          if(hashed)ud[f]=hashed;
        }})
      );
    }}
  }});

  // Copy non-PII fields
  if(mergedUser.external_id){{
    var eid=Array.isArray(mergedUser.external_id)?mergedUser.external_id:[mergedUser.external_id];
    ud.external_id=eid;
  }}

  Promise.all(hashJobs).then(function(){{
    var evt={{
      event_name:eventName,
      event_time:Math.floor(Date.now()/1000),
      event_id:uid(),
      event_source_url:location.href,
      action_source:'website',
      user_data:ud
    }};

    if(customData){{
      var cd={{}};
      if(customData.value!=null)cd.value=Number(customData.value);
      if(customData.currency)cd.currency=customData.currency;
      if(customData.content_ids)cd.content_ids=customData.content_ids;
      if(customData.content_type)cd.content_type=customData.content_type;
      if(customData.order_id)cd.order_id=customData.order_id;
      if(customData.num_items!=null)cd.num_items=Number(customData.num_items);
      evt.custom_data=cd;
    }}

    var body=JSON.stringify({{data:[evt]}});

    // Prefer sendBeacon (works even on page unload)
    if(navigator.sendBeacon){{
      var blob=new Blob([body],{{type:'application/json'}});
      var ok=navigator.sendBeacon(E+'?key='+K,blob);
      if(!ok)fallbackFetch(body);
    }}else{{
      fallbackFetch(body);
    }}
  }}).catch(function(err){{
    // Silently fail — never break client's website
    if(typeof console!=='undefined')console.warn('[CAPI]',err);
  }});
}}

function fallbackFetch(body){{
  fetch(E+'?key='+K,{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:body,
    keepalive:true
  }}).catch(function(){{}});
}}

/* ─── Global API ───────────────────────────────────────────────── */
function capi(cmd){{
  if(cmd==='track'){{
    var evtName=arguments[1];
    var cd=arguments[2]||null;
    var ud=arguments[3]||null;
    if(!R){{Q.push([evtName,cd,ud]);return;}}
    send(evtName,cd,ud);
  }}
  else if(cmd==='setUser'){{
    var data=arguments[1]||{{}};
    // Convenience: 'email' → 'em', 'phone' → 'ph'
    if(data.email){{data.em=[data.email];delete data.email;}}
    if(data.phone){{data.ph=[data.phone];delete data.phone;}}
    if(data.first_name){{data.fn=[data.first_name];delete data.first_name;}}
    if(data.last_name){{data.ln=[data.last_name];delete data.last_name;}}
    if(data.city){{data.ct=[data.city];delete data.city;}}
    if(data.state){{data.st=[data.state];delete data.state;}}
    if(data.zip){{data.zp=[data.zip];delete data.zip;}}
    Object.assign(U,data);
  }}
}}

// Expose globally
window.capi=capi;

/* ─── SPA Support (History API) ────────────────────────────────── */
var origPush=history.pushState;
var origReplace=history.replaceState;
history.pushState=function(){{
  origPush.apply(this,arguments);
  setTimeout(function(){{send('PageView');}},100);
}};
history.replaceState=function(){{
  origReplace.apply(this,arguments);
  setTimeout(function(){{send('PageView');}},100);
}};
window.addEventListener('popstate',function(){{
  setTimeout(function(){{send('PageView');}},100);
}});

/* ─── Init ─────────────────────────────────────────────────────── */
function init(){{
  R=true;
  // Fire auto PageView
  send('PageView');
  // Flush queued events
  Q.forEach(function(q){{send(q[0],q[1],q[2]);}});
  Q=[];
}}

if(document.readyState==='loading'){{
  document.addEventListener('DOMContentLoaded',init);
}}else{{
  init();
}}

}})();"""
