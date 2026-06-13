FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN groupadd --system bracket && \
    useradd --system --create-home --gid bracket --home-dir /home/bracket bracket && \
    chown bracket:bracket /app
USER bracket

# Install dependencies before copying the source so this layer is only
# rebuilt when the lockfile changes
COPY --chown=bracket:bracket pyproject.toml uv.lock ./
RUN uv sync --no-dev --locked

COPY --chown=bracket:bracket . /app

EXPOSE 8400

HEALTHCHECK --interval=3s --timeout=5s --retries=10 \
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
