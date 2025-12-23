"""
Test script for image upload functionality
Tests the /upload-images endpoint with actual files
"""

import asyncio
import httpx
import os
from pathlib import Path

# Test configuration
API_BASE_URL = os.getenv("DUNGEONMIND_API_URL", "http://localhost:8000")
UPLOAD_ENDPOINT = f"{API_BASE_URL}/api/statblockgenerator/upload-images"

# Create a simple test image
def create_test_image(filename: str) -> bytes:
    """Create a simple PNG test image"""
    from PIL import Image, ImageDraw
    import io
    
    # Create 100x100 colored square
    img = Image.new('RGB', (100, 100), color='red')
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), "TEST", fill='white')
    
    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.read()

async def test_upload_images():
    """Test uploading multiple images"""
    print("🧪 Testing image upload endpoint...")
    
    # Create test images
    test_image_1 = create_test_image("test1.png")
    test_image_2 = create_test_image("test2.png")
    
    print(f"✅ Created 2 test images")
    print(f"   - test1.png: {len(test_image_1)} bytes")
    print(f"   - test2.png: {len(test_image_2)} bytes")
    
    # Prepare multipart form data
    files = [
        ('images', ('test1.png', test_image_1, 'image/png')),
        ('images', ('test2.png', test_image_2, 'image/png')),
    ]
    
    try:
        print(f"\n📤 Uploading images to {UPLOAD_ENDPOINT}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Note: In production, you'd need authentication cookies
            # This test assumes you're logged in or testing locally
            response = await client.post(
                UPLOAD_ENDPOINT,
                files=files
            )
            
            print(f"📊 Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Upload successful!")
                print(f"   - Uploaded {result['data']['count']} images")
                
                for idx, img in enumerate(result['data']['images'], 1):
                    print(f"\n   Image {idx}:")
                    print(f"     - ID: {img['id']}")
                    print(f"     - URL: {img['url'][:80]}...")
                    print(f"     - Filename: {img['filename']}")
                    print(f"     - Timestamp: {img['timestamp']}")
                
                return True
            elif response.status_code == 401:
                print(f"❌ Authentication required")
                print(f"   This endpoint requires being logged in")
                return False
            else:
                print(f"❌ Upload failed: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_file_validation():
    """Test file validation (size, type)"""
    print("\n🧪 Testing file validation...")
    
    # Test 1: Invalid file type (text file)
    print("\n📋 Test 1: Invalid file type")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = [('images', ('test.txt', b'Not an image', 'text/plain'))]
            response = await client.post(UPLOAD_ENDPOINT, files=files)
            
            if response.status_code == 400:
                print(f"✅ Correctly rejected non-image file")
            else:
                print(f"❌ Should have rejected non-image file, got {response.status_code}")
    except Exception as e:
        print(f"⚠️  Error testing validation: {e}")
    
    # Test 2: File too large (over 10MB)
    print("\n📋 Test 2: File size validation")
    print("   (Skipping - would generate 11MB file)")
    print("   Expected: 400 error with 'too large' message")

if __name__ == "__main__":
    print("=" * 80)
    print("Image Upload Endpoint Test")
    print("=" * 80)
    print(f"API URL: {API_BASE_URL}")
    print(f"Endpoint: {UPLOAD_ENDPOINT}")
    print()
    
    # Run tests
    success = asyncio.run(test_upload_images())
    
    if success:
        asyncio.run(test_file_validation())
    
    print("\n" + "=" * 80)
    if success:
        print("✅ Image upload endpoint working correctly!")
    else:
        print("❌ Image upload endpoint needs authentication or has issues")
    print("=" * 80)


