#!/bin/bash

# Server and directory configurations
SERVER_USER="alan"
SERVER_IP="191.101.14.169"
REMOTE_PROJECT_PATH="/var/www/DungeonMind"
LOCAL_PROJECT_PATH="/media/drakosfire/Shared1/DungeonMind"

# Step 1: SSH into the server, backup, and remove existing directory
ssh -tt "$SERVER_USER@$SERVER_IP" << "EOF"
    # Stop and remove all containers
    sudo docker stop \$(sudo docker ps -q) || true
    sudo docker rm \$(sudo docker ps -a -q) || true

    # Backup the existing project directory
    if [ -d "$REMOTE_PROJECT_PATH" ]; then
        echo "Backing up existing project directory..."
        sudo cp -r "$REMOTE_PROJECT_PATH" "${REMOTE_PROJECT_PATH}_backup_$(date +%F)"
        
        echo "Removing the existing project directory..."
        sudo rm -rf "$REMOTE_PROJECT_PATH"
    else
        echo "No existing project directory found. Skipping backup and removal."
    fi
EOF

# Step 2: Sync the new project directory from local to the server
echo "Syncing new project directory..."
rsync -avz --progress --delete-after "$LOCAL_PROJECT_PATH/" "$SERVER_USER@$SERVER_IP:$REMOTE_PROJECT_PATH"

# Step 3: SSH into the server again to restart any necessary services
ssh -tt "$SERVER_USER@$SERVER_IP" << "EOF"
    cd "$REMOTE_PROJECT_PATH"

    # Copy the dungeonmind nginx config file to the server
    sudo cp -r "$LOCAL_PROJECT_PATH/dungeonmind" /etc/nginx/sites-available/dungeonmind.net

    # Optional: Restart Docker services if necessary
    if [ -f "docker-compose.yml" ]; then
        echo "Restarting Docker services..."
        sudo docker-compose down && sudo docker-compose up -d
    fi

    # Optional: Restart other services if necessary, e.g., Nginx
    echo "Restarting Nginx..."
    sudo systemctl restart nginx

    echo "Deployment completed!"
EOF
