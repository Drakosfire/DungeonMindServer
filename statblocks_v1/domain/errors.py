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


class CandidateNotFoundError(StatblockV1Error):
    def __init__(self, candidate_id: str) -> None:
        super().__init__("candidate_not_found", "Candidate was not found", {"candidate_id": candidate_id})


class CandidateExpiredError(StatblockV1Error):
    def __init__(self, candidate_id: str) -> None:
        super().__init__("candidate_expired", "Candidate has expired", {"candidate_id": candidate_id})


class CandidateMissingBeforeExpiryError(StatblockV1Error):
    """Completed operation points to a candidate missing before its declared expiry."""

    def __init__(self, candidate_id: str) -> None:
        super().__init__(
            "candidate_missing_before_expiry",
            "Completed generation points to a candidate missing before its declared expiry",
            {"candidate_id": candidate_id},
        )


class GenerateOperationIntegrityError(StatblockV1Error):
    """Generate-operation document failed key/state/binding integrity checks."""

    def __init__(
        self,
        request_id: str,
        *,
        candidate_id: str | None = None,
        reason: str = "Generate operation record failed integrity checks",
    ) -> None:
        details: dict[str, Any] = {"request_id": request_id}
        if candidate_id is not None:
            details["candidate_id"] = candidate_id
        super().__init__(
            "generate_operation_integrity",
            reason,
            details,
        )


class StatblockNotFoundError(StatblockV1Error):
    def __init__(self, statblock_id: str) -> None:
        super().__init__("statblock_not_found", "Statblock was not found", {"statblock_id": statblock_id})


class RevisionNotFoundError(StatblockV1Error):
    def __init__(self, revision_id: str) -> None:
        super().__init__("revision_not_found", "Revision was not found", {"revision_id": revision_id})


class ParentRevisionMismatchError(StatblockV1Error):
    def __init__(self, statblock_id: str, revision_id: str) -> None:
        super().__init__(
            "parent_revision_mismatch",
            "Parent revision does not belong to this statblock",
            {"statblock_id": statblock_id, "revision_id": revision_id},
        )


class StaleParentRevisionError(StatblockV1Error):
    def __init__(
        self, statblock_id: str, parent_revision_id: str, latest_revision_id: str
    ) -> None:
        super().__init__(
            "stale_parent_revision",
            "Parent revision is not the current latest revision",
            {
                "statblock_id": statblock_id,
                "parent_revision_id": parent_revision_id,
                "latest_revision_id": latest_revision_id,
            },
        )


class ImmutableResourceConflictError(StatblockV1Error):
    def __init__(self, resource_type: str, resource_id: str) -> None:
        super().__init__(
            "immutable_resource_conflict",
            f"{resource_type} IDs are server-owned and immutable",
            {"resource_type": resource_type, "resource_id": resource_id},
        )


class ImmutableRevisionConflictError(ImmutableResourceConflictError):
    def __init__(self, revision_id: str) -> None:
        StatblockV1Error.__init__(
            self,
            "immutable_revision_conflict",
            "Revision IDs are server-owned and immutable",
            {"revision_id": revision_id},
        )


class IdempotencyConflictError(StatblockV1Error):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            "idempotency_conflict",
            "Idempotency key was reused with a different request",
            {"idempotency_key": idempotency_key},
        )


class AmbiguousRequestPayloadError(StatblockV1Error):
    def __init__(self, key: str) -> None:
        super().__init__(
            "ambiguous_request_payload",
            "Request map keys collide after Unicode NFC normalization",
            {"key": key},
        )


class PersistenceValidationError(StatblockV1Error):
    def __init__(self, receipt: Any | None = None) -> None:
        details = None
        if receipt is not None:
            details = {
                "validation_receipt": receipt.model_dump(mode="json"),
                "is_persistence_ready": receipt.is_persistence_ready,
            }
        super().__init__(
            "validation_failed",
            "Definition is not persistence-ready",
            details,
        )


class PersistenceUnavailableError(StatblockV1Error):
    def __init__(self) -> None:
        super().__init__("persistence_unavailable", "Persistence is unavailable")


class TransactionIndeterminateError(StatblockV1Error):
    def __init__(self) -> None:
        super().__init__(
            "transaction_indeterminate",
            "Transaction outcome is indeterminate and requires reconciliation",
        )
