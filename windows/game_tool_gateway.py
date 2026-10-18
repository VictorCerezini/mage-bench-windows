"""Loopback-only, allow-listed MCP forwarding and player-view tracing."""

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def validate_loopback_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("The game bridge must be an HTTP endpoint on 127.0.0.1")


class GameToolGateway:
    def __init__(self, upstream, allowed_tools, trace_path, max_calls=400):
        validate_loopback_url(upstream)
        self.upstream = upstream
        self.allowed = set(allowed_tools)
        self.trace_path = trace_path
        self.max_calls = max_calls
        self.call_count = 0
        self.violations = []
        self.lock = threading.Lock()
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(405)
                self.end_headers()

            def do_DELETE(self):
                self.send_response(202)
                self.end_headers()

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                method = payload.get("method")
                params = payload.get("params", {})
                if method == "tools/call":
                    tool = params.get("name")
                    with gateway.lock:
                        gateway.call_count += 1
                        count = gateway.call_count
                        if tool not in gateway.allowed:
                            gateway.violations.append(tool)
                    if tool not in gateway.allowed or count > gateway.max_calls:
                        error = {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "error": {"code": -32601, "message": "Tool not permitted or pilot call limit exceeded"},
                        }
                        body = json.dumps(error).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(body)
                        return
                started = time.monotonic()
                req = urllib.request.Request(  # noqa: S310 - constructor restricts upstream to loopback HTTP
                    gateway.upstream, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
                )
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                try:
                    with opener.open(req, timeout=180) as response:
                        status = response.status
                        body = response.read()
                except urllib.error.HTTPError as exc:
                    status, body = exc.code, exc.read()
                result = json.loads(body) if body else None
                if method == "tools/list" and result and "result" in result:
                    result["result"]["tools"] = [
                        tool for tool in result["result"]["tools"] if tool["name"] in gateway.allowed
                    ]
                    for tool in result["result"]["tools"]:
                        read_only = tool["name"].startswith("get_")
                        tool["annotations"] = {
                            "readOnlyHint": read_only,
                            "destructiveHint": tool["name"] == "concede",
                            "openWorldHint": False,
                            "idempotentHint": read_only,
                        }
                    body = json.dumps(result).encode()
                if method == "tools/call":
                    record = {
                        "ts": datetime.now(UTC).isoformat(),
                        "tool": params["name"],
                        "arguments": params.get("arguments", {}),
                        "latency_seconds": round(time.monotonic() - started, 3),
                        "response": result,
                    }
                    with gateway.lock, gateway.trace_path.open("a", encoding="utf-8") as file:
                        file.write(json.dumps(record, separators=(",", ":")) + "\n")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
