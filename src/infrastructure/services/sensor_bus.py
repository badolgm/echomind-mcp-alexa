"""Home sensor bus feeding the autonomous ambient watchdog.

The sensor layer exposes a **static, deterministic baseline** (gate and door
closed, calm pet, no smoke or temperature anomalies) instead of time-driven
scenario cycles. Live movement is therefore decided exclusively by the camera:
``frame_delta_ratio >= MOTION_THRESHOLD`` on the Vivotek snapshot is the only
real-time HIGH driver. A reading reproduces exactly for any timestamp, so tests
can pin ``now`` and always reason over the same calm baseline.
"""

from __future__ import annotations

from dataclasses import dataclass

_BASELINE_TEMPERATURE = 22.4


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


def read_sensors(now: float) -> SensorReading:
    """Return the calm, deterministic baseline for a given wall-clock time."""
    return SensorReading(
        timestamp=now,
        temperature_c=_BASELINE_TEMPERATURE,
        smoke_density=0.02,
        gate_open=False,
        door_open=False,
        pet_proximity=0.12,
        pet_moving=False,
    )


class SimulatedSensorBus:
    """Duck-typed sensor source consumed by the ambient watchdog."""

    def read(self, now: float) -> SensorReading:
        return read_sensors(now)
