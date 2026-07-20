"""
Input size caps for demo and paid generation endpoints.
"""

from __future__ import annotations

from fastapi import HTTPException

MAX_PROMPT_CHARS = 4000
MAX_DESCRIPTION_CHARS = 8000
MAX_CHAT_HISTORY_MESSAGES = 40
MAX_CHAT_MESSAGE_CHARS = 4000
MAX_IMAGES_PER_REQUEST = 8


def enforce_max_chars(value: str, *, field: str, limit: int) -> None:
    if value is None:
        return
    if len(value) > limit:
        raise HTTPException(
            status_code=422,
            detail=f"{field} exceeds maximum length of {limit} characters",
        )


def clamp_num_images(num: int) -> int:
    if num < 1:
        raise HTTPException(status_code=422, detail="numImages must be >= 1")
    if num > MAX_IMAGES_PER_REQUEST:
        raise HTTPException(
            status_code=422,
            detail=f"numImages cannot exceed {MAX_IMAGES_PER_REQUEST}",
        )
    return num
