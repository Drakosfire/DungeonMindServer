import httpx
from fastapi import HTTPException
import os
from dotenv import load_dotenv
import logging
from typing import Union
from fastapi import UploadFile
import io

from security_limits.image_validation import (
    MAX_UPLOAD_BYTES,
    read_upload_limited,
    validate_image_bytes,
)
from security_limits.download_limits import download_url_allowed, MAX_PROXY_BYTES

load_dotenv(dotenv_path='../.env')

cloudflare_account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
cloudflare_api_token = os.getenv('CLOUDFLARE_IMAGES_API_TOKEN')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def upload_image_to_cloudflare(image_input: Union[str, UploadFile]):
    logger.info("Uploading image to Cloudflare")
    
    # Validate credentials are set
    if not cloudflare_account_id:
        error_msg = "CLOUDFLARE_ACCOUNT_ID environment variable is not set"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    if not cloudflare_api_token:
        error_msg = "CLOUDFLARE_IMAGES_API_TOKEN environment variable is not set"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    
    url = f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1"
    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
    }
    
    # Check if input is a URL or UploadFile
    if isinstance(image_input, str):
        if not download_url_allowed(image_input):
            raise HTTPException(
                status_code=400,
                detail="Source image URL host is not allowlisted",
            )
        # Fetch with size/type caps before handing URL to Cloudflare
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            async with client.stream("GET", image_input) as upstream:
                upstream.raise_for_status()
                buf = bytearray()
                async for chunk in upstream.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_PROXY_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Source image exceeds maximum size of {MAX_PROXY_BYTES} bytes",
                        )
                mime = validate_image_bytes(bytes(buf), max_bytes=MAX_PROXY_BYTES)
        files = {
            'file': ("remote-image", bytes(buf), mime),
            'metadata': (None, '{"key":"value"}'),
            'requireSignedURLs': (None, 'false')
        }
    else:
        # Handle uploaded file — incremental read + magic sniff
        file_content, sniffed_mime = await read_upload_limited(image_input)
        filename = image_input.filename or "upload.bin"
        files = {
            'file': (filename, file_content, sniffed_mime),
            'metadata': (None, '{"key":"value"}'),
            'requireSignedURLs': (None, 'false')
        }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, files=files)
        
        if response.status_code != 200:
            error_text = response.text
            raise HTTPException(status_code=response.status_code, detail=f"Cloudflare API error: {error_text}")
        
        result = response.json()["result"]
        public_url = result.get("variants")[0]
        
        # Ensure URL ends with /Full (1024x1024 variant, case-sensitive)
        if not public_url.endswith('/Full'):
            public_url = '/'.join(public_url.split('/')[:-1]) + '/Full'
            
        logger.info("Image uploaded successfully to Cloudflare Images")
        return public_url
