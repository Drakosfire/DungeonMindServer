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

echo "Script execution completed."
