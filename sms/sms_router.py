from fastapi import APIRouter, Request, Response, HTTPException
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
import httpx
import logging
import os
from typing import Optional
import json
from datetime import datetime, timedelta
import asyncio
from functools import lru_cache

router = APIRouter()
logger = logging.getLogger(__name__)

EXTERNAL_API_KEY = os.getenv("EXTERNAL_MESSAGE_API_KEY")
EXTERNAL_ENDPOINT = os.getenv("EXTERNAL_SMS_ENDPOINT", "http://100.92.179.100:3081/api/receive-sms")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")  # API Key (username)
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")  # Changed from TWILIO_API_SECRET to TWILIO_AUTH_TOKEN
TEST_MODE = os.getenv("TWILIO_TEST_MODE", "false").lower() == "true"  # Bypass signature validation for testing
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# In-memory cache for failed messages
failed_messages = {}

# Supported media types for MMS
SUPPORTED_MEDIA_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/mpeg', 'video/webm',
    'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/webm',
    'application/pdf', 'text/plain', 'text/vcard'
}

def validate_media_type(content_type: str) -> bool:
    """Validate if the media type is supported"""
    if not content_type:
        return False
    return content_type.lower() in SUPPORTED_MEDIA_TYPES

def validate_twilio_message_format(form_data: dict) -> dict:
    """
    Validate and extract standard Twilio webhook fields.
    Returns a dict with validation results and extracted data.
    """
    validation = {
        "is_valid": True,
        "warnings": [],
        "errors": []
    }
    
    # Required fields check
    required_fields = ["From", "MessageSid"]
    for field in required_fields:
        if not form_data.get(field):
            validation["errors"].append(f"Missing required field: {field}")
            validation["is_valid"] = False
    
    # Message SID format validation
    message_sid = form_data.get("MessageSid", "")
    if message_sid and not (message_sid.startswith("SM") or message_sid.startswith("MM")):
        validation["warnings"].append(f"Unexpected MessageSid format: {message_sid}")
    
    # NumMedia validation
    try:
        num_media = int(form_data.get("NumMedia", 0))
        if num_media < 0:
            validation["warnings"].append(f"Negative NumMedia value: {num_media}")
    except (ValueError, TypeError):
        validation["warnings"].append(f"Invalid NumMedia value: {form_data.get('NumMedia')}")
    
    # Check for unexpected MMS/SMS mismatch
    is_mms_sid = message_sid.startswith("MM")
    has_media = int(form_data.get("NumMedia", 0)) > 0
    if is_mms_sid != has_media:
        validation["warnings"].append(f"Message type mismatch: SID suggests {'MMS' if is_mms_sid else 'SMS'} but NumMedia={form_data.get('NumMedia', 0)}")
    
    return validation

async def download_media_file(media_url: str, account_sid: str, auth_token: str) -> Optional[bytes]:
    """
    Download media file from Twilio URL with authentication.
    Returns the file content as bytes or None if failed.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                media_url,
                auth=(account_sid, auth_token)  # HTTP Basic Auth
            )
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Failed to download media from {media_url}: {str(e)}")
        return None

@lru_cache(maxsize=100)
def get_cached_response(message_id: str) -> Optional[dict]:
    """Cache successful responses to avoid duplicate processing"""
    return None

async def forward_message(payload: dict, headers: dict, retry_count: int = 0) -> bool:
    """Forward message to external API with retry logic"""
    try:
        logger.info(f"=== Forwarding Message to External API ===")
        logger.info(f"Endpoint: {EXTERNAL_ENDPOINT}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        logger.info(f"Headers: {json.dumps(headers, indent=2)}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:  # 10 second timeout
            logger.info(f"Making request to {EXTERNAL_ENDPOINT}")
            response = await client.post(EXTERNAL_ENDPOINT, json=payload, headers=headers)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response body: {response.text}")
            response.raise_for_status()
            logger.info(f"External API response: {response.status_code}")
            return True
    except httpx.ConnectError as e:
        logger.error(f"Connection error: {str(e)}")
        if retry_count < MAX_RETRIES:
            logger.warning(f"Retry {retry_count + 1}/{MAX_RETRIES} for message forwarding: Connection error")
            await asyncio.sleep(RETRY_DELAY * (retry_count + 1))  # Exponential backoff
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {MAX_RETRIES} retries: Connection error")
            return False
    except httpx.TimeoutException as e:
        logger.error(f"Timeout error: {str(e)}")
        if retry_count < MAX_RETRIES:
            logger.warning(f"Retry {retry_count + 1}/{MAX_RETRIES} for message forwarding: Timeout")
            await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {MAX_RETRIES} retries: Timeout")
            return False
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code}: {str(e)}")
        logger.error(f"Response body: {e.response.text}")
        if retry_count < MAX_RETRIES:
            logger.warning(f"Retry {retry_count + 1}/{MAX_RETRIES} for message forwarding: HTTP {e.response.status_code}")
            await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {MAX_RETRIES} retries: HTTP {e.response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if retry_count < MAX_RETRIES:
            logger.warning(f"Retry {retry_count + 1}/{MAX_RETRIES} for message forwarding: {str(e)}")
            await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {MAX_RETRIES} retries: {str(e)}")
            return False

@router.post("/receive")
async def receive_sms(request: Request) -> Response:
    """
    Receive incoming SMS messages and forward them securely.
    Includes caching and retry logic for external API failures.
    """
    resp = MessagingResponse()

    try:
        # Get the raw request body for Twilio validation
        body = await request.body()
        form_data = await request.form()
        
        # Log incoming request details
        logger.info("=== Incoming SMS/MMS Webhook Request ===")
        logger.info(f"Request URL: {request.url}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request headers: {dict(request.headers)}")
        logger.info(f"Request body: {body}")
        logger.info(f"Form data: {dict(form_data)}")
        
        # Validate Twilio webhook format
        validation = validate_twilio_message_format(dict(form_data))
        if not validation["is_valid"]:
            logger.error(f"Invalid Twilio webhook format: {validation['errors']}")
            return Response(content=str(resp), media_type="application/xml", status_code=400)
        
        if validation["warnings"]:
            for warning in validation["warnings"]:
                logger.warning(f"Webhook validation warning: {warning}")
        
        # Validate the request is from Twilio using API Key authentication
        # Skip validation in test mode
        if TEST_MODE:
            logger.info("=== TEST MODE: Skipping Twilio signature validation ===")
            is_valid = True
        else:
            if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
                logger.error("Missing Twilio API credentials")
                raise HTTPException(status_code=500, detail="Server configuration error")

            validator = RequestValidator(TWILIO_AUTH_TOKEN)  # Use API Secret for validation
            
            # Use the production URL for validation
            url = "https://www.dungeonmind.net/api/sms/receive"
            
            signature = request.headers.get("X-Twilio-Signature", "")
            
            # Get the form data as a dict for validation
            form_dict = dict(form_data)
            
            # Debug logging for validation
            logger.info("=== Twilio Validation Details ===")
            logger.info(f"URL for validation: {url}")
            logger.info(f"Received signature: {signature}")
            logger.info(f"Form data for validation: {form_dict}")
            logger.info(f"Auth token present: {bool(TWILIO_AUTH_TOKEN)}")
            logger.info(f"Auth token length: {len(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else 0}")
            
            # Calculate expected signature for debugging
            expected_signature = validator.compute_signature(url, form_dict)
            logger.info(f"Expected signature: {expected_signature}")
            logger.info(f"Signature match: {signature == expected_signature}")
            
            # Validate the request
            is_valid = validator.validate(url, form_dict, signature)
            logger.info(f"Validation result: {'Valid' if is_valid else 'Invalid'}")
            
            if not is_valid:
                logger.warning(f"Invalid Twilio signature for request from {request.client.host}")
                logger.warning(f"Validation failed with URL: {url}")
                return Response(content=str(resp), media_type="application/xml", status_code=403)

        message_body = form_data.get("Body", "")
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")
        message_sid = form_data.get("MessageSid", "")  # Twilio's unique message ID
        account_sid = form_data.get("AccountSid", "")
        api_version = form_data.get("ApiVersion", "")
        message_status = form_data.get("SmsStatus", form_data.get("MessageStatus", ""))  # Could be SmsStatus or MessageStatus
        
        # Validate Message SID format based on Twilio documentation
        # SMS messages start with SM, MMS messages start with MM
        is_mms_by_sid = message_sid.startswith("MM") if message_sid else False
        is_sms_by_sid = message_sid.startswith("SM") if message_sid else False
        
        # Extract MMS fields
        num_media = int(form_data.get("NumMedia", 0))
        media = []
        unsupported_media = []
        
        for i in range(num_media):
            media_url = form_data.get(f"MediaUrl{i}")
            media_type = form_data.get(f"MediaContentType{i}")
            if media_url:
                if validate_media_type(media_type):
                    media.append({
                        "url": media_url,
                        "content_type": media_type,
                        "index": i,
                        "supported": True
                    })
                else:
                    unsupported_media.append({
                        "url": media_url,
                        "content_type": media_type,
                        "index": i,
                        "supported": False
                    })
                    logger.warning(f"Unsupported media type: {media_type} for media {i}")
        
        # Include all media (supported and unsupported) in the final list
        all_media = media + unsupported_media
        
        # Determine message type using multiple indicators (more robust)
        has_media = num_media > 0
        
        # Validate consistency between NumMedia and MessageSid format
        if has_media and is_sms_by_sid:
            logger.warning(f"Inconsistency: NumMedia={num_media} but MessageSid starts with SM: {message_sid}")
        elif not has_media and is_mms_by_sid:
            logger.warning(f"Inconsistency: NumMedia=0 but MessageSid starts with MM: {message_sid}")
        
        # Primary determination by NumMedia, secondary by SID pattern
        if has_media or is_mms_by_sid:
            message_type = "MMS"
        else:
            message_type = "SMS"
        
        logger.info(f"=== Message Details ===")
        logger.info(f"MessageSid: {message_sid} (Type: {message_type})")
        logger.info(f"From: {from_number}")
        logger.info(f"To: {to_number}")
        logger.info(f"AccountSid: {account_sid}")
        logger.info(f"Status: {message_status}")
        logger.info(f"ApiVersion: {api_version}")
        logger.info(f"Body: {message_body}")
        logger.info(f"NumMedia: {num_media}")
        logger.info(f"Supported media items: {len(media)}")
        logger.info(f"Unsupported media items: {len(unsupported_media)}")
        if all_media:
            for media_item in all_media:
                status = "✓" if media_item['supported'] else "✗"
                logger.info(f"Media {media_item['index']} {status}: {media_item['content_type']} - {media_item['url']}")

        # Check cache first
        cached_response = get_cached_response(message_sid)
        if cached_response:
            logger.info(f"Using cached response for message {message_sid}")
            return Response(content=str(resp), media_type="application/xml")

        # Only check external API key and endpoint when forwarding
        if not EXTERNAL_ENDPOINT:
            logger.error("Missing EXTERNAL_SMS_ENDPOINT")
            return Response(content=str(resp), media_type="application/xml", status_code=500)

        # Build Twilio-compatible payload with all standard fields
        payload = {
            # Core message data
            "from": from_number,
            "to": to_number,
            "body": message_body,
            "message_sid": message_sid,
            "account_sid": account_sid,
            "api_version": api_version,
            "status": message_status,
            "direction": "inbound",  # Webhook messages are always inbound
            "timestamp": datetime.utcnow().isoformat(),
            
            # Message type and media info
            "message_type": message_type,
            "num_media": num_media,
            "media": all_media,
            
            # LibreChat specific fields
            "conversationId": "",
            
            # Enhanced metadata for processing
            "metadata": {
                "phoneNumber": from_number,
                "messageType": message_type,
                "mediaCount": num_media,
                "supportedMediaCount": len(media),
                "unsupportedMediaCount": len(unsupported_media),
                "twilioAccountSid": account_sid,
                "twilioApiVersion": api_version,
                "messageStatus": message_status
            },
            
            # Media subresource info (following Twilio pattern)
            "subresource_info": {
                "media_available": num_media > 0,
                "media_urls_expire": True,
                "note": "Media URLs expire after a few hours. Download immediately if needed."
            }
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {EXTERNAL_API_KEY}"
        }

        # Log the forwarding attempt
        logger.info(f"=== Forwarding Message ===")
        logger.info(f"Forwarding to: {EXTERNAL_ENDPOINT}")
        logger.info(f"Message Type: {message_type}")
        if all_media:
            logger.info(f"Total Media Items: {len(all_media)} (Supported: {len(media)}, Unsupported: {len(unsupported_media)})")
            for media_item in all_media:
                status = "✓" if media_item['supported'] else "✗"
                logger.info(f"  {status} {media_item['content_type']}: {media_item['url']}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        logger.info(f"Headers: {json.dumps(headers, indent=2)}")
        
        # Note: Twilio media URLs expire after a few hours
        # If long-term storage is needed, download immediately

        # Attempt to forward the message
        success = await forward_message(payload, headers)
        
        if success:
            # Cache successful response
            get_cached_response.cache_clear()  # Clear old cache entries
            get_cached_response(message_sid)
            logger.info(f"Successfully forwarded message {message_sid}")
            return Response(content=str(resp), media_type="application/xml")
        else:
            # Store failed message for later retry
            failed_messages[message_sid] = {
                "payload": payload,
                "headers": headers,
                "timestamp": datetime.utcnow(),
                "retry_count": 0
            }
            logger.warning(f"Failed to forward message {message_sid}, stored for retry")
            return Response(content=str(resp), media_type="application/xml", status_code=202)  # Accepted but not processed

    except HTTPException as he:
        logger.error(f"HTTP Exception: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error processing SMS: {str(e)}")
        return Response(content=str(resp), media_type="application/xml", status_code=500)

@router.get("/retry-failed")
async def retry_failed_messages() -> dict:
    """
    Endpoint to manually trigger retry of failed messages.
    This could be called by a scheduled task or manually.
    """
    retried = 0
    failed = 0
    current_time = datetime.utcnow()
    
    for message_sid, message_data in list(failed_messages.items()):
        # Skip messages older than 24 hours
        if current_time - message_data["timestamp"] > timedelta(hours=24):
            del failed_messages[message_sid]
            continue
            
        if message_data["retry_count"] >= MAX_RETRIES:
            failed += 1
            continue
            
        success = await forward_message(
            message_data["payload"],
            message_data["headers"],
            message_data["retry_count"]
        )
        
        if success:
            retried += 1
            del failed_messages[message_sid]
        else:
            message_data["retry_count"] += 1
            failed += 1
    
    return {
        "retried": retried,
        "failed": failed,
        "remaining": len(failed_messages)
    }

@router.get("/download-media")
async def download_media(media_url: str) -> dict:
    """
    Endpoint to download media from a Twilio URL.
    Useful for testing or if external services need to download media.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured")
    
    if not media_url.startswith("https://api.twilio.com/"):
        raise HTTPException(status_code=400, detail="Invalid Twilio media URL")
    
    try:
        media_content = await download_media_file(media_url, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        if media_content:
            return {
                "success": True,
                "size_bytes": len(media_content),
                "message": "Media downloaded successfully"
            }
        else:
            return {
                "success": False,
                "message": "Failed to download media"
            }
    except Exception as e:
        logger.error(f"Error in download_media endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@router.get("/supported-media-types")
async def get_supported_media_types() -> dict:
    """
    Endpoint to get the list of supported media types for MMS.
    """
    return {
        "supported_types": sorted(list(SUPPORTED_MEDIA_TYPES)),
        "count": len(SUPPORTED_MEDIA_TYPES)
    } 