"""Tests for erp-service Streamable HTTP MCP transport."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import threading
import urllib.request

from erp_service.mcp_server import build_arg_parser, make_http_handler


def test_arg_parser_defaults_and_http_flags():
    d = build_arg_parser().parse_args([])
    assert d.transport == "stdio"
    h = build_arg_parser().parse_args(["--transport", "streamable-http", "--port", "9001"])
    assert h.transport == "streamable-http"
    assert h.port == 9001


def test_streamable_http_health_and_tools_list():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_http_handler())
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as r:
            assert r.status == 200
            health = json.loads(r.read().decode())
            assert health["status"] == "ok"
            assert health["transport"] == "streamable-http"

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
            body = json.loads(r.read().decode())
            names = {tool["name"] for tool in body["result"]["tools"]}
            assert {"erp.warehouse.analyze", "erp.shipper.digest", "erp.inventory.plan"}.issubset(names)
    finally:
        srv.shutdown()
        srv.server_close()
