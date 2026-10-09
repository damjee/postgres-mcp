"""Acceptance tests against a real Docker image and disposable PostgreSQL.

No production connection is used; credentials are generated for each invocation.
Docker absence is a hard failure, never a skipped acceptance test.
"""

import asyncio
import os
import secrets
import time

import docker
import httpx
import psycopg
from mcp import ClientSession
from mcp import StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from psycopg import sql
from psycopg.conninfo import make_conninfo

IMAGE = os.environ.get("SMOKE_IMAGE", "postgres-mcp:test")
client = docker.from_env()
client.ping()
suffix = secrets.token_hex(5)
network = client.networks.create(f"mcp-smoke-{suffix}")
assert network.name is not None
network_name = network.name
containers = []
admin_password = secrets.token_urlsafe(24)
reader_password = secrets.token_urlsafe(24)


def wait_for(predicate, description, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (httpx.HTTPError, psycopg.OperationalError):
            pass
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for {description}")


def start_mcp(user, password, transport="streamable-http", command=None):
    # libpq keyword format avoids embedded URI secrets in committed examples.
    connection = make_conninfo(host=db.name, dbname="smoke", user=user, password=password)
    container = client.containers.run(
        IMAGE,
        command=command,
        detach=True,
        network=network_name,
        environment={"DATABASE_URI": connection, "MCP_TRANSPORT": transport, "MCP_ALLOWED_HOSTS": "mcp.example.test:8000"},
        ports={"8000/tcp": ("127.0.0.1", 0)},
    )
    containers.append(container)
    container.reload()
    url = f"http://127.0.0.1:{container.ports['8000/tcp'][0]['HostPort']}"
    wait_for(lambda: httpx.get(url + "/health").status_code == 200, "MCP liveness")
    assert container.attrs["Config"]["User"] == "app"
    return container, url


async def check_session(session, writes=True):
    result = await session.initialize()
    assert result.serverInfo.name == "postgres-mcp"
    listed = await session.list_tools()
    assert "execute_sql" in [tool.name for tool in listed.tools]
    query = await session.call_tool("execute_sql", {"sql": "SELECT value FROM smoke_check ORDER BY value"})
    text = " ".join(item.text for item in query.content if item.type == "text")
    assert "original" in text and "Error:" not in text, text
    if writes:
        statements = [
            "INSERT INTO smoke_check VALUES ('changed')",
            "UPDATE smoke_check SET value = 'changed'",
            "DELETE FROM smoke_check",
            "CREATE TABLE forbidden_write (id int)",
            "DROP TABLE smoke_check",
            "SELECT 1; DELETE FROM smoke_check",
            "WITH deleted AS (DELETE FROM smoke_check RETURNING *) SELECT * FROM deleted",
        ]
        for statement in statements:
            result = await session.call_tool("execute_sql", {"sql": statement})
            text = " ".join(item.text for item in result.content if item.type == "text")
            assert result.isError or "Error:" in text, f"Restricted mode accepted: {statement}: {text}"
        result = await session.call_tool("explain_query", {"sql": "DELETE FROM smoke_check", "analyze": True})
        text = " ".join(item.text for item in result.content if item.type == "text")
        assert result.isError or "Error:" in text, text


async def check_http(url):
    async with streamablehttp_client(url + "/mcp", headers={"Host": "mcp.example.test:8000"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await check_session(session)
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    assert httpx.post(url + "/mcp", headers={**headers, "Host": "attacker.invalid"}, json={}).status_code == 421
    assert httpx.post(url + "/mcp", headers={**headers, "Origin": "https://attacker.invalid"}, json={}).status_code == 403


async def check_sse(url):
    async with sse_client(url + "/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await check_session(session, writes=False)


async def check_stdio():
    environment = dict(os.environ)
    environment["DATABASE_URI"] = make_conninfo(host=db.name, dbname="smoke", user="smoke_reader", password=reader_password)
    params = StdioServerParameters(
        command="docker",
        args=["run", "--rm", "-i", "--network", network_name, "-e", "DATABASE_URI", IMAGE, "--transport", "stdio"],
        env=environment,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await check_session(session, writes=False)


try:
    db = client.containers.run(
        "postgres:16-bookworm",
        name=f"mcp-db-{suffix}",
        detach=True,
        network=network_name,
        environment={"POSTGRES_PASSWORD": admin_password, "POSTGRES_DB": "smoke"},
        ports={"5432/tcp": ("127.0.0.1", 0)},
    )
    containers.append(db)
    db.reload()
    port = db.ports["5432/tcp"][0]["HostPort"]
    admin_info = make_conninfo(host="127.0.0.1", port=port, dbname="smoke", user="postgres", password=admin_password)
    connection = wait_for(lambda: psycopg.connect(admin_info, autocommit=True), "PostgreSQL")
    with connection:
        connection.execute("CREATE TABLE smoke_check (value text)")
        connection.execute("INSERT INTO smoke_check VALUES ('original')")
        connection.execute(sql.SQL("CREATE ROLE smoke_reader LOGIN PASSWORD {}").format(sql.Literal(reader_password)))
        connection.execute("GRANT CONNECT ON DATABASE smoke TO smoke_reader")
        connection.execute("GRANT USAGE ON SCHEMA public TO smoke_reader")
        connection.execute("GRANT SELECT ON smoke_check TO smoke_reader")
        reader_info = make_conninfo(host="127.0.0.1", port=port, dbname="smoke", user="smoke_reader", password=reader_password)
        with psycopg.connect(reader_info, autocommit=True) as reader:
            try:
                reader.execute("INSERT INTO smoke_check VALUES ('forbidden')")
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError("Database read-only role unexpectedly permits writes")
        # Test application restrictions independently with a write-capable DB role,
        # then the intended least-privileged deployment configuration.
        for user, password in [("postgres", admin_password), ("smoke_reader", reader_password)]:
            container, endpoint = start_mcp(user, password)
            asyncio.run(check_http(endpoint))
            assert connection.execute("SELECT value FROM smoke_check").fetchall() == [("original",)]
            assert connection.execute("SELECT to_regclass('forbidden_write')").fetchone() == (None,)
            health = container.exec_run(["python", "/app/healthcheck.py"])
            assert health.exit_code == 0
            logs = container.logs().decode()
            assert admin_password not in logs and reader_password not in logs, "Credential leaked into MCP logs"
            container.stop(timeout=10)
        _, endpoint = start_mcp("smoke_reader", reader_password, command=["--transport", "sse"])
        asyncio.run(check_sse(endpoint))
        asyncio.run(check_stdio())
    print("PASS: Docker startup, non-root, health, native /mcp initialize, SQL reads, restricted writes, DB grants, Host/Origin, SSE, stdio")
finally:
    for container in reversed(containers):
        container.remove(force=True, v=True)
    network.remove()
