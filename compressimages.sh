#!/bin/bash

# Function to create checksums
create_checksums() {
    local dir=$1
    local output=$2
    find "$dir" -type f -print0 | sort -z | xargs -0 sha256sum > "$output"
}

# Create checksums for uncompressed images
echo "Creating checksums for uncompressed images..."
create_checksums "./static/images" "checksums_main_uncompressed.txt"
create_checksums "./storegenerator/static/images" "checksums_storegenerator_uncompressed.txt"

# Compress images
echo "Compressing images..."
tar czvf images_main.tar.gz -C . static/images
tar czvf images_storegenerator.tar.gz -C . storegenerator/static/images

# Create checksums for compressed images
echo "Creating checksums for compressed images..."
sha256sum images_main.tar.gz > checksums_main_compressed.txt
sha256sum images_storegenerator.tar.gz > checksums_storegenerator_compressed.txt

# SCP the compressed files and checksums to the server
echo "Copying files to server..."
scp images_main.tar.gz images_storegenerator.tar.gz checksums_*.txt alan@191.101.14.169:/var/www/DungeonMind/

# SSH into server and run deploy script
echo "SSHing into server and running deploy script..."
ssh alan@191.101.14.169 "sudo bash /var/www/DungeonMind/deploy.sh"

echo "Local deployment script completed."
