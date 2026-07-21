"""
Server-controlled image asset registry.

Opaque asset IDs authorize deletion. User-supplied URLs and mutable project
references must never authorize cloud deletes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

IMAGE_ASSETS_COLLECTION = "image_assets"


def cloudflare_image_id_from_url(url: str) -> str:
    """
    Extract Cloudflare Images id from imagedelivery.net URL.
    Path form: /{account_hash}/{image_id}/{variant}
    """
    if not url:
        return ""
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return parts[1]
    return ""


@dataclass
class ImageAssetRecord:
    asset_id: str
    owner_id: str
    provider: str  # cloudflare_images | r2
    object_key: str  # CF Images id or R2 object key
    canonical_url: str
    account_or_bucket: str
    created_at: str
    service: str = ""


def _db():
    from firestore.firebase_config import db

    return db


def register_image_asset(
    *,
    owner_id: str,
    provider: str,
    object_key: str,
    canonical_url: str,
    account_or_bucket: str = "",
    service: str = "",
    asset_id: Optional[str] = None,
) -> ImageAssetRecord:
    """Persist a trusted asset record owned by the authenticated user."""
    aid = asset_id or str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    record = ImageAssetRecord(
        asset_id=aid,
        owner_id=owner_id,
        provider=provider,
        object_key=object_key,
        canonical_url=canonical_url,
        account_or_bucket=account_or_bucket,
        created_at=created_at,
        service=service,
    )
    payload = {
        "asset_id": record.asset_id,
        "owner_id": record.owner_id,
        "provider": record.provider,
        "object_key": record.object_key,
        "canonical_url": record.canonical_url,
        "account_or_bucket": record.account_or_bucket,
        "created_at": record.created_at,
        "service": record.service,
    }
    _db().collection(IMAGE_ASSETS_COLLECTION).document(aid).set(payload)
    logger.info(
        "Registered image asset_id=%s owner=%s provider=%s",
        aid,
        owner_id,
        provider,
    )
    return record


def get_asset_for_owner(asset_id: str, owner_id: str) -> Optional[ImageAssetRecord]:
    """Return the asset only if it exists and is owned by owner_id."""
    doc = _db().collection(IMAGE_ASSETS_COLLECTION).document(asset_id).get()
    if not doc.exists:
        return None
    data: dict[str, Any] = doc.to_dict() or {}
    if data.get("owner_id") != owner_id:
        return None
    return ImageAssetRecord(
        asset_id=data.get("asset_id", asset_id),
        owner_id=data["owner_id"],
        provider=data.get("provider", ""),
        object_key=data.get("object_key", ""),
        canonical_url=data.get("canonical_url", ""),
        account_or_bucket=data.get("account_or_bucket", ""),
        created_at=data.get("created_at", ""),
        service=data.get("service", ""),
    )


def delete_asset_record(asset_id: str) -> None:
    _db().collection(IMAGE_ASSETS_COLLECTION).document(asset_id).delete()


def get_owned_asset_by_url(owner_id: str, url: str) -> Optional[ImageAssetRecord]:
    """Return the owner's registry row for this canonical URL, if any."""
    if not url:
        return None
    query = (
        _db()
        .collection(IMAGE_ASSETS_COLLECTION)
        .where("owner_id", "==", owner_id)
        .where("canonical_url", "==", url)
        .limit(1)
    )
    for doc in query.stream():
        data: dict[str, Any] = doc.to_dict() or {}
        return ImageAssetRecord(
            asset_id=data.get("asset_id", doc.id),
            owner_id=data["owner_id"],
            provider=data.get("provider", ""),
            object_key=data.get("object_key", ""),
            canonical_url=data.get("canonical_url", ""),
            account_or_bucket=data.get("account_or_bucket", ""),
            created_at=data.get("created_at", ""),
            service=data.get("service", ""),
        )
    return None


def owner_has_asset_url(owner_id: str, url: str) -> bool:
    """
    True only if a registry row for this owner already holds this URL.
    Used to reject forging foreign CDN URLs into map projects.
    """
    if not url:
        return True  # empty allowed
    return get_owned_asset_by_url(owner_id, url) is not None


def register_cloudflare_url_asset(
    *,
    owner_id: str,
    canonical_url: str,
    provider_image_id: str = "",
    account_or_bucket: str = "",
    service: str = "",
) -> ImageAssetRecord:
    """Register a Cloudflare Images URL (GenerationEngine / upload producers)."""
    object_key = provider_image_id or cloudflare_image_id_from_url(canonical_url)
    return register_image_asset(
        owner_id=owner_id,
        provider="cloudflare_images",
        object_key=object_key,
        canonical_url=canonical_url,
        account_or_bucket=account_or_bucket,
        service=service,
    )
