# ── Stage 1: Build frontend ────────────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --prefer-offline

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# util-linux provides `unshare` for HYDRA_SANDBOX_NETWORK=true.
# unshare --user --net does not require CAP_SYS_ADMIN on kernels with
# unprivileged user namespaces enabled (the default on most distros).
RUN apt-get update && apt-get install -y --no-install-recommends \
    util-linux \
 && rm -rf /var/lib/apt/lists/*

# Create a non-root user so the process never runs as root inside the container.
RUN groupadd --gid 1001 hydra \
 && useradd --uid 1001 --gid 1001 --no-create-home hydra

# Copy Python package sources and build frontend into the bundled dist dir.
COPY pyproject.toml README.md MANIFEST.in ./
COPY hydra_agents/ ./hydra_agents/
COPY --from=frontend-builder /app/frontend/dist/ ./hydra_agents/frontend_dist/

# Install the package, then hand ownership of everything to the hydra user.
RUN pip install --no-cache-dir . \
 && mkdir -p /data/output \
 && chown -R hydra:hydra /app /data

ENV HYDRA_OUTPUT_DIRECTORY=/data/output

USER hydra

EXPOSE 8000

# --no-open: no point trying to open a browser inside the container
CMD ["hydra-agents", "serve", "--no-open"]
