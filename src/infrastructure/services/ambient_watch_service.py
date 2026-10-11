"""Autonomous ambient watchdog: continuous prediction engine for the home.

Runs a periodic loop over live camera frames and home sensor telemetry,
computes a deterministic, explainable prediction (risk + detections) and
pushes ``camera_alert`` events to the dashboard ``EventHub`` whenever the
predicted risk reaches HIGH/CRITICAL **and** the verdict is driven by a
visual access event — motion, an open gate, or a pet/person near the exit.
Smoke and temperature readings still feed the live readout but never fire
alerts on their own (no random smoke/temperature alarms). Because it is a
pure edge-data engine (no network, no ML runtime, no AWS), it keeps predicting
and alerting 24/7 even behind the Quota Fallback Protocol.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.infrastructure.config.event_hub import EventHub
from src.infrastructure.services.sensor_bus import SensorReading

if TYPE_CHECKING:
    from src.infrastructure.adapters.iot.vivotek_adapter import CameraFrameSource

MOTION_THRESHOLD = 0.20
_WATCH_ALERT_LEVELS = ("HIGH", "CRITICAL")
_ALERT_TRIGGERS = frozenset({"GATE_OPEN", "PET_ESCAPING", "MOTION"})

_LABEL_ES: dict[str, str] = {
    "SMOKE": "humo",
    "FIRE": "fuego",
    "TEMP_RISING": "la temperatura sube",
    "GATE_OPEN": "la reja está abierta",
    "DOOR_OPEN": "la puerta está abierta",
    "PET_ESCAPING": "la mascota intenta escapar",
    "MOTION": "movimiento detectado",
}

_RECOMMENDATIONS_ES: dict[str, str] = {
    "CRITICAL": "Llama a emergencias e inspecciona el origen de inmediato.",
    "HIGH": "Actúa ya: cierra el perímetro o revisa el origen del evento.",
    "MEDIUM": "Revisa la zona en los próximos minutos.",
    "LOW": "Sigue monitoreando: todo se ve normal.",
}

_NEUTRAL_ANNOUNCEMENT = (
    "Sin detecciones activas. Todo normal.\n" "No active detections. All normal."
)

_SEVERITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


@dataclass(frozen=True, slots=True)
class AmbientPrediction:
    """One watchdog verdict combining sensors and camera motion."""

    risk_level: str
    signals: tuple[str, ...]
    detections: tuple[dict[str, object], ...]
    announcement: str
    recommendation: str


def _image_payload(data: bytes) -> bytes:
    """Strip container headers so comparison ignores JPEG EXIF timestamps.

    Android IP Webcam embeds a fresh timestamp/EXIF block on every snapshot,
    so raw-byte comparison of two static-scene JPEGs reports a large delta
    even though the pixels are identical. Trimming the container (everything
    before the SOS marker for JPEG, everything before IDAT for PNG) focuses
    the delta on the entropy-coded pixel data, where real motion dominates.
    """
    if data.startswith(b"\xff\xd8"):
        sos = data.rfind(b"\xff\xda")
        if sos != -1 and sos + 4 <= len(data):
            header_len = int.from_bytes(data[sos + 2 : sos + 4], "big")
            start = sos + 2 + header_len
            return data[start:]
        return data
    if data.startswith(b"\x89PNG"):
        idat = data.find(b"IDAT")
        if idat != -1:
            return data[idat:]
        return data
    return data


def frame_delta_ratio(first: bytes, second: bytes) -> float:
    """Fraction of sampled bytes that differ between two frames.

    A coarse but real motion proxy for compressed JPEG snapshots: consecutive
    frames of a static scene are near-identical, so a high delta ratio means
    the scene is actually changing (movement/zoom/lighting shift).
    """
    if not first or not second:
        return 0.0
    first = _image_payload(first)
    second = _image_payload(second)
    samples = 4096
    n = min(len(first), len(second))
    step = max(1, n // samples)
    checked = (n + step - 1) // step
    if checked == 0:
        return 0.0
    changed = 0
    for index in range(0, n, step):
        if first[index] != second[index]:
            changed += 1
    return changed / checked


def predict_ambient_state(
    reading: SensorReading,
    prev: SensorReading | None = None,
    motion_score: float = 0.0,
) -> AmbientPrediction:
    """Predict home risk from sensor telemetry, trends and camera motion.

    Every rule is explainable and deterministic: smoke thresholds, temperature
    level + rising slope, perimeter reed switches, and the pet-vs-open-gate
    correlation. The most severe active rule dominates the risk level.
    """
    risk = "LOW"
    signals: list[str] = []
    detections: dict[str, float] = {}

    def escalate(level: str) -> None:
        nonlocal risk
        if _SEVERITY[level] > _SEVERITY[risk]:
            risk = level

    smoke = reading.smoke_density
    smoke_delta = 0.0
    if prev is not None:
        smoke_delta = smoke - prev.smoke_density
    if smoke >= 0.75 or (smoke >= 0.45 and smoke_delta > 0.03):
        escalate("CRITICAL" if smoke >= 0.75 else "HIGH")
        signals.append("smoke indicators")
        detections["SMOKE"] = 0.95 if smoke >= 0.75 else 0.72
        if smoke >= 0.75:
            detections["FIRE"] = 0.86
    elif smoke >= 0.20:
        escalate("MEDIUM")
        signals.append("smoke indicators")
        detections["SMOKE"] = 0.55

    temp_delta = 0.0
    if prev is not None:
        temp_delta = reading.temperature_c - prev.temperature_c
    if reading.temperature_c >= 28.0 or (
        reading.temperature_c >= 26.0 and temp_delta > 0.2
    ):
        escalate("HIGH")
        signals.append("temperature rising")
        detections["TEMP_RISING"] = 0.81
    elif reading.temperature_c >= 26.0:
        escalate("MEDIUM")
        signals.append("temperature anomaly")
        detections["TEMP_RISING"] = 0.64

    if reading.gate_open:
        escalate("MEDIUM")
        signals.append("perimeter open")
        detections["GATE_OPEN"] = 0.9
    if reading.door_open:
        escalate("MEDIUM")
        signals.append("door open")
        detections["DOOR_OPEN"] = 0.88

    if reading.gate_open and reading.pet_proximity >= 0.5:
        escalate("HIGH")
        signals.append("pet escape risk")
        detections["PET_ESCAPING"] = 0.85

    if motion_score >= MOTION_THRESHOLD:
        detections["MOTION"] = round(min(0.4 + motion_score, 0.85), 2)
        escalate("HIGH")

    announcement = _announcement(risk, detections)
    recommendation = _RECOMMENDATIONS_ES[risk]
    return AmbientPrediction(
        risk_level=risk,
        signals=tuple(signals),
        detections=tuple(
            {"label": label, "confidence": confidence}
            for label, confidence in detections.items()
        ),
        announcement=announcement,
        recommendation=recommendation,
    )


def _announcement(risk: str, detections: dict[str, float]) -> str:
    phrases = sorted({_LABEL_ES[label] for label in detections if label in _LABEL_ES})
    prefix = {
        "CRITICAL": "¡Alerta crítica! ",
        "HIGH": "Atención: ",
        "MEDIUM": "Aviso: ",
    }.get(risk, "")
    if not phrases:
        return prefix + _NEUTRAL_ANNOUNCEMENT
    body = "Detecciones: " + ", ".join(phrases) + ". "
    return prefix + body + _RECOMMENDATIONS_ES[risk]


class AmbientWatchService:
    """Periodic watch loop: cameras + sensors -> predictions -> alerts."""

    def __init__(
        self,
        *,
        camera: CameraFrameSource,
        sensor_bus: Any,
        event_hub: EventHub,
        interval: float = 0.5,
        motion_threshold: float = MOTION_THRESHOLD,
    ) -> None:
        self._camera = camera
        self._sensors = sensor_bus
        self._hub = event_hub
        self._interval = interval
        self._motion_threshold = motion_threshold
        self._prev_payload = b""
        self._prev_reading: SensorReading | None = None
        self._stop = False
        self._last_state: dict[str, Any] = {
            "risk": "LOW",
            "source": "idle",
            "detections": [],
            "announcement": "",
        }

    @property
    def last_state(self) -> dict[str, Any]:
        return dict(self._last_state)

    async def tick(self, now: float | None = None) -> AmbientPrediction:
        """Evaluate one watch cycle: frame + sensors -> prediction -> alert."""
        now = time.time() if now is None else now
        reading = self._sensors.read(now)
        frame = await self._camera.get_frame()
        motion = 0.0
        if frame.source == "live":
            motion = frame_delta_ratio(self._prev_payload, frame.data)
        self._prev_payload = frame.data

        prediction = predict_ambient_state(reading, self._prev_reading, motion)
        self._prev_reading = reading

        detections = [dict(item) for item in prediction.detections]
        self._camera.record_detections(detections, frame.source)
        model_analysis_text = (
            f"{prediction.announcement}\n{prediction.recommendation}"
            if detections
            else prediction.announcement
        )
        self._last_state = {
            "risk": prediction.risk_level,
            "signals": list(prediction.signals),
            "detections": detections,
            "temperature_c": reading.temperature_c,
            "smoke_density": reading.smoke_density,
            "gate_open": reading.gate_open,
            "door_open": reading.door_open,
            "pet_proximity": reading.pet_proximity,
            "motion_score": round(motion, 4),
            "source": frame.source,
            "announcement": prediction.announcement,
            "recommendation": prediction.recommendation,
            "model_analysis": model_analysis_text,
            "safety_gate_signals": list(prediction.signals),
            "safety_gate_recommendation": prediction.recommendation,
            "ts": now,
        }

        triggered = any(item["label"] in _ALERT_TRIGGERS for item in detections)
        if prediction.risk_level in _WATCH_ALERT_LEVELS and triggered:
            self._hub.publish(
                {
                    "kind": "camera_alert",
                    "tool": "ambient_watchdog",
                    "status": prediction.risk_level,
                    "risk": prediction.risk_level,
                    "location": "camera",
                    "source": frame.source,
                    "detections": detections,
                    "motion_score": round(motion, 4),
                    "announcement": prediction.announcement,
                    "model_analysis": model_analysis_text,
                    "safety_gate_signals": list(prediction.signals),
                    "safety_gate_recommendation": prediction.recommendation,
                    "ts": now,
                }
            )
        return prediction

    async def run(self) -> None:
        """Watch forever until :meth:`stop` is requested."""
        while not self._stop:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - a watchdog must never die
                pass
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._stop = True
