from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4


class RulesLawyerSavedRulesRepository:
    def __init__(self, db, collection_name: str = "ruleslawyer_saved_rules"):
        self._collection = db[collection_name]

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        return list(self._collection.find({"userId": user_id}, {"_id": 0}).sort("createdAt", -1))

    def save_rule(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow()
        record = {
            "id": str(uuid4()),
            "userId": user_id,
            "rulebookId": payload["rulebookId"],
            "queryText": payload["queryText"],
            "responseText": payload["responseText"],
            "citations": payload.get("citations", []),
            "tags": payload.get("tags", []),
            "createdAt": now,
            "updatedAt": now,
        }
        self._collection.insert_one(record)
        return record
