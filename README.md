# Buykori AdSync

Multi-tenant ad tracking and conversion sync platform that forwards client site events (Conversions API) to Facebook, TikTok, and GA4 with built-in deduplication, rate-limiting, and quota management.

---

## 🚀 Features

- **Multi-Tenant Event Syncing:** Support for multiple clients, each with independent API Keys, Pixel IDs, and tokens.
- **Conversion APIs:** Sync conversion events to Facebook Conversions API (CAPI), TikTok Events API, and Google Analytics 4 (GA4).
- **Event Deduplication:** Database-level deduplication to prevent duplicate server-side and browser-side conversions.
- **Client Management Portal:** Modern administrative dashboard and client dashboard interfaces.
- **Plugin Delivery:** Auto-update feed and dynamically configured WordPress plugin downloads.

---

## 🛠️ Local Setup & Installation

### 1. Prerequisites
- **Python:** 3.10 or higher (Python 3.13 recommended)
- **Database:** SQLite (local development) or PostgreSQL (production)
- **WordPress:** Local testing environment for the WordPress plugin

### 2. Install Dependencies
Clone the repository, initialize a virtual environment, and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the project root (use `.env.example` as a starting point):
```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-admin-password
ADMIN_API_KEY=your-admin-api-key
DATABASE_URL=sqlite+aiosqlite:///./test.db
REDIS_URL=redis://localhost:6379/0  # optional locally, required for production health/stream ingest
ENCRYPTION_KEY=your-32-byte-fernet-key
```
*Note: You can generate a random 32-byte Fernet key with:*
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Database Migrations
Initialize and upgrade your database schema:
```bash
# If using Alembic migrations
alembic upgrade head

# For initial schema creation in development only (alternative)
# Set ENABLE_CREATE_ALL=true in .env
```

### 5. Running the Application
Start the FastAPI server locally:
```bash
uvicorn app.main:app --reload --port 8000
```
- **Interactive API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Admin Panel:** [http://localhost:8000/api/v1/admin](http://localhost:8000/api/v1/admin)
- **Client Portal:** [http://localhost:8000/client](http://localhost:8000/client)

---

## 🧪 Testing

We use `pytest` for backend testing. All database operations in tests are isolated and use in-memory SQLite instances.

Run the test suite:
```bash
python -m pytest
```

To run with verbose output:
```bash
python -m pytest -v
```

---

## ⚙️ Running Utility Scripts

The `scripts/` directory contains helper scripts for database inspections, portal key management, diagnostics, and packaging.

Because these scripts import internal app modules (e.g., `from app.database import ...`), Python must search the project root directory when running them. **Always run utility scripts from the project root using one of the following methods:**

### Method A: Using `PYTHONPATH` (Recommended)
Prepend the command with the `PYTHONPATH` environment variable:
- **macOS / Linux:**
  ```bash
  PYTHONPATH=. python scripts/db/check_clients.py
  ```
- **Windows (PowerShell):**
  ```powershell
  $env:PYTHONPATH="."
  python scripts/db/check_clients.py
  ```
- **Windows (CMD):**
  ```cmd
  set PYTHONPATH=.
  python scripts/db/check_clients.py
  ```

### Method B: Using Module Flag `-m`
Invoke the script as a module from the project root:
```bash
python -m scripts.db.check_clients
```

### Common Utility Scripts
- **Database Status:** `scripts/db/check_clients.py`, `scripts/db/check_events.py`
- **Key Generation:** `scripts/keys/create_client.py`, `scripts/keys/get_api_key.py`
- **Diagnostics:** `scripts/ops/tiktok_diag.py`
- **Packaging:** `scripts/ops/zip_plugin.py`

---

## 📦 WordPress Plugin Installation

1. Log into the Client Portal.
2. Click **Download Plugin** from the top menu bar. This downloads a customized plugin ZIP (`buykori-adsync.zip`) preloaded with your API key and server gateway URL.
3. Upload the ZIP to your WordPress site and activate the plugin.
