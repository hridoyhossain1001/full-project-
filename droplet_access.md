# Buykori AdSync — Droplet Access & Infrastructure Guide

This document contains connection credentials, directory structures, and commands for the production droplet so that future AI agents or developers can seamlessly access, manage, and deploy updates.

---

## 🔑 Droplet Connection Credentials

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Host IP** | `159.223.59.78` | Public IP of the DigitalOcean Droplet |
| **Username** | `root` | System administrator account |
| **SSH Port** | `22` | Default SSH port |
| **Authentication Method** | Password / SSH Key | Key-based authentication is highly recommended |
| **Root Password** | `1122334455Hk` | Active root password (updated on May 25, 2026) |

---

## 📁 System Architecture & Directory Structure

* **Project Root:** `/var/www/buykori-adsync`
* **Python Virtual Environment:** `/var/www/buykori-adsync/venv` (Python 3.12)
* **Supervisor Logs:** `/var/log/supervisor/`
  * Web Service Error Log: `/var/log/supervisor/buykori-web.err.log`
  * Web Service Output Log: `/var/log/supervisor/buykori-web.out.log`
  * Worker Service Error Log: `/var/log/supervisor/buykori-worker.err.log`
  * Worker Service Output Log: `/var/log/supervisor/buykori-worker.out.log`

---

## 🛠️ Essential Operational Commands

Run these commands inside `/var/www/buykori-adsync` as root (or using `sudo`):

### 1. Service Management (Supervisor)
To monitor and manage the running services:
```bash
# Check status of the services
sudo supervisorctl status

# Restart the application and background workers
sudo supervisorctl restart buykori-web buykori-worker

# Stop all services
sudo supervisorctl stop all
```

### 2. Database Migrations (Alembic)
To apply new database schema updates to the PostgreSQL production database:
```bash
# Run migrations inside the project root
./venv/bin/alembic upgrade head
```

### 3. Deploying Local Changes to Server
A helper script is available in the local workspace to synchronize changes via SFTP, run migrations, and automatically restart services. Run it locally:
```powershell
# From local workspace root
python scratch/deploy_updates.py
```

---

> [!WARNING]
> Do not modify `.env` configuration variables directly on the server without verifying compatibility with the PostgreSQL instance. The database username is `buykori` and the database name is `buykori_adsync`.
