#!/bin/bash
# Frontend artifact deploy helper. It does not commit, pull, push, deploy backend
# code, or restart services. VM backend + schema migrations: scripts/deploy_backend_vm.sh

set -e

echo "Starting frontend artifact build..."

# -------- CONFIG --------
REMOTE_USER="your-user"
REMOTE_HOST="your-vm-ip"
SSH_KEY="~/.ssh/your-key.pem"
REMOTE_PATH="/path/to/project/frontend/build"
LOCAL_FRONTEND="frontend"
# ------------------------

echo "Building frontend..."
cd "$LOCAL_FRONTEND"
npm run build
cd ..

echo "Deploying build artifacts..."
rsync -avz --delete \
  -e "ssh -i $SSH_KEY" \
  /path/to/project/frontend/build/ \
  "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH"

echo "Deployment script complete."
echo "Restart the appropriate service on your target environment if needed."
