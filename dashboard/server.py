#!/usr/bin/env python3
"""
AI Search Blog Optimiser — local dashboard server.

Acts as both:
1. An MCP server (stdio) exposing `open_dashboard`, `register_run`, `update_state`, `list_runs`, `get_actions` tools.
2. A local HTTP server on a free port serving the dashboard HTML and a JSON state API.

The MCP side lets Claude agents push state updates. The HTTP side lets the user's
browser render the live dashboard and POST accept/reject decisions back.

Stdlib only. Works on macOS Python 3.8+. Cross-platform where possible.
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths + state
# ---------------------------------------------------------------------------
#
# Important: in Claude Cowork, ${CLAUDE_PLUGIN_ROOT} is mounted READ-ONLY for
# sub-agents. Static assets (HTML, CSS, fonts, logos) can be served from there,
# but all WRITABLE state (runs, brand voice artefacts, decisions) must live in
# a user-writable location. Default: ~/.ai-search-blog-optimiser/. Override with
# --data-dir or the AI_SEARCH_BLOG_OPTIMISER_DATA env var.

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
DASHBOARD_DIR = PLUGIN_ROOT / "dashboard"

DATA_DIR = Path(os.environ.get("AI_SEARCH_BLOG_OPTIMISER_DATA", Path.home() / ".ai-search-blog-optimiser"))
RUNS_DIR = DATA_DIR / "runs"
BRANDS_DIR = DATA_DIR / "brands"

STATE_LOCK = threading.RLock()
HTTP_SERVER: socketserver.TCPServer | None = None
HTTP_PORT: int | None = None
SERVER_THREAD: threading.Thread | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for MCP JSON-RPC)."""
    print(f"[dashboard-server] {msg}", file=sys.stderr, flush=True)


def _free_port() -> int:
    """Find a free TCP port by binding to port 0."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _atomic_write(path: Path, data: str) -> None:
    """Write file atomically via .tmp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_json(path: Path, data: Any) -> None:
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))


def _list_runs() -> list[dict]:
    """List all runs in the runs/ directory, newest first."""
    if not RUNS_DIR.exists():
        return []
    entries: list[dict] = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        state_file = run_dir / "state.json"
        state = _read_json(state_file) or {}
        entries.append({
            "run_id": run_dir.name,
            "path": str(run_dir),
            "state": state,
        })
    return entries


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve dashboard HTML + a small JSON API, handle POST actions.

    Routes:
      GET  /                         → latest run's dashboard (or run-picker if none)
      GET  /runs/{run_id}/           → specific run dashboard
      GET  /api/runs                 → list of all runs (JSON)
      GET  /api/runs/{run_id}/state  → state.json for a run
      GET  /api/runs/{run_id}/articles/{slug}  → article record
      GET  /api/runs/{run_id}/recommendations/{slug}  → recs for an article
      POST /api/runs/{run_id}/actions  → accept/reject/approve action
      GET  /static/...               → static assets (CSS, JS, fonts, images)

    Everything else falls through to SimpleHTTPRequestHandler serving from DASHBOARD_DIR.
    """

    def log_message(self, format, *args):  # type: ignore[override]
        _log(f"HTTP: {format % args}")

    # ---- routing -----------------------------------------------------------

    def do_GET(self):  # type: ignore[override]
        try:
            path = self.path.split("?")[0].rstrip("/")
            if path == "" or path == "/":
                return self._serve_latest_or_picker()
            if path == "/api/runs":
                return self._serve_json(_list_runs())
            if path.startswith("/api/runs/"):
                return self._serve_run_api(path)
            if path.startswith("/runs/"):
                return self._serve_run_index(path)
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/health":
                return self._serve_json({"status": "ok", "version": "0.1.0"})
            return self._serve_static("index.html")
        except Exception as e:
            _log(f"GET {self.path} failed: {e}\n{traceback.format_exc()}")
            self.send_error(500, str(e))

    def do_POST(self):  # type: ignore[override]
        try:
            path = self.path.split("?")[0].rstrip("/")
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body) if body else {}
            if path.startswith("/api/runs/") and path.endswith("/actions"):
                return self._handle_action(path, payload)
            self.send_error(404, "Not Found")
        except Exception as e:
            _log(f"POST {self.path} failed: {e}\n{traceback.format_exc()}")
            self.send_error(500, str(e))

    # ---- serving -----------------------------------------------------------

    def _serve_latest_or_picker(self):
        runs = _list_runs()
        if runs:
            run_id = runs[0]["run_id"]
            self.send_response(302)
            self.send_header("Location", f"/runs/{run_id}/")
            self.end_headers()
            return
        return self._serve_static("welcome.html")

    def _serve_run_index(self, path: str):
        # /runs/{run_id}/ → serves dashboard/index.html
        return self._serve_static("index.html")

    def _serve_static(self, relative: str):
        target = DASHBOARD_DIR / relative
        if not target.exists() or not target.is_file():
            # fall back to index.html for SPA-style routing
            target = DASHBOARD_DIR / "index.html"
            if not target.exists():
                self.send_error(404, "Dashboard assets not found")
                return
        content = target.read_bytes()
        ext = target.suffix.lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
        }.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _serve_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_run_api(self, path: str):
        # /api/runs/{run_id}/state
        # /api/runs/{run_id}/articles/{slug}
        # /api/runs/{run_id}/recommendations/{slug}
        # /api/runs/{run_id}/decisions
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            self.send_error(400, "Malformed API path")
            return
        # parts = ["api", "runs", "{run_id}", "state", ...]
        run_id = parts[2]
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists() or not run_dir.is_dir():
            self.send_error(404, f"Run {run_id} not found")
            return

        remainder = parts[3:]
        if remainder == ["state"]:
            state = _read_json(run_dir / "state.json") or {}
            return self._serve_json(state)
        if remainder == ["decisions"]:
            decisions = _read_json(run_dir / "decisions.json") or {}
            return self._serve_json(decisions)
        if len(remainder) == 2 and remainder[0] == "articles":
            data = _read_json(run_dir / "articles" / f"{remainder[1]}.json")
            if data is None:
                self.send_error(404, "Article not found")
                return
            return self._serve_json(data)
        if len(remainder) == 2 and remainder[0] == "recommendations":
            data = _read_json(run_dir / "recommendations" / f"{remainder[1]}.json")
            if data is None:
                self.send_error(404, "Recommendations not found")
                return
            return self._serve_json(data)
        if len(remainder) >= 2 and remainder[0] == "optimised":
            # Serve files under runs/{run_id}/optimised/ (HTML preview, media)
            rel = "/".join(remainder[1:])
            target = (run_dir / "optimised" / rel).resolve()
            if not str(target).startswith(str((run_dir / "optimised").resolve())):
                self.send_error(403, "Path traversal rejected")
                return
            if not target.exists() or not target.is_file():
                self.send_error(404, "File not found")
                return
            ext = target.suffix.lower()
            ctype = {
                ".html": "text/html; charset=utf-8",
                ".md": "text/markdown; charset=utf-8",
                ".json": "application/json",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(404, "Unknown API route")

    # ---- actions -----------------------------------------------------------

    def _handle_action(self, path: str, payload: dict):
        parts = path.strip("/").split("/")
        run_id = parts[2]
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            self.send_error(404, "Run not found")
            return
        action_type = payload.get("action")
        if action_type not in {"accept", "reject", "approve", "reject_article", "rerun_article", "set_brand_role"}:
            self.send_error(400, f"Unknown action: {action_type}")
            return
        slug = payload.get("slug")
        rec_id = payload.get("rec_id")

        decisions_path = run_dir / "decisions.json"
        with STATE_LOCK:
            decisions = _read_json(decisions_path) or {"articles": {}}
            article_decisions = decisions["articles"].setdefault(slug or "_global", {"recs": {}, "approved": False})
            if action_type in {"accept", "reject"} and rec_id:
                article_decisions["recs"][rec_id] = action_type
            if action_type == "approve":
                article_decisions["approved"] = True
            if action_type == "reject_article":
                article_decisions["rejected"] = True
            if action_type == "rerun_article":
                article_decisions["rerun_requested"] = True
            if action_type == "set_brand_role":
                decisions["brand_role_override"] = payload.get("role")
            decisions["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _write_json(decisions_path, decisions)
        self._serve_json({"ok": True, "decisions": decisions})


# ---------------------------------------------------------------------------
# HTTP server lifecycle
# ---------------------------------------------------------------------------

class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_http_server() -> int:
    global HTTP_SERVER, HTTP_PORT, SERVER_THREAD
    if HTTP_SERVER is not None and HTTP_PORT is not None:
        return HTTP_PORT
    port = _free_port()
    HTTP_SERVER = ReusableTCPServer(("127.0.0.1", port), DashboardRequestHandler)
    HTTP_PORT = port
    SERVER_THREAD = threading.Thread(target=HTTP_SERVER.serve_forever, name="dashboard-http", daemon=True)
    SERVER_THREAD.start()
    _log(f"HTTP server listening on http://127.0.0.1:{port}/")
    return port


def stop_http_server() -> None:
    global HTTP_SERVER, HTTP_PORT
    if HTTP_SERVER is not None:
        HTTP_SERVER.shutdown()
        HTTP_SERVER.server_close()
        HTTP_SERVER = None
        HTTP_PORT = None


# ---------------------------------------------------------------------------
# MCP server (stdio JSON-RPC)
# ---------------------------------------------------------------------------
#
# Minimal stdio MCP implementation. Exposes tools that agents can call:
#   - open_dashboard: start the HTTP server (if not running), open the user's browser
#   - register_run: initialise a new runs/{ts}/ directory with an empty state.json
#   - update_state: merge a state fragment into runs/{ts}/state.json
#   - list_runs: return all runs
#   - get_decisions: return runs/{ts}/decisions.json
#   - get_dashboard_url: return the HTTP server URL (starting it if needed)
#
# Follows the MCP protocol 2024-11-05 (stdio transport). Responses are minimal but spec-compliant.

MCP_TOOLS = [
    {
        "name": "open_dashboard",
        "description": "Start the local dashboard HTTP server (if not running) and open the user's default browser to it. Call this at the start of every pipeline run. Returns the URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Optional run id; dashboard will land on this run's view."},
                "open_browser": {"type": "boolean", "description": "Whether to auto-open the browser. Default true.", "default": True},
            },
        },
    },
    {
        "name": "get_dashboard_url",
        "description": "Return the URL of the dashboard HTTP server, starting it if necessary.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "register_run",
        "description": "Initialise a new run directory at {data_dir}/runs/{run_id}/. Creates state.json and all sub-directories (articles/, recommendations/, optimised/, media/, raw/, gaps/, competitors/, peec-cache/). Returns run_id, absolute run path, data_dir, and brands_dir — USE THESE absolute paths in all subsequent sub-agent file operations. The plugin install dir is read-only; all writes must go under data_dir (defaults to ~/.ai-search-blog-optimiser/).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blog_url": {"type": "string"},
                "brand_name": {"type": "string"},
                "peec_project_id": {"type": "string"},
                "role": {"type": "string", "enum": ["own", "competitor", "unknown"]},
            },
            "required": ["blog_url"],
        },
    },
    {
        "name": "get_paths",
        "description": "Return the absolute data_dir, brands_dir, and — if run_id is provided — the run_dir. Use this at the start of any sub-agent that reads/writes files to avoid hard-coding paths. Run state files live under {data_dir}/runs/{run_id}/, brand-voice artefacts under {data_dir}/brands/{peec_project_id}/.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
        },
    },
    {
        "name": "update_state",
        "description": "Merge a state fragment into runs/{run_id}/state.json. Writes atomically. Fragment is a dict that is deep-merged into the existing state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "fragment": {"type": "object"},
            },
            "required": ["run_id", "fragment"],
        },
    },
    {
        "name": "list_runs",
        "description": "List all runs in the runs/ directory (newest first) with their state summary.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_decisions",
        "description": "Return the current decisions.json for a run (user accept/reject/approve actions).",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "show_banner",
        "description": "Display a banner in the dashboard (e.g. prereq-missing warning, Peec cold-start notice). Adds to state.banners[].",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "warn", "error"]},
                "message": {"type": "string"},
                "action_url": {"type": "string"},
                "action_label": {"type": "string"},
            },
            "required": ["run_id", "severity", "message"],
        },
    },
]


def _deep_merge(dst: dict, src: dict) -> dict:
    """Deep-merge src into dst. Special-cases the `articles` key: merges by `slug`
    so agents can send partial updates for individual articles without replacing
    the whole list. All other lists replace wholesale."""
    for k, v in src.items():
        if k == "articles" and isinstance(v, list) and isinstance(dst.get(k), list):
            existing = {a.get("slug"): a for a in dst[k] if isinstance(a, dict)}
            order = [a.get("slug") for a in dst[k] if isinstance(a, dict)]
            for incoming in v:
                if not isinstance(incoming, dict):
                    continue
                slug = incoming.get("slug")
                if slug in existing:
                    _deep_merge(existing[slug], incoming)
                else:
                    existing[slug] = incoming
                    order.append(slug)
            dst[k] = [existing[s] for s in order if s in existing]
        elif k == "banners" and isinstance(v, list) and isinstance(dst.get(k), list):
            # Banners are append-only; never clobber existing list.
            dst[k] = dst[k] + v
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _tool_open_dashboard(args: dict) -> dict:
    port = start_http_server()
    url = f"http://127.0.0.1:{port}/"
    run_id = args.get("run_id")
    if run_id:
        url = f"http://127.0.0.1:{port}/runs/{run_id}/"
    if args.get("open_browser", True):
        try:
            webbrowser.open(url)
        except Exception as e:
            _log(f"Could not open browser: {e}")
    return {"url": url, "port": port}


def _tool_get_dashboard_url(_args: dict) -> dict:
    port = start_http_server()
    return {"url": f"http://127.0.0.1:{port}/", "port": port}


def _tool_register_run(args: dict) -> dict:
    run_id = time.strftime("%Y-%m-%dT%H-%M-%S", time.gmtime())
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("articles", "recommendations", "optimised", "media", "raw", "gaps", "competitors", "peec-cache"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    # Ensure the brands dir is ready for the voice-extractor.
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    initial_state = {
        "run_id": run_id,
        "blog_url": args.get("blog_url"),
        "brand": {
            "name": args.get("brand_name"),
            "peec_project_id": args.get("peec_project_id"),
            "role": args.get("role", "unknown"),
        },
        "paths": {
            "data_dir": str(DATA_DIR),
            "run_dir": str(run_dir),
            "brands_dir": str(BRANDS_DIR),
        },
        "pipeline": {
            "crawl": {"status": "pending"},
            "voice": {"status": "pending"},
            "recommend": {"status": "pending"},
            "generate": {"status": "pending"},
        },
        "articles": [],
        "banners": [],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(run_dir / "state.json", initial_state)
    return {"run_id": run_id, "path": str(run_dir), "data_dir": str(DATA_DIR), "brands_dir": str(BRANDS_DIR)}


def _tool_update_state(args: dict) -> dict:
    run_id = args["run_id"]
    fragment = args["fragment"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _read_json(state_path) or {}
        _deep_merge(state, fragment)
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_json(state_path, state)
    return {"ok": True}


def _tool_list_runs(_args: dict) -> dict:
    return {"runs": _list_runs()}


def _tool_get_decisions(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    decisions = _read_json(run_dir / "decisions.json") or {"articles": {}}
    return decisions


def _tool_show_banner(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _read_json(state_path) or {}
        banners = state.setdefault("banners", [])
        banners.append({
            "severity": args["severity"],
            "message": args["message"],
            "action_url": args.get("action_url"),
            "action_label": args.get("action_label"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_json(state_path, state)
    return {"ok": True}


def _tool_get_paths(args: dict) -> dict:
    run_id = args.get("run_id")
    paths = {
        "data_dir": str(DATA_DIR),
        "runs_dir": str(RUNS_DIR),
        "brands_dir": str(BRANDS_DIR),
        "dashboard_dir": str(DASHBOARD_DIR),
        "plugin_root": str(PLUGIN_ROOT),
    }
    if run_id:
        run_dir = RUNS_DIR / run_id
        if run_dir.exists():
            paths["run_dir"] = str(run_dir)
            paths["articles_dir"] = str(run_dir / "articles")
            paths["recommendations_dir"] = str(run_dir / "recommendations")
            paths["optimised_dir"] = str(run_dir / "optimised")
            paths["media_dir"] = str(run_dir / "media")
            paths["gaps_dir"] = str(run_dir / "gaps")
            paths["competitors_dir"] = str(run_dir / "competitors")
            paths["peec_cache_dir"] = str(run_dir / "peec-cache")
            paths["state_json"] = str(run_dir / "state.json")
            paths["decisions_json"] = str(run_dir / "decisions.json")
        else:
            paths["run_dir"] = None
            paths["error"] = f"Run {run_id} does not exist"
    return paths


TOOL_DISPATCH = {
    "open_dashboard": _tool_open_dashboard,
    "get_dashboard_url": _tool_get_dashboard_url,
    "register_run": _tool_register_run,
    "update_state": _tool_update_state,
    "list_runs": _tool_list_runs,
    "get_decisions": _tool_get_decisions,
    "show_banner": _tool_show_banner,
    "get_paths": _tool_get_paths,
}


def _mcp_response(id_: Any, result: Any = None, error: dict | None = None) -> dict:
    response = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    return response


def _mcp_loop() -> None:
    """Read JSON-RPC messages from stdin, dispatch, write to stdout."""
    _log(f"MCP server starting (plugin root: {PLUGIN_ROOT})")
    # The HTTP server lazily starts on first use.
    initialised = False
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"Could not decode message: {e}")
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "blog-optimiser-dashboard", "version": "0.1.0"},
                }
                _send(_mcp_response(msg_id, result))
                initialised = True
            elif method == "notifications/initialized":
                continue  # no response expected
            elif method == "tools/list":
                _send(_mcp_response(msg_id, {"tools": MCP_TOOLS}))
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if name not in TOOL_DISPATCH:
                    _send(_mcp_response(msg_id, error={"code": -32601, "message": f"Unknown tool: {name}"}))
                    continue
                try:
                    output = TOOL_DISPATCH[name](arguments)
                    _send(_mcp_response(msg_id, {
                        "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, indent=2)}],
                        "isError": False,
                    }))
                except Exception as e:
                    _log(f"Tool {name} failed: {e}\n{traceback.format_exc()}")
                    _send(_mcp_response(msg_id, {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    }))
            elif method == "ping":
                _send(_mcp_response(msg_id, {}))
            elif method == "resources/list":
                _send(_mcp_response(msg_id, {"resources": []}))
            elif method == "prompts/list":
                _send(_mcp_response(msg_id, {"prompts": []}))
            else:
                if msg_id is not None:
                    _send(_mcp_response(msg_id, error={"code": -32601, "message": f"Method not found: {method}"}))
        except Exception as e:
            _log(f"Error handling {method}: {e}\n{traceback.format_exc()}")
            if msg_id is not None:
                _send(_mcp_response(msg_id, error={"code": -32603, "message": str(e)}))
    _log("MCP stdin closed, shutting down")
    stop_http_server()


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    global PLUGIN_ROOT, RUNS_DIR, BRANDS_DIR, DATA_DIR, DASHBOARD_DIR, HTTP_SERVER, HTTP_PORT

    parser = argparse.ArgumentParser(description="AI Search Blog Optimiser dashboard server")
    parser.add_argument("--plugin-root", type=str, default=str(PLUGIN_ROOT),
                        help="Absolute path to the plugin root (defaults to CLAUDE_PLUGIN_ROOT env). Read-only in Cowork sandbox — assets only.")
    parser.add_argument("--data-dir", type=str,
                        default=os.environ.get("AI_SEARCH_BLOG_OPTIMISER_DATA", str(Path.home() / ".ai-search-blog-optimiser")),
                        help="Writable data directory for runs/ and brands/ (default: ~/.ai-search-blog-optimiser/).")
    parser.add_argument("--http-only", action="store_true",
                        help="Skip MCP, run HTTP only (for local dev and QA).")
    parser.add_argument("--port", type=int, default=0,
                        help="Fixed HTTP port (0 = auto). --http-only only.")
    args = parser.parse_args()

    PLUGIN_ROOT = Path(args.plugin_root).resolve()
    DASHBOARD_DIR = PLUGIN_ROOT / "dashboard"
    DATA_DIR = Path(args.data_dir).expanduser().resolve()
    RUNS_DIR = DATA_DIR / "runs"
    BRANDS_DIR = DATA_DIR / "brands"

    # Verify writability up-front — this is the root cause of v0.1.0 failures.
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        BRANDS_DIR.mkdir(parents=True, exist_ok=True)
        # Write a probe file to confirm the dir is actually writable.
        probe = DATA_DIR / ".writable-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        _log(f"FATAL: data dir {DATA_DIR} is not writable: {e}")
        _log("Set --data-dir or AI_SEARCH_BLOG_OPTIMISER_DATA to a writable path.")
        sys.exit(2)

    _log(f"plugin_root (read-only assets): {PLUGIN_ROOT}")
    _log(f"data_dir (writable state):      {DATA_DIR}")

    if args.http_only:
        # Dev/QA mode: serve the dashboard on a fixed port without MCP stdio.
        port = args.port or _free_port()
        HTTP_SERVER = ReusableTCPServer(("127.0.0.1", port), DashboardRequestHandler)
        HTTP_PORT = port
        _log(f"[http-only] serving http://127.0.0.1:{port}/ (Ctrl-C to stop)")
        try:
            HTTP_SERVER.serve_forever()
        except KeyboardInterrupt:
            _log("interrupted, shutting down")
        finally:
            stop_http_server()
        return

    try:
        _mcp_loop()
    except KeyboardInterrupt:
        stop_http_server()


if __name__ == "__main__":
    main()
