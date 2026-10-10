# Created 2026.10.10
# Minimal Dockerfile respecting pyproject.toml + uv.lock + .python-version
# Uses uv to install locked dependencies (frozen) for reproducibility
FROM python:3.13-slim

WORKDIR /app

# Install uv (package manager) via pip - respects .python-version (3.13) from base image
RUN pip install --no-cache-dir uv

# Copy dependency files first for layer caching (respecting lock)
COPY pyproject.toml uv.lock .python-version README.md ./

# Copy src for package=false project (no build, just deps)
COPY src/ ./src/

# Sync dependencies from uv.lock (frozen, respects pyproject.toml)
# --no-install-project because package=false (no installable package, just deps)
# This creates .venv with cryptography and mlkem locked versions
RUN uv sync --frozen --no-install-project

# Ensure venv is on PATH (uv creates .venv)
ENV PATH="/app/.venv/bin:$PATH"

# Expose ports: gateway 5000 data + 5001 health, cloud 6000 data + 6001 health
EXPOSE 5000 5001 6000 6001

# Healthcheck: try gateway 5000 or cloud 6000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 5000))" || \
      python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 6000))" || exit 1

# Default command runs gateway (overridden in docker-compose for cloud)
# Use python from venv (via PATH)
CMD ["python", "src/edge_gateway.py"]

