# Build static frontend files
FROM node:25-alpine AS builder

WORKDIR /app

ENV NODE_ENV=production

RUN apk add pnpm

# Install dependencies before copying the source so this layer is only
# rebuilt when the lockfile changes
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN CI=true pnpm install

COPY frontend .

ARG VITE_API_BASE_URL=/api
RUN VITE_API_BASE_URL=${VITE_API_BASE_URL} pnpm build

# Build backend image that also serves frontend (stored in `/app/frontend-dist`)
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN groupadd --system bracket && \
    useradd --system --create-home --gid bracket --home-dir /home/bracket bracket && \
    chown bracket:bracket /app
USER bracket

# Install dependencies before copying the source so this layer is only
# rebuilt when the lockfile changes
COPY --chown=bracket:bracket backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --locked

COPY --chown=bracket:bracket backend /app

COPY --from=builder /app/dist /app/frontend-dist

EXPOSE 8400

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8400/ping', timeout=5).read()"]

CMD [ \
    "uv", \
    "run", \
    "--no-dev", \
    "--locked", \
    "--", \
    "gunicorn", \
    "-k", \
    "uvicorn.workers.UvicornWorker", \
    "bracket.app:app", \
    "--bind", \
    "0.0.0.0:8400", \
    "--workers", \
    "1" \
]
