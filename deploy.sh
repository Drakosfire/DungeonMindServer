#!/bin/bash
# Function to verify checksums
verify_checksums() {
    local compressed_file=$1
    local uncompressed_dir=$2
    local compressed_checksum_file=$3
    local uncompressed_checksum_file=$4

    echo "Verifying checksum for $compressed_file..."
    sha256sum -c "$compressed_checksum_file"

    echo "Decompressing $compressed_file..."
    tar xzf "$compressed_file" -C "$uncompressed_dir"

    echo "Verifying checksums for uncompressed files in $uncompressed_dir..."
    pushd "$uncompressed_dir" > /dev/null
    sha256sum -c "../../$uncompressed_checksum_file"
    popd > /dev/null
}
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

# Verify and decompress images
verify_checksums "images_main.tar.gz" "./static" "checksums_main_compressed.txt" "checksums_main_uncompressed.txt"
verify_checksums "images_storegenerator.tar.gz" "./storegenerator/static" "checksums_storegenerator_compressed.txt" "checksums_storegenerator_uncompressed.txt"

# Build the Docker image
echo "Building Docker image 'dungeonmind-image'..."
docker build -t dungeonmind-image .

# Run the Docker container with the specified environment file and port mapping
echo "Running Docker container 'dungeonmind-container'..."
sudo docker run -v /var/www/DungeonMind/saved_data:/home/user/app/saved_data --env-file .env -d -p 7860:7860 --name dungeonmind-container dungeonmind-image

echo "Script execution completed."
