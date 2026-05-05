# CAPI Gateway — Deployment Guide (Heroku CLI)

## প্রজেক্ট স্ট্রাকচার
```
Server site traking/
├── app/
│   ├── main.py              # FastAPI app + lifespan + CORS + routers
│   ├── database.py          # Async PostgreSQL engine + session
│   ├── dependencies.py      # API Key auth dependency
│   ├── limiter.py           # Shared rate limiter instance
│   ├── security.py          # Fernet token encryption/decryption
│   ├── models/
│   │   ├── client.py        # Client model (quota/rate fields)
│   │   ├── event_log.py     # Event log (success/failed + event_id dedup)
│   │   └── failed_event.py  # Failed event retry queue
│   ├── schemas/event.py     # Pydantic schemas
│   ├── routers/
│   │   ├── events.py        # POST /events — dedup → quota → CAPI → log
│   │   ├── admin.py         # Admin Panel (HTML dashboard + forms)
│   │   └── monitoring.py    # Health + stats endpoints
│   └── services/
│       ├── capi_service.py  # Facebook CAPI HTTP client
│       └── retry_service.py # Background retry with exponential backoff
├── migrations/
│   ├── env.py               # Async Alembic migrations
│   ├── script.py.mako       # Migration template
│   └── versions/            # Migration files
├── requirements.txt         # 10 dependencies
├── Procfile                 # Heroku: uvicorn, 1 worker
├── runtime.txt              # Python 3.13.0
├── alembic.ini              # DB migration config
├── DEPLOY_GUIDE.md          # এই ফাইল
└── .env                     # লোকাল টেস্টের জন্য (Heroku-তে push হবে না)
```

---

## ধাপ ১ — Prerequisites (একবারই করতে হবে)

### Git Install করুন
https://git-scm.com/downloads

### Heroku CLI Install করুন
https://devcenter.heroku.com/articles/heroku-cli

Terminal/PowerShell-এ চেক করুন:
```
git --version
heroku --version
```

---

## ধাপ ২ — Heroku Login

```powershell
heroku login
```
ব্রাউজার খুলবে, লগইন করুন।

---

## ধাপ ৩ — Git Repository Init

আপনার প্রজেক্ট ফোল্ডারে (Server site traking):
```powershell
git init
git add .
git commit -m "Initial commit: CAPI Gateway"
```

---

## ধাপ ৪ — Heroku App তৈরি করুন

```powershell
heroku create capi-gateway-yourname
```
(yourname পরিবর্তন করুন, যেমন: capi-gateway-hridoy)

---

## ধাপ ৫ — Postgres Database যোগ করুন ($5/মাস)

```powershell
heroku addons:create heroku-postgresql:essential-0 -a capi-gateway-yourname
```

DATABASE_URL অটো সেট হয়ে যাবে।

---

## ধাপ ৬ — Environment Variables সেট করুন

```powershell
# Admin credentials
heroku config:set ADMIN_USERNAME=admin ADMIN_PASSWORD=your-strong-password -a capi-gateway-yourname

# Encryption key (Token encryption-এর জন্য আবশ্যক)
# প্রথমে key জেনারেট করুন:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# তারপর সেট করুন:
heroku config:set ENCRYPTION_KEY=your-generated-key-here -a capi-gateway-yourname
```

> ⚠️ **Important:** `ENCRYPTION_KEY` সেট না করলে access token plaintext-এ সংরক্ষিত হবে। Production-এ অবশ্যই সেট করুন।

---

## ধাপ ৭ — Deploy করুন

```powershell
git push heroku main
```

---

## ধাপ ৮ — অ্যাপ চেক করুন

```powershell
heroku open -a capi-gateway-yourname
```

অথবা ব্রাউজারে যান:
- **Health Check:** `https://capi-gateway-yourname.herokuapp.com/`
- **Admin Panel:** `https://capi-gateway-yourname.herokuapp.com/api/v1/admin`
- **API Docs:** `https://capi-gateway-yourname.herokuapp.com/docs`
- **System Status:** `https://capi-gateway-yourname.herokuapp.com/api/v1/health/detailed`
- **FB Connectivity:** `https://capi-gateway-yourname.herokuapp.com/api/v1/health/facebook`
- **Client Stats:** `https://capi-gateway-yourname.herokuapp.com/api/v1/stats/clients`

---

## ধাপ ৯ — Custom Domain যোগ করুন (Optional, Heroku লুকানোর জন্য)

```powershell
heroku domains:add tracking.yourname.com -a capi-gateway-yourname
heroku domains -a capi-gateway-yourname
```

DNS Target নোট করুন (যেমন: abc123.herokudns.com)।
আপনার Domain provider-এ CNAME Record যোগ করুন:
- Host: tracking
- Value: abc123.herokudns.com

SSL অটো সেটআপ হবে।

---

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Tenant Events** | একাধিক ক্লায়েন্ট, আলাদা API Key ও Pixel ID |
| **Token Encryption** | Fernet-এ encrypted, DB-তে plaintext থাকে না |
| **Event Deduplication** | একই event_id ২৪ ঘণ্টার মধ্যে দ্বিতীয়বার পাঠালে skip |
| **Per-Client Rate Limit** | প্রতিটি ক্লায়েন্টের আলাদা rate limit (default 5000/min) |
| **Daily Quota** | প্রতিদিন সর্বোচ্চ event সংখ্যা (default 100K) |
| **Retry Queue** | ব্যর্থ event স্বয়ংক্রিয়ভাবে retry হয় (5x, exponential backoff) |
| **Monitoring** | Health check, FB connectivity, per-client stats |
| **Admin Dashboard** | Dark UI, real-time analytics, client management |

---

## Useful Commands

```powershell
# লাইভ লগ দেখুন
heroku logs --tail -a capi-gateway-yourname

# অ্যাপ রিস্টার্ট করুন
heroku restart -a capi-gateway-yourname

# ডাটাবেস চেক করুন
heroku pg:info -a capi-gateway-yourname

# Config vars দেখুন
heroku config -a capi-gateway-yourname

# Alembic migration চালাতে (schema change-এর পর)
heroku run alembic upgrade head -a capi-gateway-yourname
```

---

## Admin Panel ব্যবহার

1. `https://your-app.herokuapp.com/api/v1/admin` এ যান
2. Admin credentials দিয়ে লগইন করুন
3. নতুন ক্লায়েন্ট যোগ করুন (নাম, Pixel ID, Access Token)
4. "📋 Instructions" বাটনে ক্লিক করে ক্লায়েন্টকে পাঠানোর জন্য ইন্সট্রাকশন নিন

---

## Client-এর কাছ থেকে কী নেবেন?

- Facebook Pixel ID (FB Events Manager → Settings)
- CAPI Access Token (Events Manager → Settings → Conversions API → Generate Token)
- ক্লায়েন্টের নাম

আপনি "Instructions" পেজে ক্লিক করলে সব তৈরি হয়ে যাবে — ক্লায়েন্টকে শুধু লিংকটা পাঠান।
