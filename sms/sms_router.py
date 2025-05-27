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
EXTERNAL_ENDPOINT = os.getenv("EXTERNAL_SMS_ENDPOINT")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")  # API Key (username)
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")  # Changed from TWILIO_API_SECRET to TWILIO_AUTH_TOKEN
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# In-memory cache for failed messages
failed_messages = {}

@lru_cache(maxsize=100)
def get_cached_response(message_id: str) -> Optional[dict]:
    """Cache successful responses to avoid duplicate processing"""
    return None

async def forward_message(payload: dict, headers: dict, retry_count: int = 0) -> bool:
    """Forward message to external API with retry logic"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:  # 10 second timeout
            logger.info(f"Making request to {EXTERNAL_ENDPOINT}")
            response = await client.post(EXTERNAL_ENDPOINT, json=payload, headers=headers)
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
        
        # Validate the request is from Twilio using API Key authentication
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.error("Missing Twilio API credentials")
            raise HTTPException(status_code=500, detail="Server configuration error")

        validator = RequestValidator(TWILIO_AUTH_TOKEN)  # Use API Secret for validation
        url = str(request.url)
        signature = request.headers.get("X-Twilio-Signature", "")
        
        # Get the form data as a dict for validation
        form_dict = dict(form_data)
        
        # Validate the request
        if not validator.validate(url, form_dict, signature):
            logger.warning(f"Invalid Twilio signature for request from {request.client.host}")
            return Response(content=str(resp), media_type="application/xml", status_code=403)

        message_body = form_data.get("Body", "")
        from_number = form_data.get("From", "")
        message_sid = form_data.get("MessageSid", "")  # Twilio's unique message ID
        
        logger.info(f"Received SMS from {from_number}: {message_body}")

        if not EXTERNAL_API_KEY or not EXTERNAL_ENDPOINT:
            logger.error("Missing EXTERNAL_MESSAGE_API_KEY or EXTERNAL_SMS_ENDPOINT")
            return Response(content=str(resp), media_type="application/xml", status_code=500)

        # Check cache first
        cached_response = get_cached_response(message_sid)
        if cached_response:
            logger.info(f"Using cached response for message {message_sid}")
            return Response(content=str(resp), media_type="application/xml")

        payload = {
            "from": from_number,
            "body": message_body,
            "message_sid": message_sid,
            "timestamp": datetime.utcnow().isoformat()
        }
        headers = {
            "Authorization": f"Bearer {EXTERNAL_API_KEY}",
            "Content-Type": "application/json"
        }

        # Log the forwarding attempt
        logger.info(f"Attempting to forward message to {EXTERNAL_ENDPOINT}")
        logger.debug(f"Forwarding payload: {json.dumps(payload)}")

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