# Operations — CI/CD, Deployment, Monitoring, Logging, PQC Observability

## 1. How to Run (Local, 3 Terminals)

**Prerequisites:** Python 3.13, `uv` package manager (or pip), `cryptography`, `mlkem`

**Setup (once):**
```bash
uv sync --frozen
# or pip install cryptography mlkem
```

**Terminal 1: Cloud Service (data 6000 + health 6001)**
```bash
uv run python src/cloud_service.py
# Expected:
# Cloud Service listening for gateway on port 6000...
# Cloud health/analytics listening on 6001...
# Generates cloud_public_key.bin (800B) and telemetry.db (SQLite)
```

**Terminal 2: Edge Gateway (legacy 5000 + health 5001)**
```bash
uv run python src/edge_gateway.py
# Expected:
# Edge Gateway listening for legacy devices on port 5000...
# Gateway health listening on 5001...
# Reads cloud_public_key.bin if exists, otherwise fallback
```

**Terminal 3: Legacy Device (ephemeral)**
```bash
uv run python src/legacy_device.py
# Sends one telemetry reading, closes
```

**Verify:**
- Gateway Terminal 2: `Received from device: {"device_id":...}`
- Cloud Terminal 1: `Cloud received from sensor-node-01: {...}` + `Cloud stored...`
- DB: `sqlite3 telemetry.db "SELECT * FROM telemetry;"`
- Health:
  - `curl http://127.0.0.1:5001/health` → gateway metrics `received, forwarded_to_cloud, fallback_local, replayed`
  - `curl http://127.0.0.1:6001/health` → cloud `db_rows, analytics avg_temp, pqc decaps_ok, success_rate, avg_decaps_ms`

**Fallback test:**
- Stop cloud (Ctrl+C in Terminal1), keep gateway running, send legacy again
- Check `gateway_fallback.log` → has `<timestamp> <json>`
- Health 5001 shows `fallback_local++`

## 2. Docker Deployment (Simulated, per course Q&A: entire pipeline is simulated, just code)

**Build:**
```bash
docker build -t edge-gateway:test .
docker build -t cloud-service:test .
```

**Run via docker-compose (local simulation):**
```bash
docker-compose up
# cloud: 6000:6000, 6001:6001, volumes for pk sharing
# gateway: 5000:5000, 5001:5001, depends_on cloud healthy
```

**Legacy device via Docker (ephemeral):**
```bash
docker run --network host python:3.13-slim python src/legacy_device.py
# Or locally: python src/legacy_device.py
```

**Dockerfile respects pyproject.toml + uv.lock + .python-version:**
- `FROM python:3.13-slim` matches `.python-version` 3.13
- `COPY pyproject.toml uv.lock .python-version README.md`
- `RUN pip install uv && uv sync --frozen --no-install-project` — uses locked versions from uv.lock
- `ENV PATH="/app/.venv/bin:$PATH"`
- `HEALTHCHECK` tries 5000 or 6000

## 3. CI/CD Pipeline

**File:** `.github/workflows/ci.yml`

**Triggers:** push to `main` or `arena/*`, PRs to `main`

**Jobs:**
1. **test:**
   - `actions/checkout@v4`
   - `astral-sh/setup-uv@v4` with cache — reads `.python-version` (3.13) automatically
   - `uv python install && uv python pin 3.13`
   - `uv sync --frozen` — respects `pyproject.toml` + `uv.lock`
   - `uv pip install pytest`
   - `uv run pytest -v` → 33 tests
   - `uv run python src/pqc_utils.py` → round-trip test
   - `uv run python -c "import src... print('imports ok')"`
   - Verify `pyproject.toml`, `uv.lock`, `.python-version` exist

2. **docker-build:** needs test, builds both images to verify Dockerfile respects lock

**Why CI matters:** Ensures gateway hardening (33/33) doesn't regress, PQC utils round-trip works, imports ok, Docker builds reproducible.

## 4. Monitoring, Logging, PQC Observability

**Logging:**
- Gateway: `gateway.log` (file handler, not stderr to keep tests clean), INFO level, timestamp, e.g., `2026-10-10 INFO Valid telemetry from sensor-node-01 temp=21.8`
- Cloud: `cloud.log` similarly
- PQC: `pqc.log` for encaps/decaps timings
- All logs use `logging.basicConfig` with file handler, minimal deps

**Metrics (in-memory counters, thread-safe with lock):**
- Gateway `metrics`: `received, rejected, replayed, invalid_json, invalid_schema, empty, forwarded_to_cloud, fallback_local, cloud_fail`, `replay_cache_size=len(seen_nonces)`, `uptime_s`
- Cloud `metrics`: `total_received, decaps_ok, decaps_fail, json_fail, db_rows, avg_decaps_ms, total_decaps_ms, uptime_start`

**Health endpoints:**
- Gateway 5001: `GET /health` → JSON with metrics, replay_cache_size, uptime
- Cloud 6001: `GET /health` or `/analytics` → JSON with `db_rows, total_received, analytics {total_count, avg_temperature, avg_humidity, max_timestamp, last_10}, pqc {decaps_ok, decaps_fail, json_fail, success_rate, avg_decaps_ms}, uptime_s`

**PQC observability (post-quantum-related):**
- Encaps time: `encaps_ms` logged in `pqc_utils.encrypt_for_cloud` (~0.03ms)
- Decaps time: `decaps_ms` logged in `decrypt_from_gateway` (~0.04ms)
- Sizes: `ct_len=768`, `pk_len=800`, `ss_len=32`, `total_len` ~845B for small JSON
- Success rate: `success_rate = decaps_ok/(ok+fail)` exposed via health
- Fallback rate: `fallback_local` and `cloud_fail` show PQC distribution failures

**Analytics as observability (simple DB):**
- SQLite `telemetry.db` with table `telemetry(id, device_id, timestamp, temperature, humidity, status, received_at, source_ip, pqc_decaps_ms, raw_json)`
- Queries: `COUNT`, `AVG(temperature)`, `AVG(humidity)`, `last 10 ORDER BY received_at DESC`
- Useful for managers: see how many messages protected by PQC vs fallback, avg temp, recent telemetry

## 5. LLM Interaction Summary

- Prompt: "Generate Docker and CI/CD for Python project with uv, need to respect pyproject.toml, uv.lock, .python-version, simple healthchecks, docker-compose for gateway and cloud"
- LLM initially suggested `pip install -r requirements.txt` — rejected, project uses `uv` and `pyproject.toml`, not requirements.txt
- LLM suggested Flask for health endpoints — rejected, adds extra dep, we used stdlib `http.server` to keep simple
- Accepted: `astral-sh/setup-uv` action, `uv sync --frozen`, Dockerfile with `uv sync --no-install-project`, `ENV PATH .venv/bin`, HEALTHCHECK via socket connect, docker-compose with `depends_on healthy` and volume sharing for pk file
- Human verification: ran `pytest -v` 33 passed, `docker build` not possible in sandbox (no docker), but verified Dockerfile copies correct files and uses uv

## 6. Remaining Ops Gaps

- No Prometheus/Grafana (JSON health only, documented as simple)
- No log rotation (logs grow forever, should add rotation)
- No alerting (future: alert if `success_rate < 0.9` or `fallback_local` high)
- File-based pk sharing via bind mount is not secure for production (should use secret manager)

