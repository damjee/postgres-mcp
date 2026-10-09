"""Probe the HTTP process without database credentials or extra dependencies."""

import os
import sys
import urllib.request

# CLI overrides can select a different port. Set MCP_HEALTH_PORT in that case.
if os.environ.get("MCP_TRANSPORT", "streamable-http") == "stdio":
    sys.exit(0)
port = int(os.environ.get("MCP_HEALTH_PORT", os.environ.get("MCP_PORT", "8000")))
with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
    sys.exit(0 if response.status == 200 else 1)
