"""Typed domain/application errors for the statblock v1 contract."""

from __future__ import annotations

from typing import Any


class StatblockV1Error(Exception):
    """Base error with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")


class UnauthorizedInternalClientError(StatblockV1Error):
    """Caller failed internal service authentication."""

    def __init__(self, message: str = "Unauthorized internal client") -> None:
        super().__init__(code="unauthorized_internal_client", message=message)


class InternalServiceMisconfiguredError(StatblockV1Error):
    """Server-side configuration required for the route is missing."""

    def __init__(self, message: str = "Internal service is misconfigured") -> None:
        super().__init__(code="internal_service_misconfigured", message=message)
