"""Persist daily prediction snapshots for review and iteration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from domain.db import get_session, init_db
from domain.models import PredictionSnapshotRow
from domain.paths import PREDICTIONS_DIR, SYDNEY


def _parse_generated_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(SYDNEY).replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return datetime.now(SYDNEY).replace(tzinfo=None)


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def import_files_if_empty() -> int:
    """Import legacy data/predictions/*.json into SQLite when DB is empty."""
    init_db()
    session = get_session()
    try:
        if session.query(PredictionSnapshotRow).count() > 0:
            return 0
        imported = 0
        if not PREDICTIONS_DIR.exists():
            return 0
        for path in sorted(PREDICTIONS_DIR.glob("*.json")):
            payload = _load_json_file(path)
            if not payload:
                continue
            signal_date = str(payload.get("date") or path.stem)
            session.merge(
                PredictionSnapshotRow(
                    signal_date=signal_date,
                    generated_at=_parse_generated_at(payload.get("generated_at")),
                    payload=json.dumps(payload, ensure_ascii=False),
                )
            )
            imported += 1
        if imported:
            session.commit()
        return imported
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_prediction_snapshot(signal_date: str, payload: dict[str, Any]) -> None:
    init_db()
    import_files_if_empty()
    session = get_session()
    try:
        row = PredictionSnapshotRow(
            signal_date=signal_date,
            generated_at=_parse_generated_at(payload.get("generated_at")),
            payload=json.dumps(payload, ensure_ascii=False),
        )
        session.merge(row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = PREDICTIONS_DIR / f"{signal_date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_prediction_snapshot(signal_date: str) -> dict[str, Any] | None:
    init_db()
    import_files_if_empty()
    session = get_session()
    try:
        row = session.get(PredictionSnapshotRow, signal_date)
        if row:
            return json.loads(row.payload)
    finally:
        session.close()
    return _load_json_file(PREDICTIONS_DIR / f"{signal_date}.json")


def list_prediction_dates() -> list[str]:
    init_db()
    import_files_if_empty()
    session = get_session()
    dates: set[str] = set()
    try:
        for row in session.query(PredictionSnapshotRow.signal_date).all():
            dates.add(row[0])
    finally:
        session.close()
    if PREDICTIONS_DIR.exists():
        for path in PREDICTIONS_DIR.glob("*.json"):
            dates.add(path.stem)
    return sorted(dates)


def iter_prediction_snapshots() -> Iterator[tuple[str, dict[str, Any]]]:
    for signal_date in list_prediction_dates():
        payload = load_prediction_snapshot(signal_date)
        if payload:
            yield signal_date, payload
