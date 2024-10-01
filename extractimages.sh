#!/bin/bash

# Function to verify checksums
verify_checksums() {
    local file=$1
    local checksum_file=$2
    echo "Verifying checksums for $file..."
    sha256sum -c "$checksum_file"
}

# Function to extract and verify contents
extract_and_verify() {
    local archive=$1
    local destination=$2
    local checksum_file=$3

    echo "Extracting $archive to $destination..."
    tar xzvf "$archive" -C "$destination"

    echo "Verifying extracted contents..."
    pushd "$destination" > /dev/null
    verify_checksums "." "$checksum_file"
    popd > /dev/null
}

# Set the base directory
BASE_DIR="/var/www/DungeonMind"

# Verify compressed archives
verify_checksums "$BASE_DIR/images_main.tar.gz" "$BASE_DIR/checksums_main_compressed.txt"
verify_checksums "$BASE_DIR/images_storegenerator.tar.gz" "$BASE_DIR/checksums_storegenerator_compressed.txt"
verify_checksums "$BASE_DIR/images_storegenerator_assets.tar.gz" "$BASE_DIR/checksums_storegenerator_assets_compressed.txt"

# Extract and verify main images
extract_and_verify "$BASE_DIR/images_main.tar.gz" "$BASE_DIR" "$BASE_DIR/checksums_main_uncompressed.txt"

# Extract and verify storegenerator images
extract_and_verify "$BASE_DIR/images_storegenerator.tar.gz" "$BASE_DIR" "$BASE_DIR/checksums_storegenerator_uncompressed.txt"

# Extract and verify storegenerator assets
extract_and_verify "$BASE_DIR/images_storegenerator_assets.tar.gz" "$BASE_DIR" "$BASE_DIR/checksums_storegenerator_assets_uncompressed.txt"

echo "Uncompression and verification completed."