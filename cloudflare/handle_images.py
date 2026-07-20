import httpx
from fastapi import HTTPException
import os
from dotenv import load_dotenv
import logging
from typing import Union, NamedTuple
from fastapi import UploadFile

from security_limits.image_validation import (
    read_upload_limited,
    validate_image_bytes,
)
from security_limits.download_limits import download_url_allowed, MAX_PROXY_BYTES

load_dotenv(dotenv_path="../.env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CloudflareUploadResult(NamedTuple):
    url: str
    provider_image_id: str
    account_id: str


def _cloudflare_credentials() -> tuple[str, str]:
    """Read credentials at call time (not only at import)."""
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID") or ""
    api_token = os.getenv("CLOUDFLARE_IMAGES_API_TOKEN") or ""
    return account_id, api_token


async def upload_image_to_cloudflare(
    image_input: Union[str, UploadFile],
) -> str:
    """
    Upload and return public URL (legacy callers).
    Prefer upload_image_to_cloudflare_detailed for asset registry.
    """
    detailed = await upload_image_to_cloudflare_detailed(image_input)
    return detailed.url


async def upload_image_to_cloudflare_detailed(
    image_input: Union[str, UploadFile],
) -> CloudflareUploadResult:
    """
    Validate client input first, then require Cloudflare config, then upload.

    Malformed uploads must return 400/413 even when credentials are missing
    (CI / misconfigured environments).
    """
    logger.info("Uploading image to Cloudflare")

    # 1) Normalize + validate input (independent of provider config)
    if isinstance(image_input, str):
        if not download_url_allowed(image_input):
            raise HTTPException(status_code=400, detail="Source image URL host is not allowlisted")
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
            "file": ("remote-image", bytes(buf), mime),
            "metadata": (None, '{"key":"value"}'),
            "requireSignedURLs": (None, "false"),
        }
    else:
        file_content, sniffed_mime = await read_upload_limited(image_input)
        filename = image_input.filename or "upload.bin"
        files = {
            "file": (filename, file_content, sniffed_mime),
            "metadata": (None, '{"key":"value"}'),
            "requireSignedURLs": (None, "false"),
        }

    # 2) Provider configuration (after client-input validation)
    cloudflare_account_id, cloudflare_api_token = _cloudflare_credentials()
    if not cloudflare_account_id:
        raise HTTPException(
            status_code=500,
            detail="CLOUDFLARE_ACCOUNT_ID environment variable is not set",
        )
    if not cloudflare_api_token:
        raise HTTPException(
            status_code=500,
            detail="CLOUDFLARE_IMAGES_API_TOKEN environment variable is not set",
        )

    # 3) Call Cloudflare
    url = f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1"
    headers = {"Authorization": f"Bearer {cloudflare_api_token}"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, files=files)

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cloudflare API error: {response.text}",
            )

        result = response.json()["result"]
        provider_image_id = result.get("id") or ""
        public_url = result.get("variants")[0]

        if not public_url.endswith("/Full"):
            public_url = "/".join(public_url.split("/")[:-1]) + "/Full"

        logger.info("Image uploaded successfully to Cloudflare Images")
        return CloudflareUploadResult(
            url=public_url,
            provider_image_id=provider_image_id,
            account_id=cloudflare_account_id or "",
        )


async def delete_cloudflare_image_by_id(provider_image_id: str) -> bool:
    """Delete by trusted Cloudflare Images id from the asset registry."""
    cloudflare_account_id, cloudflare_api_token = _cloudflare_credentials()
    if not cloudflare_account_id or not cloudflare_api_token:
        raise HTTPException(status_code=500, detail="Image storage not configured")
    if not provider_image_id:
        return False
    delete_url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{cloudflare_account_id}/images/v1/{provider_image_id}"
    )
    headers = {"Authorization": f"Bearer {cloudflare_api_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(delete_url, headers=headers)
        data = resp.json()
        return bool(data.get("success"))
