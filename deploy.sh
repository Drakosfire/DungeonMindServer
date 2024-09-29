#!/bin/bash

# Stop the Docker container
echo "Stopping Docker container 'dungeonmind-container'..."
docker stop dungeonmind-container

# Remove the Docker container
echo "Removing Docker container 'dungeonmind-container'..."
docker rm dungeonmind-container

# Remove the Docker image
echo "Removing Docker image 'dungeonmind-image'..."
docker rmi dungeonmind-image

# Navigate to /var/www/DungeonMind directory
echo "Navigating to /var/www/DungeonMind directory..."
cd /var/www/DungeonMind

# Clone the DungeonMind repository
echo "Pulling the DungeonMind repository..."
git pull

# Clone the storegenerator submodule
git submodule update --init --recursive

# Build the Docker image
echo "Building Docker image 'dungeonmind-image'..."
docker build -t dungeonmind-image .

# Run the Docker container with the specified environment file and port mapping
echo "Running Docker container 'dungeonmind-container'..."
sudo docker run -v /var/www/DungeonMind/saved_data:/home/user/app/saved_data --env-file .env -d -p 7860:7860 --name dungeonmind-container dungeonmind-image

echo "Script execution completed."
