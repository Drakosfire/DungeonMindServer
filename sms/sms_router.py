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

# Configuration Management
class SMSConfig:
    """Centralized configuration management for SMS router"""
    
    def __init__(self):
        # External API Configuration
        self.external_api_key = os.getenv("EXTERNAL_MESSAGE_API_KEY")
        self.external_endpoint = os.getenv("EXTERNAL_SMS_ENDPOINT")
        
        # Twilio Configuration
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.test_mode = os.getenv("TWILIO_TEST_MODE", "false").lower() == "true"
        
        # Webhook Configuration
        self.webhook_url = os.getenv("TWILIO_WEBHOOK_URL", "https://www.dungeonmind.net/api/sms/receive")
        
        # Retry Configuration
        self.max_retries = int(os.getenv("SMS_MAX_RETRIES", "3"))
        self.retry_delay = int(os.getenv("SMS_RETRY_DELAY", "1"))
        
        # Timeout Configuration
        self.request_timeout = int(os.getenv("SMS_REQUEST_TIMEOUT", "10"))
        
        # Validation
        self._validate_config()
    
    def _validate_config(self):
        """Validate required configuration"""
        errors = []
        
        if not self.external_api_key:
            errors.append("EXTERNAL_MESSAGE_API_KEY is required")
        
        if not self.external_endpoint:
            errors.append("EXTERNAL_SMS_ENDPOINT is required")
        
        if not self.test_mode:
            if not self.twilio_account_sid:
                errors.append("TWILIO_ACCOUNT_SID is required when not in test mode")
            if not self.twilio_auth_token:
                errors.append("TWILIO_AUTH_TOKEN is required when not in test mode")
        
        if errors:
            raise ValueError(f"SMS Configuration errors: {'; '.join(errors)}")
    
    def log_config(self):
        """Log configuration (without sensitive data)"""
        logger.info("=== SMS Router Configuration ===")
        logger.info(f"External Endpoint: {self.external_endpoint}")
        logger.info(f"Webhook URL: {self.webhook_url}")
        logger.info(f"Test Mode: {self.test_mode}")
        logger.info(f"Max Retries: {self.max_retries}")
        logger.info(f"Request Timeout: {self.request_timeout}s")
        logger.info(f"External API Key: {'*' * len(self.external_api_key) if self.external_api_key else 'None'}")
        logger.info(f"Twilio Account SID: {'*' * len(self.twilio_account_sid) if self.twilio_account_sid else 'None'}")
        logger.info(f"Twilio Auth Token: {'*' * len(self.twilio_auth_token) if self.twilio_auth_token else 'None'}")

# Initialize configuration
try:
    config = SMSConfig()
    config.log_config()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    raise

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
        logger.info(f"Endpoint: {config.external_endpoint}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        logger.info(f"Headers: {json.dumps({k: v for k, v in headers.items() if k.lower() != 'authorization'}, indent=2)}")
        
        async with httpx.AsyncClient(timeout=config.request_timeout) as client:
            logger.info(f"Making request to {config.external_endpoint}")
            response = await client.post(config.external_endpoint, json=payload, headers=headers)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response body: {response.text}")
            response.raise_for_status()
            logger.info(f"External API response: {response.status_code}")
            return True
    except httpx.ConnectError as e:
        logger.error(f"Connection error: {str(e)}")
        if retry_count < config.max_retries:
            logger.warning(f"Retry {retry_count + 1}/{config.max_retries} for message forwarding: Connection error")
            await asyncio.sleep(config.retry_delay * (retry_count + 1))  # Exponential backoff
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {config.max_retries} retries: Connection error")
            return False
    except httpx.TimeoutException as e:
        logger.error(f"Timeout error: {str(e)}")
        if retry_count < config.max_retries:
            logger.warning(f"Retry {retry_count + 1}/{config.max_retries} for message forwarding: Timeout")
            await asyncio.sleep(config.retry_delay * (retry_count + 1))
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {config.max_retries} retries: Timeout")
            return False
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code}: {str(e)}")
        logger.error(f"Response body: {e.response.text}")
        if retry_count < config.max_retries:
            logger.warning(f"Retry {retry_count + 1}/{config.max_retries} for message forwarding: HTTP {e.response.status_code}")
            await asyncio.sleep(config.retry_delay * (retry_count + 1))
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {config.max_retries} retries: HTTP {e.response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if retry_count < config.max_retries:
            logger.warning(f"Retry {retry_count + 1}/{config.max_retries} for message forwarding: {str(e)}")
            await asyncio.sleep(config.retry_delay * (retry_count + 1))
            return await forward_message(payload, headers, retry_count + 1)
        else:
            logger.error(f"Failed to forward message after {config.max_retries} retries: {str(e)}")
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
        if config.test_mode:
            logger.info("=== TEST MODE: Skipping Twilio signature validation ===")
            is_valid = True
        else:
            if not config.twilio_account_sid or not config.twilio_auth_token:
                logger.error("Missing Twilio API credentials")
                raise HTTPException(status_code=500, detail="Server configuration error")

            validator = RequestValidator(config.twilio_auth_token)  # Use API Secret for validation
            
            # Use configured webhook URL for validation
            url = config.webhook_url
            
            signature = request.headers.get("X-Twilio-Signature", "")
            
            # Get the form data as a dict for validation
            form_dict = dict(form_data)
            
            # Debug logging for validation
            logger.info("=== Twilio Validation Details ===")
            logger.info(f"URL for validation: {url}")
            logger.info(f"Received signature: {signature}")
            logger.info(f"Form data for validation: {form_dict}")
            logger.info(f"Auth token present: {bool(config.twilio_auth_token)}")
            logger.info(f"Auth token length: {len(config.twilio_auth_token) if config.twilio_auth_token else 0}")
            
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
            "Authorization": f"Bearer {config.external_api_key}"
        }

        # Log the forwarding attempt
        logger.info(f"=== Forwarding Message ===")
        logger.info(f"Forwarding to: {config.external_endpoint}")
        logger.info(f"Message Type: {message_type}")
        if all_media:
            logger.info(f"Total Media Items: {len(all_media)} (Supported: {len(media)}, Unsupported: {len(unsupported_media)})")
            for media_item in all_media:
                status = "✓" if media_item['supported'] else "✗"
                logger.info(f"  {status} {media_item['content_type']}: {media_item['url']}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        logger.info(f"Headers: {json.dumps({k: v for k, v in headers.items() if k.lower() != 'authorization'}, indent=2)}")
        
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
            
        if message_data["retry_count"] >= config.max_retries:
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
    if not config.twilio_account_sid or not config.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured")
    
    if not media_url.startswith("https://api.twilio.com/"):
        raise HTTPException(status_code=400, detail="Invalid Twilio media URL")
    
    try:
        media_content = await download_media_file(media_url, config.twilio_account_sid, config.twilio_auth_token)
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