"""Spatial identity helpers for the memory records (A5 activation).

Pure and duck-typed, following the ``evidence`` module convention: they read
``camera_id``/``zone`` off any object that carries them, so they work on
``MemoryRecord``, on ``Evidence`` and on bare test stand-ins alike.

Every helper degrades to the V1 identity when the spatial field is absent:
``zone`` falls back to ``location`` and ``camera_id`` falls back to ``source``.
That fallback is exactly the grouping the recall engine performed before this
phase, so records without spatial metadata keep resolving to the same keys.

A helper returns ``(value, degraded)``: ``degraded`` is ``True`` when the
coarser fallback had to be used, which lets the engine report honestly in its
trace whether the spatial identity is precise or only approximated.
"""

from __future__ import annotations


def _optional_text(value: object) -> str | None:
    """Normalize an optional spatial field: blanks and ``None`` mean absent."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_zone(record: object) -> tuple[str, bool]:
    """Zone identity of ``record``, degrading to ``location`` when absent."""
    zone = _optional_text(getattr(record, "zone", None))
    if zone is not None:
        return zone, False
    return str(getattr(record, "location", "")), True


def resolve_camera(record: object) -> tuple[str, bool]:
    """Camera identity of ``record``, degrading to ``source`` when absent."""
    camera = _optional_text(getattr(record, "camera_id", None))
    if camera is not None:
        return camera, False
    return str(getattr(record, "source", "")), True
