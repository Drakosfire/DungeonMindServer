#!/bin/bash

# Stop the Docker container
echo "Stopping Docker container 'storegenerator-container'..."
docker stop storegenerator-container

# Remove the Docker container
echo "Removing Docker container 'storegenerator-container'..."
docker rm storegenerator-container

# Remove the Docker image
echo "Removing Docker image 'storegenerator-image'..."
docker rmi storegenerator-image

# Build the Docker image
echo "Building Docker image 'storegenerator-image'..."
docker build -t storegenerator-image .

# Run the Docker container with the specified environment file and port mapping
echo "Running Docker container 'storegenerator-container'..."
sudo docker run --env-file .env -d -p 5000:7860 --name storegenerator-container storegenerator-image

echo "Script execution completed."
