"""Typed HTTP error transport for the v1 router.

Auth and other foundation failures raise ``StatblockV1HTTPError``. An app-level
exception handler converts those into a top-level ``ErrorEnvelopeV1`` JSON body
so FastAPI never wraps the envelope under ``{"detail": ...}``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from statblocks_v1.api.models import ErrorDetailV1, ErrorEnvelopeV1
from statblocks_v1.domain.errors import StatblockV1Error


class StatblockV1HTTPError(Exception):
    """Domain error paired with the HTTP status code to emit."""

    def __init__(self, status_code: int, error: StatblockV1Error) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(f"{status_code} {error.code}: {error.message}")


def envelope_for(error: StatblockV1Error) -> dict[str, object]:
    return ErrorEnvelopeV1(
        error=ErrorDetailV1(
            code=error.code,
            message=error.message,
            details=error.details,
        )
    ).model_dump(mode="json", exclude_none=True)


def register_error_handlers(app: FastAPI) -> None:
    """Install handlers that emit the top-level v1 error envelope."""

    @app.exception_handler(StatblockV1HTTPError)
    async def handle_statblock_v1_http_error(
        _request: Request,
        exc: StatblockV1HTTPError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=envelope_for(exc.error))

    @app.exception_handler(StatblockV1Error)
    async def handle_statblock_v1_error(
        _request: Request,
        exc: StatblockV1Error,
    ) -> JSONResponse:
        # Bare domain errors default to 500; auth uses StatblockV1HTTPError for status.
        return JSONResponse(status_code=500, content=envelope_for(exc))
