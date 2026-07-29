"""Typed HTTP error transport for the v1 router.

Auth and application failures raise ``StatblockV1HTTPError``. App-level handlers
convert those into a top-level ``ErrorEnvelopeV1`` JSON body so FastAPI never
wraps the envelope under ``{"detail": ...}``.

Request-validation handling is path-scoped: only
``/api/internal/dungeonbuddy/v1`` receives the v1 envelope. Legacy routes keep
FastAPI's default ``{"detail": ...}`` shape.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from statblocks_v1.api.models import ErrorDetailV1, ErrorEnvelopeV1
from statblocks_v1.application.generation import GenerationFailureV1
from statblocks_v1.domain.errors import (
    AmbiguousRequestPayloadError,
    CandidateExpiredError,
    CandidateMissingBeforeExpiryError,
    CandidateNotFoundError,
    GenerateOperationIntegrityError,
    ReviseOperationIntegrityError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    InternalServiceMisconfiguredError,
    ParentRevisionMismatchError,
    PersistenceUnavailableError,
    PersistenceValidationError,
    RevisionNotFoundError,
    StaleParentRevisionError,
    StatblockNotFoundError,
    StatblockV1Error,
    TransactionIndeterminateError,
    UnauthorizedInternalClientError,
)

V1_PATH_PREFIX = "/api/internal/dungeonbuddy/v1"

_DOMAIN_STATUS: dict[type[StatblockV1Error], int] = {
    UnauthorizedInternalClientError: 401,
    InternalServiceMisconfiguredError: 503,
    CandidateNotFoundError: 404,
    CandidateExpiredError: 410,
    CandidateMissingBeforeExpiryError: 500,
    GenerateOperationIntegrityError: 500,
    ReviseOperationIntegrityError: 500,
    StatblockNotFoundError: 404,
    RevisionNotFoundError: 404,
    IdempotencyConflictError: 409,
    ParentRevisionMismatchError: 409,
    StaleParentRevisionError: 409,
    ImmutableResourceConflictError: 409,
    ImmutableRevisionConflictError: 409,
    AmbiguousRequestPayloadError: 422,
    PersistenceValidationError: 422,
    PersistenceUnavailableError: 503,
    TransactionIndeterminateError: 503,
}

# Final PR16 GenerationFailureV1.kind → (status, public code, message)
_GENERATION_FAILURE_POLICY: dict[str, tuple[int, str, str]] = {
    "provider_refusal": (422, "provider_refused", "Provider refused the request"),
    "provider_incomplete": (422, "provider_incomplete", "Provider returned incomplete output"),
    "provider_timeout": (504, "provider_timeout", "Provider timed out"),
    "provider_rate_limit": (429, "rate_limited", "Provider rate limit reached"),
    "provider_failure": (503, "provider_unavailable", "Provider is unavailable"),
    "definition_invalid": (422, "validation_failed", "Generated definition failed validation"),
    "ruleset_mismatch": (422, "ruleset_mismatch", "Generated definition ruleset does not match the request"),
    "source_digest_mismatch": (
        422,
        "source_digest_mismatch",
        "Caller-supplied source description digest does not match the description",
    ),
    "invalid_request": (422, "invalid_request", "Revision request is invalid"),
    "source_unavailable": (503, "source_unavailable", "Revision source is unavailable"),
    "persistence_unavailable": (
        503,
        "persistence_unavailable",
        "Persistence is unavailable",
    ),
    "revision_not_found": (404, "revision_not_found", "Revision was not found"),
    "statblock_not_found": (404, "statblock_not_found", "Statblock was not found"),
    "generation_in_progress": (
        409,
        "generation_in_progress",
        "Candidate generation is already in progress for this request",
    ),
    "generation_replay_expired": (
        410,
        "generation_replay_expired",
        "Completed generation points to an expired candidate",
    ),
}


class StatblockV1HTTPError(Exception):
    """Domain error paired with the HTTP status code to emit."""

    def __init__(self, status_code: int, error: StatblockV1Error) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(f"{status_code} {error.code}: {error.message}")


class GenerationTransportError(StatblockV1Error):
    """Stable transport code for a mapped generation/revision failure."""


def envelope_for(error: StatblockV1Error) -> dict[str, object]:
    return ErrorEnvelopeV1(
        error=ErrorDetailV1(
            code=error.code,
            message=error.message,
            details=error.details,
        )
    ).model_dump(mode="json", exclude_none=True)


def status_for_domain_error(error: StatblockV1Error) -> int:
    return _DOMAIN_STATUS.get(type(error), 500)


def raise_for_generation_failure(failure: GenerationFailureV1) -> None:
    """Map a final PR16 failure kind to a typed HTTP error; unknown kinds fail closed."""

    status, code, message = _GENERATION_FAILURE_POLICY.get(
        failure.kind,
        (500, "generation_failed", "Generation failed with an unexpected outcome"),
    )
    details: dict[str, object] | None = None
    if failure.diagnostics is not None:
        details = failure.diagnostics.model_dump(mode="json", exclude_none=True)
    raise StatblockV1HTTPError(
        status,
        GenerationTransportError(code, message, details=details),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install handlers that emit the top-level v1 error envelope where appropriate."""

    @app.exception_handler(StatblockV1HTTPError)
    async def handle_statblock_v1_http_error(
        request: Request,
        exc: StatblockV1HTTPError,
    ) -> JSONResponse:
        try:
            from statblocks_v1.observability import bind_outcome

            bind_outcome(request, exc.error.code)
        except Exception:
            pass
        return JSONResponse(status_code=exc.status_code, content=envelope_for(exc.error))

    @app.exception_handler(StatblockV1Error)
    async def handle_statblock_v1_error(
        request: Request,
        exc: StatblockV1Error,
    ) -> JSONResponse:
        try:
            from statblocks_v1.observability import bind_outcome

            bind_outcome(request, exc.code)
        except Exception:
            pass
        return JSONResponse(
            status_code=status_for_domain_error(exc),
            content=envelope_for(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # Preserve FastAPI's default envelope for every non-v1 route.
        if not request.url.path.startswith(V1_PATH_PREFIX):
            return JSONResponse(
                status_code=422,
                content={"detail": jsonable_encoder(exc.errors())},
            )
        try:
            from statblocks_v1.observability import bind_outcome

            bind_outcome(request, "invalid_request")
        except Exception:
            pass
        return JSONResponse(
            status_code=422,
            content=ErrorEnvelopeV1(
                error=ErrorDetailV1(
                    code="invalid_request",
                    message="Request validation failed",
                    details={"fields": jsonable_encoder(exc.errors())},
                )
            ).model_dump(mode="json", exclude_none=True),
        )
