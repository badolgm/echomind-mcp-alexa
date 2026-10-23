# JUDGE_QUICK_START.md

## EchoMind in 5 Minutes

### What is it?
EchoMind is an evidence-first episodic memory system for the home. It remembers facts observed by cameras and sensors, and answers by reconstructing, relating, ordering, and narrating based on auditable evidence.

### Key Differentiator
- Not a chatbot: It does not memorize conversation; it remembers persisted events
- Evidence-first: Every response shows evidence + trace
- Two paths: CURRENT_STATE (live snapshot) vs RECALL (historical)
- Deterministic: Majority without LLM for recall; auditable
- Honest: Abstains when evidence is insufficient

### Architecture in Brief
Sensors/Cameras -> Watchdog -> EventHub -> MemoryBridge -> VectorMemoryService
Question -> Query Router -> (CURRENT_STATE | RECALL Engine) -> Response + evidence + trace

### Quick Demo (3 Questions)
1. Is the gate closed? -> Live state (Query Router)
2. What happened before the fall? -> Timeline + Relations + evidence
3. Which cameras observed the same event? -> Traceability

### Key Documentation
- README.md - Overview
- docs/architecture/ECHOMIND_V2_MEMORY_FIRST_ARCHITECTURE.md - Memory architecture
- docs/implementation/A7C_QUERY_ROUTER_ARCHITECTURE.md - Router
- docs/implementation/A7D_IMPLEMENTATION_REPORT.md - Response Intent Adapter

### Tests
641 tests pass (635 unit + 6 integration). 9 collection errors from missing boto3/botocore modules (environment dependency, not code regression).
