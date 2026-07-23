"""Validated, secret-safe runtime configuration for the statblock v1 boundary."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

from statblocks_v1.application.settings import _policy_model
from statblocks_v1.domain.errors import InternalServiceMisconfiguredError


class ConfigurationError(ValueError):
    """A readiness-safe configuration error; never include environment values."""


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value


def _positive_int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a number") from error
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean")


@dataclass(frozen=True)
class StatblocksV1Settings:
    internal_api_key: str
    openai_api_key: str | None
    model: str
    provider_timeout_seconds: float
    provider_max_retries: int
    candidate_ttl_seconds: int
    firestore_enabled: bool
    firestore_namespace: str
    candidates_collection: str
    statblocks_collection: str
    idempotency_collection: str
    generate_ops_collection: str
    generate_lease_seconds: int
    asset_gateway_enabled: bool
    asset_timeout_seconds: float
    feature_enabled: bool
    allow_reads_when_disabled: bool
    structured_logging: bool
    log_level: str

    @classmethod
    def from_environment(cls, *, require_generation: bool = False) -> "StatblocksV1Settings":
        namespace = os.getenv("STATBLOCKS_V1_FIRESTORE_NAMESPACE", "dungeonbuddy_statblocks_v1").strip()
        if not namespace.replace("_", "").replace("-", "").isalnum():
            raise ConfigurationError("STATBLOCKS_V1_FIRESTORE_NAMESPACE contains invalid characters")
        feature_enabled = _boolean("STATBLOCKS_V1_FEATURE_ENABLED", True)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if require_generation and feature_enabled and not openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is required when generation is enabled")
        configured_model = os.getenv("STATBLOCKS_V1_OPENAI_MODEL")
        try:
            model = configured_model if configured_model else _policy_model()
        except InternalServiceMisconfiguredError as error:
            raise ConfigurationError("structured generation model is not configured") from error
        provider_timeout_seconds = _positive_float("STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS", 45)
        provider_max_retries = _positive_int("STATBLOCKS_V1_OPENAI_MAX_RETRIES", 1)
        asset_timeout_seconds = _positive_float("STATBLOCKS_V1_ASSET_TIMEOUT_SECONDS", 20)
        # Lease must cover provider retries, post-provider asset work, and margin.
        # Ceil so fractional timeouts cannot shrink the budget via truncation.
        provider_retry_budget_seconds = math.ceil(
            provider_timeout_seconds * (provider_max_retries + 1)
            + asset_timeout_seconds
            + 30
        )
        default_lease = max(120, provider_retry_budget_seconds)
        generate_lease_seconds = _positive_int(
            "STATBLOCKS_V1_GENERATE_LEASE_SECONDS",
            default_lease,
            minimum=1,
        )
        if generate_lease_seconds < provider_retry_budget_seconds:
            raise ConfigurationError(
                "STATBLOCKS_V1_GENERATE_LEASE_SECONDS must cover the full provider "
                "retry budget plus asset generation timeout "
                "(timeout × (retries+1) + asset_timeout + margin)"
            )
        return cls(
            internal_api_key=_required("DUNGEONBUDDY_INTERNAL_API_KEY"),
            openai_api_key=openai_api_key,
            model=model,
            provider_timeout_seconds=provider_timeout_seconds,
            provider_max_retries=provider_max_retries,
            candidate_ttl_seconds=_positive_int("STATBLOCKS_V1_CANDIDATE_TTL_SECONDS", 86400, minimum=1),
            firestore_enabled=_boolean("STATBLOCKS_V1_FIRESTORE_ENABLED", True),
            firestore_namespace=namespace,
            candidates_collection=os.getenv("STATBLOCKS_V1_CANDIDATES_COLLECTION", "dungeonbuddy_statblock_candidates_v1"),
            statblocks_collection=os.getenv("STATBLOCKS_V1_STATBLOCKS_COLLECTION", "dungeonbuddy_statblocks_v1"),
            idempotency_collection=os.getenv("STATBLOCKS_V1_IDEMPOTENCY_COLLECTION", "dungeonbuddy_statblock_idempotency_v1"),
            generate_ops_collection=os.getenv(
                "STATBLOCKS_V1_GENERATE_OPS_COLLECTION",
                "dungeonbuddy_statblock_candidate_generate_ops_v1",
            ),
            generate_lease_seconds=generate_lease_seconds,
            asset_gateway_enabled=_boolean("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", False),
            asset_timeout_seconds=asset_timeout_seconds,
            feature_enabled=feature_enabled,
            allow_reads_when_disabled=_boolean("STATBLOCKS_V1_ALLOW_READS_WHEN_DISABLED", True),
            structured_logging=_boolean("STATBLOCKS_V1_STRUCTURED_LOGGING", True),
            log_level=os.getenv("STATBLOCKS_V1_LOG_LEVEL", "INFO").upper(),
        )

    def readiness_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.firestore_enabled:
            errors.append("firestore_disabled")
        if self.feature_enabled and not self.openai_api_key:
            errors.append("openai_not_configured")
        return errors
