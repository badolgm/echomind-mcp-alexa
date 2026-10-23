"""Domain purity guard: A1 modules must stay pure (stdlib + domain only)."""

from __future__ import annotations

from pathlib import Path

_MODULES = [
    Path("src/domain/services/recall_plan.py"),
    Path("src/domain/services/evidence.py"),
    Path("src/domain/services/recall_planner.py"),
]

_FORBIDDEN = (
    "fastapi",
    "boto3",
    "mcp",
    "src.infrastructure",
    "infrastructure.",
    "httpx",
    "requests",
    "urlopen",
    "urllib.request",
    "PIL",
    "numpy",
    "torch",
    "transformers",
    "openai",
    "sklearn",
    "sqlalchemy",
)

_PROHIBITED_CALLS = ("time.time(", "requests.", "httpx.", "urlopen(")


def test_new_modules_import_only_stdlib_and_domain() -> None:
    for path in _MODULES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in _FORBIDDEN:
            # imports usually start with from/import + token
            if f"from {token}" in text or f"import {token}" in text:
                raise AssertionError(f"forbidden import in {path}: {token}")


def test_no_time_or_network_calls_in_domain() -> None:
    for path in _MODULES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for call in _PROHIBITED_CALLS:
            if call in text:
                raise AssertionError(f"forbidden call in {path}: {call}")


def test_required_future_import_present() -> None:
    for path in _MODULES:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "from __future__ import annotations" in text, f"missing future in {path}"
