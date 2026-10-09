import pytest

from postgres_mcp.server import parse_args


def test_env_config_and_cli_precedence(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "9000")
    monkeypatch.setenv("MCP_ACCESS_MODE", "restricted")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp.example.test:8000")
    args = parse_args([])
    assert (args.transport, args.streamable_http_host, args.streamable_http_port) == ("streamable-http", "0.0.0.0", 9000)
    assert args.sse_host == "0.0.0.0"
    assert args.access_mode == "restricted"
    assert args.allowed_hosts == "mcp.example.test:8000"
    args = parse_args(["--transport", "stdio", "--streamable-http-port", "8000", "--access-mode", "unrestricted"])
    assert (args.transport, args.streamable_http_port, args.access_mode) == ("stdio", 8000, "unrestricted")


@pytest.mark.parametrize("name,value", [("MCP_PORT", "0"), ("MCP_PORT", "bogus"), ("MCP_TRANSPORT", "bad"), ("MCP_ACCESS_MODE", "bad")])
def test_invalid_env_fails_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit):
        parse_args([])
