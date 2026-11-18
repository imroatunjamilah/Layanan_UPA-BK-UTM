"""Utilitas kecil bersama."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Waktu UTC *naive* (disimpan konsisten di SQLite, ditandai UTC saat serialisasi)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime | None) -> str | None:
    """Serialisasi datetime naive-UTC menjadi string ISO-8601 bertanda 'Z'."""
    if dt is None:
        return None
    return dt.isoformat() + ("Z" if dt.tzinfo is None else "")
