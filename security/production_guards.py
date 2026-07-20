"""Startup guards that must fail closed in production."""

from __future__ import annotations

import os


def assert_safe_production_config() -> None:
    """
    Refuse to start when production env would disable critical controls.

    Raises:
        RuntimeError: if ENVIRONMENT=production and TWILIO_TEST_MODE=true
    """
    environment = os.environ.get("ENVIRONMENT", "development")
    twilio_test_mode = os.getenv("TWILIO_TEST_MODE", "false").lower() == "true"
    if environment == "production" and twilio_test_mode:
        raise RuntimeError(
            "Refusing to start: TWILIO_TEST_MODE=true is forbidden when "
            "ENVIRONMENT=production"
        )
