FROM python:3.14-alpine3.22
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN addgroup --system bracket && \
    adduser --system bracket --ingroup bracket && \
    chown bracket:bracket /app
USER bracket

# Install dependencies before copying the source so this layer is only
# rebuilt when the lockfile changes
COPY --chown=bracket:bracket pyproject.toml uv.lock ./
RUN uv sync --no-dev --locked

COPY --chown=bracket:bracket . /app

EXPOSE 8400

HEALTHCHECK --interval=3s --timeout=5s --retries=10 \
    CMD ["wget", "-O", "/dev/null", "http://0.0.0.0:8400/ping"]

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
