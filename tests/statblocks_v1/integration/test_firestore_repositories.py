"""Firestore emulator coverage; skipped unless FIRESTORE_EMULATOR_HOST is set."""
import os

import pytest

pytestmark = pytest.mark.firestore_emulator


@pytest.fixture
def firestore_client():
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("Firestore emulator is not configured")
    from google.cloud import firestore
    return firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "statblocks-v1-test"))


def test_v1_collection_layout_is_isolated(firestore_client):
    from statblocks_v1.infrastructure.firestore_repositories import (
        CANDIDATES_COLLECTION, IDEMPOTENCY_COLLECTION, STATBLOCKS_COLLECTION,
    )
    assert (CANDIDATES_COLLECTION, STATBLOCKS_COLLECTION, IDEMPOTENCY_COLLECTION) == (
        "dungeonbuddy_statblock_candidates_v1",
        "dungeonbuddy_statblocks_v1",
        "dungeonbuddy_statblock_idempotency_v1",
    )
