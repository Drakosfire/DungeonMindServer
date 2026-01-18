from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from ruleslawyer.constants import (
    DEFAULT_RULESLAWYER_INGESTION_COLLECTION,
    DEFAULT_RULESLAWYER_RULEBOOKS_COLLECTION,
    RULESLAWYER_INGESTION_COLLECTION_ENV,
    RULESLAWYER_RULEBOOKS_COLLECTION_ENV,
)


class RulesLawyerRegistry:
    def __init__(self, db):
        rulebooks_collection = os.environ.get(
            RULESLAWYER_RULEBOOKS_COLLECTION_ENV,
            DEFAULT_RULESLAWYER_RULEBOOKS_COLLECTION,
        )
        ingestion_collection = os.environ.get(
            RULESLAWYER_INGESTION_COLLECTION_ENV,
            DEFAULT_RULESLAWYER_INGESTION_COLLECTION,
        )

        self._rulebooks = db[rulebooks_collection]
        self._ingestion = db[ingestion_collection]

    def list_rulebooks(self) -> List[Dict[str, Any]]:
        return list(self._rulebooks.find({}, {"_id": 0}))

    def refresh_rulebooks(self, rulebook_ids: List[str], reason: Optional[str] = None) -> Dict[str, Any]:
        now = datetime.utcnow()
        payload = {
            "rulebookIds": rulebook_ids,
            "reason": reason,
            "status": "accepted",
            "startedAt": now,
        }
        self._ingestion.insert_one(payload)

        return {
            "status": "accepted",
            "refreshedRulebooks": rulebook_ids,
        }
