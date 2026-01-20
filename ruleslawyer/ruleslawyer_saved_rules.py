from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from google.cloud.firestore_v1.base_query import FieldFilter


class RulesLawyerSavedRulesRepository:
    def __init__(self, db, collection_name: str = "ruleslawyer_saved_rules"):
        self._collection = db.collection(collection_name)

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        query = self._collection.where(filter=FieldFilter("userId", "==", user_id)).stream()
        rules = []
        for doc in query:
            data = doc.to_dict()
            data["id"] = doc.id
            rules.append(data)
        rules.sort(key=lambda rule: rule.get("createdAt", ""), reverse=True)
        return rules

    def save_rule(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow()
        rule_id = str(uuid4())
        record = {
            "id": rule_id,
            "userId": user_id,
            "rulebookId": payload["rulebookId"],
            "queryText": payload["queryText"],
            "responseText": payload["responseText"],
            "citations": payload.get("citations", []),
            "tags": payload.get("tags", []),
            "createdAt": now,
            "updatedAt": now,
        }
        self._collection.document(rule_id).set(record)
        return record

    def update_rule(self, user_id: str, rule_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        updates = {key: value for key, value in payload.items() if key in {"queryText", "responseText", "citations", "tags"}}
        if not updates:
            return None

        doc_ref = self._collection.document(rule_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        existing = doc.to_dict()
        if existing.get("userId") != user_id:
            return None

        updates["updatedAt"] = datetime.utcnow()
        doc_ref.set(updates, merge=True)
        updated_doc = doc_ref.get()
        if not updated_doc.exists:
            return None
        updated = updated_doc.to_dict()
        updated["id"] = rule_id
        return updated

    def delete_rule(self, user_id: str, rule_id: str) -> bool:
        doc_ref = self._collection.document(rule_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        existing = doc.to_dict()
        if existing.get("userId") != user_id:
            return False
        doc_ref.delete()
        return True
