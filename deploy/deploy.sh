#!/bin/bash
set -e
set -o pipefail

# Configuration
PROJECT_DIR="/var/www/buykori-adsync"

echo "========================================="
echo "🔄 Starting Buykori AdSync Deployment..."
echo "========================================="

# Navigate to project directory
cd "$PROJECT_DIR"

# Fetch and pull latest changes
echo "📥 Pulling latest changes from git..."
git pull origin main

# Activate virtual environment and install requirements
echo "📦 Installing/updating dependencies..."
./venv/bin/pip install -r requirements.txt

# Run migrations
echo "🗄️ Running database migrations (Alembic)..."
./venv/bin/alembic upgrade head

# Restart Supervisor processes
echo "🔁 Reloading web and restarting worker services..."
sudo supervisorctl signal HUP buykori-web
sudo supervisorctl restart buykori-worker:*

# Check status
echo "📊 Checking service status..."
sudo supervisorctl status

echo "========================================="
echo "✅ Deployment completed successfully!"
echo "========================================="
