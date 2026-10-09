# Postgres MCP

An MCP server for querying and inspecting PostgreSQL databases. Supports native Streamable HTTP, SSE, and stdio.

## Run with Docker

Set `DATABASE_URI` privately in an environment file, then run:

```sh
docker run --rm -p 127.0.0.1:8000:8000 \
  --env-file /path/to/private.env ghcr.io/damjee/postgres-mcp:latest
```

Connect an MCP client to `http://localhost:8000/mcp`. `/health` reports process liveness, not database readiness. Pin an image digest when a fixed version is required.

## Configuration

- `DATABASE_URI`: PostgreSQL connection URI or libpq connection string
- `MCP_TRANSPORT`: `streamable-http` (container default), `sse`, or `stdio`
- `MCP_HOST` / `MCP_PORT`: listener address and port; container defaults are `0.0.0.0` and `8000`
- `MCP_ACCESS_MODE`: `restricted` (container default) or `unrestricted`
- `MCP_ALLOWED_HOSTS` / `MCP_ALLOWED_ORIGINS`: additional trusted HTTP hosts and browser origins; localhost is allowed by default
- `MCP_HEALTH_PORT`: health-check port override when a different port is supplied by CLI

CLI options include `--transport`, `--access-mode`, `--streamable-http-host`, `--streamable-http-port`, `--sse-host`, `--sse-port`, `--allowed-hosts`, and `--allowed-origins`. CLI options override matching environment settings. `DATABASE_URI` takes precedence over a positional connection string.

SSE uses `/sse`. For stdio, use `docker run --rm -i --no-healthcheck` and append `--transport stdio` to the image command.

## Security

Use a genuinely read-only database role with restricted mode. The server has no built-in authentication or TLS; keep it on a trusted, access-controlled network. Host/origin checks are not authentication. Never commit credentials or private deployment configuration.

## Development

```sh
uv sync --frozen
uv run pytest
docker build -t postgres-mcp:test .
uv run python scripts/container_smoke.py
```

CI builds and tests pull requests and publishes tested main builds to GHCR. MIT licensed; see [LICENSE](LICENSE).
