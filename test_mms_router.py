#!/usr/bin/env python3
"""
Test script for MMS functionality in sms_router.py
This script simulates Twilio webhook requests with MMS data.
"""

import asyncio
import json
import httpx
import os
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:7860"  # Adjust if your server runs on different port
SMS_ENDPOINT = f"{BASE_URL}/api/sms/receive"
RETRY_ENDPOINT = f"{BASE_URL}/api/sms/retry-failed"
MEDIA_TYPES_ENDPOINT = f"{BASE_URL}/api/sms/supported-media-types"

# Get test credentials from environment variables
TEST_ACCOUNT_SID = os.getenv("TEST_TWILIO_ACCOUNT_SID", "AC" + "1" * 32)  # Default test value
TEST_MESSAGE_SID_SMS = os.getenv("TEST_MESSAGE_SID_SMS", "SM" + "1" * 32)  # Default test value
TEST_MESSAGE_SID_MMS = os.getenv("TEST_MESSAGE_SID_MMS", "MM" + "1" * 32)  # Default test value
TEST_FROM_NUMBER = os.getenv("TEST_FROM_NUMBER", "+1234567890")
TEST_TO_NUMBER = os.getenv("TEST_TO_NUMBER", "+1987654321")

def create_sample_sms_data():
    """Create sample SMS data (no media)"""
    return {
        "From": TEST_FROM_NUMBER,
        "To": TEST_TO_NUMBER,
        "Body": "Hello, this is a test SMS message",
        "MessageSid": TEST_MESSAGE_SID_SMS,
        "NumMedia": "0",
        "AccountSid": TEST_ACCOUNT_SID,
        "ApiVersion": "2010-04-01",
        "SmsStatus": "received"
    }

def create_sample_mms_data():
    """Create sample MMS data with multiple media items"""
    return {
        "From": TEST_FROM_NUMBER,
        "To": TEST_TO_NUMBER,
        "Body": "Check out these images!",
        "MessageSid": TEST_MESSAGE_SID_MMS,
        "NumMedia": "2",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/ACTEST/Messages/MMTEST/Media/ME123",
        "MediaContentType0": "image/jpeg",
        "MediaUrl1": "https://api.twilio.com/2010-04-01/Accounts/ACTEST/Messages/MMTEST/Media/ME124",
        "MediaContentType1": "video/mp4",
        "AccountSid": TEST_ACCOUNT_SID,
        "ApiVersion": "2010-04-01",
        "SmsStatus": "received"
    }

def create_unsupported_mms_data():
    """Create MMS data with unsupported media types"""
    return {
        "From": TEST_FROM_NUMBER,
        "To": TEST_TO_NUMBER,
        "Body": "This has unsupported media",
        "MessageSid": "MM" + "9" * 32,
        "NumMedia": "2",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/ACTEST/Messages/MMTEST/Media/ME999",
        "MediaContentType0": "application/octet-stream",  # Unsupported
        "MediaUrl1": "https://api.twilio.com/2010-04-01/Accounts/ACTEST/Messages/MMTEST/Media/ME998",
        "MediaContentType1": "image/png",  # Supported
        "AccountSid": TEST_ACCOUNT_SID,
        "ApiVersion": "2010-04-01",
        "SmsStatus": "received"
    }

def create_invalid_webhook_data():
    """Create invalid webhook data to test validation"""
    return {
        "Body": "Invalid webhook missing required fields",
        "NumMedia": "invalid_number",
        # Missing From and MessageSid (required fields)
        "To": TEST_TO_NUMBER
    }

def create_inconsistent_mms_data():
    """Create MMS data with SMS SID (inconsistency test)"""
    return {
        "From": TEST_FROM_NUMBER,
        "To": TEST_TO_NUMBER,
        "Body": "This has media but SMS SID",
        "MessageSid": TEST_MESSAGE_SID_SMS,  # SMS SID but has media
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/ACTEST/Messages/SMTEST/Media/ME123",
        "MediaContentType0": "image/jpeg",
        "AccountSid": TEST_ACCOUNT_SID,
        "ApiVersion": "2010-04-01",
        "SmsStatus": "received"
    }

def create_real_twilio_mms_data():
    """Create MMS data that matches real Twilio webhook format"""
    # Use environment variables for real test data if available
    real_account_sid = os.getenv("REAL_TWILIO_ACCOUNT_SID", TEST_ACCOUNT_SID)
    real_message_sid = os.getenv("REAL_MESSAGE_SID", TEST_MESSAGE_SID_MMS)
    real_from_number = os.getenv("REAL_FROM_NUMBER", TEST_FROM_NUMBER)
    real_to_number = os.getenv("REAL_TO_NUMBER", TEST_TO_NUMBER)
    real_messaging_service_sid = os.getenv("REAL_MESSAGING_SERVICE_SID", "MG" + "a" * 32)
    
    return {
        "ToCountry": "US",
        "MediaContentType0": "image/jpeg", 
        "ToState": "DE",
        "SmsMessageSid": real_message_sid,
        "NumMedia": "1",
        "ToCity": "OCEAN VIEW", 
        "FromZip": "80620",
        "SmsSid": real_message_sid,
        "FromState": "CO",
        "SmsStatus": "received",
        "FromCity": "GREELEY",
        "Body": "MMS test",
        "FromCountry": "US",
        "To": real_to_number,
        "MessagingServiceSid": real_messaging_service_sid,
        "ToZip": "",
        "NumSegments": "1", 
        "MessageSid": real_message_sid,
        "AccountSid": real_account_sid,
        "From": real_from_number,
        "MediaUrl0": f"https://api.twilio.com/2010-04-01/Accounts/{real_account_sid}/Messages/{real_message_sid}/Media/ME" + "a" * 32,
        "ApiVersion": "2010-04-01"
    }

async def test_endpoint(client: httpx.AsyncClient, endpoint: str, data: dict, test_name: str, expected_status=200):
    """Test a specific endpoint with given data"""
    print(f"\n{'='*50}")
    print(f"Testing: {test_name}")
    print(f"Endpoint: {endpoint}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        response = await client.post(endpoint, data=data)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Response: {response.text}")
        
        # Handle different expected status codes
        if isinstance(expected_status, list):
            # Multiple acceptable status codes
            if response.status_code in expected_status:
                print("✅ Test PASSED")
            else:
                print(f"❌ Test FAILED (expected one of {expected_status}, got {response.status_code})")
        else:
            # Single expected status code
            if response.status_code == expected_status:
                print("✅ Test PASSED")
            else:
                print(f"❌ Test FAILED (expected {expected_status}, got {response.status_code})")
            
    except Exception as e:
        print(f"❌ Test ERROR: {str(e)}")

async def test_get_endpoint(client: httpx.AsyncClient, endpoint: str, test_name: str):
    """Test a GET endpoint"""
    print(f"\n{'='*50}")
    print(f"Testing: {test_name}")
    print(f"Endpoint: {endpoint}")
    
    try:
        response = await client.get(endpoint)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Test PASSED")
        else:
            print("❌ Test FAILED")
            
    except Exception as e:
        print(f"❌ Test ERROR: {str(e)}")

async def main():
    """Run all tests"""
    print("🧪 Starting MMS Router Tests")
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Basic SMS (no media)
        await test_endpoint(
            client, 
            SMS_ENDPOINT, 
            create_sample_sms_data(), 
            "Basic SMS Message"
        )
        
        # Test 2: MMS with supported media types
        await test_endpoint(
            client, 
            SMS_ENDPOINT, 
            create_sample_mms_data(), 
            "MMS with Supported Media"
        )
        
        # Test 3: MMS with mixed supported/unsupported media types
        await test_endpoint(
            client, 
            SMS_ENDPOINT, 
            create_unsupported_mms_data(), 
            "MMS with Mixed Media Types"
        )
        
        # Test 4: Invalid webhook data (should return 400 or 500)
        await test_endpoint(
            client, 
            SMS_ENDPOINT, 
            create_invalid_webhook_data(), 
            "Invalid Webhook Data (Validation Test)",
            expected_status=[400, 500]  # Accept either 400 (Bad Request) or 500 (Internal Server Error)
        )
        
        # Test 5: Inconsistent MMS data (should show warnings)
        await test_endpoint(
            client, 
            SMS_ENDPOINT, 
            create_inconsistent_mms_data(), 
            "Inconsistent MMS Data (Warning Test)"
        )
        
        # Test 6: Get supported media types
        await test_get_endpoint(
            client, 
            MEDIA_TYPES_ENDPOINT, 
            "Get Supported Media Types"
        )
        
        # Test 7: Retry failed messages
        await test_get_endpoint(
            client, 
            RETRY_ENDPOINT, 
            "Retry Failed Messages"
        )
        
        # Test 8: Real Twilio MMS format
        await test_endpoint(
            client, 
            SMS_ENDPOINT, 
            create_real_twilio_mms_data(), 
            "Real Twilio MMS Format Test"
        )
    
    print(f"\n{'='*50}")
    print("🏁 All tests completed!")

if __name__ == "__main__":
    asyncio.run(main()) 