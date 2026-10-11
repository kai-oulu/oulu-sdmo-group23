# Oulu Software DEV-Maintenance-Ops Project Group 23
Members: Kim Nguyen | Manh Nguyen | Quoc Nguyen | Danish Sharjeel | Kaiquan Mah

## Quick Start (3-tier with PQC + DB + Health)

**Prerequisites:** Python 3.13, uv package manager

```bash
uv sync --frozen
```

**Terminal 1: Cloud Service (6000 data + 6001 health)**
```bash
uv run python src/cloud_service.py
# Generates cloud_public_key.bin (800B) and telemetry.db (SQLite)
```

**Terminal 2: Edge Gateway (5000 legacy + 5001 health)**
```bash
uv run python src/edge_gateway.py
```

**Terminal 3: Legacy Device**
```bash
uv run python src/legacy_device.py
```

**Verify:**
- Gateway: `Received from device: {...}`
- Cloud: `Cloud received from sensor-node-01: {...}` + stored in DB
- `curl http://127.0.0.1:5001/health` → gateway metrics
- `curl http://127.0.0.1:6001/health` → cloud db_rows, avg_temp, pqc success_rate
- `sqlite3 telemetry.db "SELECT * FROM telemetry;"`

**Docker (simulated deployment):**
```bash
docker-compose up
# cloud 6000:6000,6001:6001, gateway 5000:5000,5001:5001
```

**Tests:**
```bash
uv run pytest -v
# 33 passed
```

## Documentation

- `documentation/00_4h_gaps_analysis_n_scope_plan.md` — 4h scope plan with progress log
- `documentation/01_baseline_analysis.md` — baseline architecture, measurements, gap analysis
- `documentation/02_design_decisions_n_key_llm_interactions.md` — 10 LLM interactions logged
- `documentation/03_mlkem_integration.md` — ML-KEM-512 hybrid design, sizes, code snippets
- `documentation/04_migration_fallback_strategy.md` — phased migration, fallback store-and-forward
- `documentation/05_operations.md` — CI/CD, Docker, logging, metrics, health, PQC observability, DB analytics
- `documentation/06_final_evaluation.md` — strengths, weaknesses, tech debt, risks
- `documentation/part1_documentation.md` — consolidated Part1 technical documentation (peer review entry point)

## Architecture

```
[Legacy Device: ATmega328P sim] --AES-GCM PSK, TCP 5000--> [Edge Gateway: 5000+5001 health]
  2KB SRAM, 16B PSK, 12B nonce                            | decrypt, validate, replay check, PQC encaps -> TCP 6000
                                                          v
                                                   [Cloud: 6000 data + 6001 health/analytics]
                                                     ML-KEM-512 decaps, SQLite telemetry.db
```

Wire formats:
- Link1: nonce(12) || ciphertext+tag ~123B (95B JSON +28B overhead)
- Link2: ct(768) || nonce(12) || aes_ct ~845B, hybrid AES-256-GCM with ML-KEM shared secret 32B

## CI/CD

- `.github/workflows/ci.yml` uses `astral-sh/setup-uv` respecting `.python-version`, `pyproject.toml`, `uv.lock`
- `Dockerfile` FROM python:3.13-slim, `uv sync --frozen`, HEALTHCHECK
- `docker-compose.yml` with healthchecks and volume sharing for public key

Copyright © 2026. All rights reserved.
