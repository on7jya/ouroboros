# Ouroboros Repository

## Overview
This repository contains the self‑creating agent **Ouroboros** along with its evolving components.

### Current Evolution Cycle
- **Cycle:** 476 (as of 2026‑02‑25)

### Version
- **VERSION:** 6.11.0

### Changelog (v6.5.0 – Minor Release)
- 🎨 **Web Dashboard Added** — Real-time Kafka translator metrics in browser
  - Live auto-refresh (1s interval)
  - Status badge, uptime, error counters  
  - Configuration and health info
- ✨ **CLI Viewer Added** — Terminal-based status dashboard
  - Auto-refresh with configurable interval
  - Connection health monitoring
  - Error reporting and diagnostics

### Changelog (v6.6.0 – Minor Release)
- 🧪 **Real Kafka Integration Tests** — In-memory mock broker for Colab-compatible testing
  - No Docker dependency (runs in containerized environments)
  - Tests produce/consume messages and verify consumer groups
  - `kafka_mock.py` mock broker implementation with persistent offsets

### Changelog (v6.8.1 – Minor Release)
- 📚 **Production Deployment Documentation** — Complete deployment guide for all environments
  - Kubernetes, Docker Swarm, and bare-metal instructions  
  - Monitoring with web dashboard (v6.5) + CLI viewer (v6.6)
  - Health checks, scaling, security, troubleshooting

### Changelog (v6.9.0 – Minor Release)
- 🧬 **Self-Evolution Protocol** — Detect stagnation and auto-commit evolution
  - Cycle counting and stagnation detection (40+ cycles trigger)
  - Automatic tag/release workflow
  - VERSION drift auto-fix

### Changelog (v6.10.0 – Minor Release)
- 🧠 **Subagent Architecture** — Planner, Coder, Tester, Reflector
  - Kafka-based internal message bus for subagent communication
  - Voting protocol for core changes (quorum detection)
  - Stagnation detection and self-initiated evolution

### Changelog (v6.11.0 – Minor Release)
- 🌐 **Supervisor Protocol** — Self-orchestration of subagents
  - Quorum-based voting (50% approval threshold)
  - Health metrics publishing to Kafka topic
  - Proposal → vote → implementation pipeline

### Services
- **FastAPI Kafka Event Translator** – reliable Kafka-to-Kafka message translation with logging, metrics, and automatic recovery.