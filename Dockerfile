# Locked application dependencies; native MCP Streamable HTTP, SSE, and stdio.
FROM ghcr.io/astral-sh/uv:0.6.9 AS uv
FROM python:3.12-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/damjee/postgres-mcp" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.description="Postgres MCP with native Streamable HTTP (Crystal DBA upstream)"
RUN groupadd --system app && useradd --system --gid app app
WORKDIR /app
COPY --from=builder /app /app
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh
COPY scripts/healthcheck.py /app/healthcheck.py
ENV PATH="/app/.venv/bin:$PATH" \
    MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8000 MCP_ACCESS_MODE=restricted
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["python", "/app/healthcheck.py"]
ENTRYPOINT ["/app/docker-entrypoint.sh", "postgres-mcp"]
