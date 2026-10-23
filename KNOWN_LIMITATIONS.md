# KNOWN_LIMITATIONS.md

## Known Limitations (Accepted for Hackathon)

### Perception / Vision
- No everyday object detection: Does not recognize charger, keys, phone, mouse, keyboard, monitor. Only event labels: PERSON, PET, MOTION, SMOKE, FIRE, GATE_OPEN, DOOR_OPEN, FALL DETECTED.
- No visual inference of openings: GATE_OPEN/DOOR_OPEN depend on SensorBus, not inferred from image.
- Vivotek based on motion + sensors: Motion detection by frame-delta (heuristic). Requires consecutive frames.

### Alerts / Memory
- DOOR_OPEN does not trigger alert: NOT in _ALERT_TRIGGERS. Generates detection if from sensors, but does not publish camera_alert.
- Sensor dependency: Without physical/configured SensorBus, GATE_OPEN/DOOR_OPEN are not generated.
- First ticks: Without previous frame, motion_score may be 0.0 until comparison is available.

### Architecture / Scope
- No remote VLM: On-device/QFP philosophy. Does not use LLM for recall.
- No integrated object detection: Planned but not implemented (out of scope for freeze).
- Limited triggers: Only GATE_OPEN, PET_ESCAPING, MOTION trigger alerts.

## Notes
These are design/scope limitations, not bugs. The focus is on traceable episodic memory, not generic object recognition.
