# Oulu Software DEV-Maintenance-Ops Project Group 23 — Hybrid Traditional & Post-Quantum Cryptography Compatible Sensor-EdgeGateway-Cloud System
* **Members:** Kaiquan Mah | Quoc Nguyen | Danish Sharjeel | Manh Nguyen | Kim Nguyen  
* **Python:** 3.13, package manager `uv`, deps `cryptography>=50.0.1`, `mlkem>=0.0.3`  
* **Tests:** 33 passed (was 27/33 baseline)


## Project Overview

Create then modernize a 2-tier legacy sensor system (simulated ATmega328P → gateway) into 3-tier with PQC (Post-Quantum Cryptography):

- **Link1 (legacy):** AES-128-GCM PSK 16B, TCP 5000, EOF framing, 28B overhead (12B nonce + 16B tag)
- **Link2 (PQC):** ML-KEM-512 hybrid `ct(768B)||nonce(12B)||aes_ct` ~845B, gateway → cloud TCP 6000, with fallback to `gateway_fallback.log`
- **Cloud:** SQLite `telemetry.db` + analytics (COUNT, AVG temp/humidity, last 10, PQC success rate) via health 6001
- **Gateway health:** 5001 metrics (received/rejected/replayed/forwarded/fallback)

**Why offload PQC to gateway:** ATmega328P 2KB SRAM cannot hold ML-KEM-512 sk 1632B + workspace 1000-1500B = ~3KB → stack overflow. Gateway (Linux/Pi) has enough RAM, encaps 0.03ms, decaps 0.04ms negligible.


## Architecture

```
[Legacy Device: ATmega328P sim] --AES-GCM PSK, TCP 5000, EOF--> [Edge Gateway: 5000 data + 5001 health]
  2KB SRAM/32KB Flash, 16B PSK                                  | decrypt, validate schema, replay check (seen_nonces set)
                                                                | load cloud_public_key.bin (800B)
                                                                | if ok: PQC encrypt -> TCP 6000
                                                                | else: fallback to gateway_fallback.log
                                                                v
                                                         [Cloud: 6000 data + 6001 health/analytics]
                                                           decaps(dk,ct) -> ss 32B, AES-256-GCM decrypt
                                                           INSERT INTO telemetry.db (SQLite)
```

Wire formats:
- Link1: `nonce(12) || ciphertext+tag`, JSON ~95B, wire ~123B
- Link2: `ct(768) || nonce(12) || aes_ct+tag` ~845B, ss 32B as AES-256-GCM key


## Quick Start (3-tier)

**Prerequisites:** Python 3.13, `uv`

```bash
uv sync --frozen --all-groups  # respects pyproject.toml + uv.lock + .python-version
```

**Terminal 1 — Cloud (6000 data + 6001 health):**
```bash
uv run python src/cloud_service.py
# Generates cloud_public_key.bin (800B) + telemetry.db
# Health: http://127.0.0.1:6001/health
```

**Terminal 2 — Gateway (5000 legacy + 5001 health):**
```bash
uv run python src/edge_gateway.py
# Listens 5000 + health 5001, forwards to cloud via PQC
# If cloud_public_key.bin missing or cloud down → fallback to gateway_fallback.log
```

**Terminal 3 — Legacy:**
```bash
uv run python src/legacy_device.py
# Sends AES-GCM encrypted telemetry to gateway
```

**Verify E2E:**
```bash
curl http://127.0.0.1:5001/health  # gateway: received 2, forwarded 2
curl http://127.0.0.1:6001/health  # cloud: db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0
sqlite3 telemetry.db "SELECT COUNT(*), AVG(temperature) FROM telemetry;"
cat gateway_fallback.log  # only if cloud down
```

**Docker (simulated deployment):**
```bash
docker-compose up --build
# cloud 6000:6000,6001:6001, gateway 5000:5000,5001:5001, depends_on healthy, volume pqc-shared for pk
# Legacy still runs on host: python src/legacy_device.py (connects to host 5000 -> gateway container)
```


## Testing

```bash
uv run pytest -v
# 33 passed (5 unit legacy/gateway, 11 security/invalid, 2 TCP flow, 10 robustness, 2 negative)
# Baseline was 27/33 (gateway crashed on InvalidTag, no schema, no replay)
# After hardening: try/except + REQUIRED_FIELDS + seen_nonces set → 33/33

uv run python src/pqc_utils.py
# PQC round-trip: packet 845B, encaps 0.03ms (Rust) / 0.82ms (pure Python), decaps 0.04ms, Round-trip OK
# Supports both Rust binding (rust.so 909KB) and pure Python (fastmath.so 80KB, empty __init__.py) wheels of mlkem==0.0.3
```

**Manual tamper test:** `packet[15] ^= 0xFF` → `InvalidTag` detected (integrity).


## Documentation (Part1)

- `documentation/00_4h_gaps_analysis_n_scope_plan.md` — 4h scope plan on 2026.10.10 to understand gaps in our codebase and work done over the weekend to cover those gaps further
- `documentation/01_baseline_analysis.md` — baseline 2-tier architecture (legacy device and gateway), 27/33 tests passed
- `documentation/02_design_decisions_n_key_llm_interactions.md` — 10 LLM interactions with accepted/modified/rejected user indications
- `documentation/03_mlkem_integration.md` — ML-KEM-512 hybrid design
- `documentation/04_migration_fallback_strategy.md`
- `documentation/05_operations.md` — CI/CD, Dockerfile, docker-compose (healthchecks, volumes), logging file-only to keep tests clean, metrics, health 5001/6001, PQC observability, DB analytics (on sqlite DB)
- `documentation/06_final_evaluation.md` — acronym glossary, strengths, weaknesses & technical debt, risks
- `documentation/part1_documentation.md` — **consolidated documentation for peer review** which includes requirements, architecture, design decisions, implementation, testing, operations, final evaluation of technical debt, references


## CI/CD

- `.github/workflows/ci.yml` on push to `main`/`arena/*` + PRs:
  - `test` job: `setup-uv` reads `.python-version` 3.13 + `uv.lock`, `uv sync --frozen --all-groups`, `uv pip install pytest`, `PYTHONPATH` set, `pytest -v` 33 tests, `pqc_utils.py` round-trip, import checks for both `src.*` and top-level
  - `docker-build` job: `needs: test`, `docker build -t edge-gateway:test .` verifies Dockerfile respects `pyproject.toml+uv.lock+.python-version`
- `Dockerfile` implicit convention: `build: .` in compose = `build: {context: ., dockerfile: Dockerfile}` implicit, `docker build .` = `docker build -f Dockerfile .` implicit — both read `./Dockerfile` without mentioning name
- Runtime table: `pyproject.toml+uv.lock+.python-version` used local+CI+Docker, `Dockerfile` used local Docker+CI docker-build, `docker-compose.yml` local only, `ci.yml` GitHub only


## Team

* Kaiquan Mah ("cloud service"/logging/db/analysis, ML-KEM/PQC implementation/migration with AES fallback (if PQC is not supported), docker, CI-CD via GitHub Actions, documentation)
* Quoc Nguyen (tests)
* Danish Sharjeel (initial legacy device and edge gateway code and its documentation)
* Manh Nguyen (cloud+DB+analytics)
* Kim Nguyen (migration/fallback, docs)

Copyright © 2026. All rights reserved.
