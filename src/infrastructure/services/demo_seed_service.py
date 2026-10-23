"""Deterministic demo memory seeder for EchoMind historical recall.

Pobla VectorMemoryService con 5 escenarios plausibles para demostraciones
del hackathon sin requerir eventos en tiempo real.
"""

from __future__ import annotations

import time

from src.infrastructure.services.memory_service import (
    MemoryRecord,
    VectorMemoryService,
)

DEMO_SEED_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "id": "seed-01-pet-patio",
        "offset_seconds": 518400.0,  # 6 días atrás
        "location": "patio",
        "source": "camera_alert",
        "risk": "HIGH",
        "detections": (
            {"label": "PET", "confidence": 0.95},
            {"label": "GATE_OPEN", "confidence": 0.92},
        ),
        "model_analysis": (
            "La mascota se acercó a la reja mientras permanecía abierta. "
            "Pet approached the open gate."
        ),
    },
    {
        "id": "seed-02-smoke-kitchen",
        "offset_seconds": 172800.0,  # 2 días atrás
        "location": "kitchen",
        "source": "camera_alert",
        "risk": "HIGH",
        "detections": (
            {"label": "SMOKE", "confidence": 0.88},
            {"label": "TEMP_RISING", "confidence": 0.84},
        ),
        "model_analysis": (
            "Indicador de humo en la cocina resuelto en 4 minutos. "
            "Smoke in kitchen resolved quickly."
        ),
    },
    {
        "id": "seed-03-gate-access",
        "offset_seconds": 79200.0,  # 22 horas atrás
        "location": "cam-01",
        "source": "camera_alert",
        "risk": "HIGH",
        "detections": (
            {"label": "GATE_OPEN", "confidence": 0.96},
            {"label": "MOTION", "confidence": 0.82},
        ),
        "model_analysis": (
            "La reja principal abierta con detección de movimiento. "
            "Main gate open with motion detected."
        ),
    },
    {
        "id": "seed-04-fall-living",
        "offset_seconds": 10800.0,  # 3 horas atrás
        "location": "living",
        "source": "camera_alert",
        "risk": "CRITICAL",
        "detections": (
            {"label": "FALL DETECTED", "confidence": 0.91},
            {"label": "PERSON", "confidence": 0.89},
        ),
        "model_analysis": (
            "Posible caída detectada cerca del sofá. Asistencia requerida. "
            "Possible fall detected in living room."
        ),
    },
    {
        "id": "seed-05-elderly-living",
        "offset_seconds": 840.0,  # 14 minutos atrás
        "location": "living",
        "source": "camera_alert",
        "risk": "LOW",
        "detections": ({"label": "PERSON_ELDERLY", "confidence": 0.93},),
        "model_analysis": (
            "Adulto mayor descansando de forma segura en la sala. "
            "Senior resting safely in living room."
        ),
    },
)


def seed_demo_memory(
    memory: VectorMemoryService,
    base_time: float | None = None,
) -> list[MemoryRecord]:
    """Inyecta registros históricos canónicos relativos a base_time."""
    ref_time = time.time() if base_time is None else base_time
    created_records: list[MemoryRecord] = []

    for item in DEMO_SEED_DEFINITIONS:
        ts = ref_time - float(item["offset_seconds"])
        detections = tuple(
            dict(d) for d in item["detections"]  # type: ignore[union-attr]
        )
        record = MemoryRecord(
            id=str(item["id"]),
            timestamp=ts,
            location=str(item["location"]),
            source=str(item["source"]),
            detections=detections,
            risk=str(item["risk"]),
            model_analysis=str(item["model_analysis"]),
        )
        memory.store_memory(record)
        created_records.append(record)

    return created_records
