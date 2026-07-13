"""Persist review run history for iteration and audit."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from domain.db import get_session, init_db
from domain.models import ReviewHistoryRow
from domain.paths import REVIEW_SCORES_PATH

_MAX_RUNS = 60


def _empty_history() -> dict[str, Any]:
    return {"runs": []}


def _load_json_file() -> dict[str, Any]:
    if not REVIEW_SCORES_PATH.exists():
        return _empty_history()
    try:
        payload = json.loads(REVIEW_SCORES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_history()
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        return _empty_history()
    return payload


def import_file_if_empty() -> int:
    init_db()
    session = get_session()
    try:
        row = session.get(ReviewHistoryRow, 1)
        if row:
            return 0
        payload = _load_json_file()
        if not payload.get("runs"):
            return 0
        session.add(
            ReviewHistoryRow(
                id=1,
                payload=json.dumps(payload, ensure_ascii=False),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
        return len(payload["runs"])
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def load_review_history() -> dict[str, Any]:
    init_db()
    import_file_if_empty()
    session = get_session()
    try:
        row = session.get(ReviewHistoryRow, 1)
        if row:
            payload = json.loads(row.payload)
            if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
                return payload
    finally:
        session.close()
    return _load_json_file()


def append_review_run(run: dict[str, Any]) -> dict[str, Any]:
    init_db()
    import_file_if_empty()
    history = load_review_history()
    history.setdefault("runs", [])
    history["runs"].append(run)
    history["runs"] = history["runs"][-_MAX_RUNS:]

    session = get_session()
    try:
        row = session.get(ReviewHistoryRow, 1)
        payload_text = json.dumps(history, ensure_ascii=False)
        if row:
            row.payload = payload_text
            row.updated_at = datetime.utcnow()
        else:
            session.add(
                ReviewHistoryRow(
                    id=1,
                    payload=payload_text,
                    updated_at=datetime.utcnow(),
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    REVIEW_SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_SCORES_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return history
