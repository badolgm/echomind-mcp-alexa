"""Simulated home sensor bus feeding the autonomous ambient watchdog.

Provides a deterministic, self-driven stream of ambient signals (temperature,
smoke density, perimeter reed switches and pet-collar telemetry) that evolves
over a repeating 120-second scenario cycle. The prediction engine therefore
always has *changing* input to reason about, without any network, hardware or
AWS dependency. Each scenario reproduces exactly for a given wall-clock phase,
so tests can pin ``now`` and verify deterministic predictions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CYCLE_SECONDS = 120.0
_BASELINE_TEMPERATURE = 22.4

# Scenario timeline (seconds within the 120 s cycle):
#   0-25   baseline (calm home)              -> LOW
#  25-45   pet moves toward the gate         -> moving, proximity rises
#  45-55   GATE OPENS, pet at the exit       -> PET_ESCAPING (HIGH)
#  55-70   gate closes, pet returns inward
#  70-90   smoke rises (stove/cooking)       -> SMOKE: MEDIUM..CRITICAL
#  90-105  door open, temperature spikes     -> TEMP_RISING (MEDIUM..HIGH)
#  105-120 cooldown back to baseline


@dataclass(frozen=True, slots=True)
class SensorReading:
    """One telemetry snapshot from the home sensor network."""

    timestamp: float
    temperature_c: float
    smoke_density: float
    gate_open: bool
    door_open: bool
    pet_proximity: float
    pet_moving: bool


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _scale(phase: float, start: float, end: float, y0: float, y1: float) -> float:
    """Piecewise linear ramp: ``y0`` before ``start``, ``y1`` after ``end``."""
    if phase <= start:
        return y0
    if phase >= end:
        return y1
    return y0 + (y1 - y0) * (phase - start) / (end - start)


def read_sensors(now: float) -> SensorReading:
    """Return the deterministic sensor snapshot for a given wall-clock time."""
    phase = now % CYCLE_SECONDS
    temperature = _BASELINE_TEMPERATURE + 0.06 * math.sin(now / 9.0)
    temperature += _scale(phase, 90.0, 104.0, 0.0, 7.4)

    smoke = _scale(phase, 70.0, 90.0, 0.05, 0.85)
    if phase >= 90.0:
        smoke = _scale(phase, 90.0, 105.0, 0.85, 0.12)

    gate_open = 45.0 <= phase < 55.0
    door_open = 92.0 <= phase < 100.0

    pet_proximity = _scale(phase, 25.0, 45.0, 0.12, 0.62)
    if 45.0 <= phase < 55.0:
        pet_proximity = _scale(phase, 45.0, 55.0, 0.62, 0.9)
    elif 55.0 <= phase < 70.0:
        pet_proximity = _scale(phase, 55.0, 70.0, 0.9, 0.2)

    pet_moving = (25.0 <= phase < 40.0) or (55.0 <= phase < 70.0)

    return SensorReading(
        timestamp=now,
        temperature_c=round(temperature, 2),
        smoke_density=round(_clamp01(smoke), 3),
        gate_open=gate_open,
        door_open=door_open,
        pet_proximity=round(_clamp01(pet_proximity), 2),
        pet_moving=pet_moving,
    )


class SimulatedSensorBus:
    """Duck-typed sensor source consumed by the ambient watchdog."""

    def read(self, now: float) -> SensorReading:
        return read_sensors(now)
