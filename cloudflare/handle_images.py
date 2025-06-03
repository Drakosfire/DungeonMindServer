import httpx
from fastapi import HTTPException
import os
from dotenv import load_dotenv
import logging

load_dotenv(dotenv_path='../.env')

cloudflare_account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
cloudflare_api_token = os.getenv('CLOUDFLARE_IMAGES_API_TOKEN')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def upload_image_to_cloudflare(image_url: str):
    logger.info("Uploading image to Cloudflare: %s", image_url)
    url = f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1"
    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
    }
    
    # Use 'files' to send multipart form data
    files = {
        'url': (None, image_url),
        'metadata': (None, '{"key":"value"}'),  # Example metadata
        'requireSignedURLs': (None, 'false')
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, files=files)
        
        if response.status_code != 200:
            error_text = response.text
            raise HTTPException(status_code=response.status_code, detail=f"Cloudflare API error: {error_text}")
        print("response.json():", response.json())
        print("response.json()['result']['variants'][0]:", response.json()["result"]["variants"][0])
        variant_url = response.json()["result"]["variants"][0]
        
        return variant_url