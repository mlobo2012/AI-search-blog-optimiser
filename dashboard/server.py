#!/usr/bin/env python3
"""
AI Search Blog Optimiser — local dashboard server (v0.2.0).

Two run modes:
  - Default (MCP stdio): Claude Cowork spawns this as its MCP server. The MCP
    side exposes tools for agents to push state updates. HTTP side runs as a
    DETACHED subprocess so it survives MCP restarts.
  - --http-daemon: long-lived HTTP server. Spawned by the MCP on first need;
    survives MCP lifecycle (idle kill, plugin reload, session transitions).
    Writes PID + port to ~/.ai-search-blog-optimiser/dashboard.lock.

Why detached: in Cowork, MCP stdio servers get killed on idle/session-boundary.
If the HTTP server were a thread in the MCP process, the browser tab would
break. Detached daemon keeps the dashboard alive regardless.

Stdlib only. Works on macOS Python 3.8+. Cross-platform where possible.
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
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
LOCK_FILE = DATA_DIR / "dashboard.lock"

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
            if path.startswith("/api/runs/") and path.endswith("/gate"):
                return self._handle_gate(path, payload)
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
        if remainder == ["gates"]:
            gates = _read_json(run_dir / "gates.json") or {}
            return self._serve_json(gates)
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

    def _handle_gate(self, path: str, payload: dict):
        """POST /api/runs/{run_id}/gate body: {"gate": "crawl_gate"|"voice_gate"|"recommend_gate", "action": "proceed"|"hold", "note": "..."}"""
        parts = path.strip("/").split("/")
        run_id = parts[2]
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            self.send_error(404, "Run not found")
            return
        gate_name = payload.get("gate")
        gate_action = payload.get("action", "proceed")
        note = payload.get("note")
        if not gate_name:
            self.send_error(400, "gate name required")
            return
        gates_path = run_dir / "gates.json"
        with STATE_LOCK:
            gates = _read_json(gates_path) or {}
            gate = gates.setdefault(gate_name, {})
            gate["status"] = "resolved"
            gate["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            gate["user_action"] = gate_action
            if note:
                gate["user_note"] = note
            _write_json(gates_path, gates)
        self._serve_json({"ok": True, "gates": gates})

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


# ---------------------------------------------------------------------------
# Detached HTTP daemon lifecycle
# ---------------------------------------------------------------------------

def _read_lock() -> dict | None:
    """Read the dashboard lock file if present."""
    if not LOCK_FILE.exists():
        return None
    try:
        return json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_lock(pid: int, port: int) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(json.dumps({
        "pid": pid,
        "port": port,
        "plugin_root": str(PLUGIN_ROOT),
        "data_dir": str(DATA_DIR),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2), encoding="utf-8")


def _clear_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    """True if a process with pid is still running."""
    try:
        os.kill(pid, 0)  # signal 0 = check existence
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    return True


def _daemon_healthy(port: int) -> bool:
    """Ping the daemon's /health endpoint."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as resp:
            if resp.status != 200:
                return False
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("status") == "ok"
    except Exception:
        return False


def _spawn_detached_daemon() -> tuple[int, int]:
    """Spawn this same script with --http-daemon as a fully detached subprocess.
    Returns (pid, port) once the daemon writes the lock file.
    """
    # Pick a port here so we can return it immediately (daemon uses --port).
    port = _free_port()
    args = [
        sys.executable,
        os.path.abspath(__file__),
        "--http-daemon",
        "--plugin-root", str(PLUGIN_ROOT),
        "--data-dir", str(DATA_DIR),
        "--port", str(port),
    ]
    # Fully detach: new session, stdin/out/err to /dev/null.
    # close_fds=True + start_new_session=True severs the lifecycle from the MCP.
    devnull = subprocess.DEVNULL
    # On macOS/Linux: start_new_session detaches from the parent's process group.
    # Windows is not supported by this plugin.
    proc = subprocess.Popen(
        args,
        stdin=devnull,
        stdout=devnull,
        stderr=devnull,
        close_fds=True,
        start_new_session=True,
    )
    # Wait up to 5s for the daemon to come up and write its lock.
    deadline = time.time() + 5
    while time.time() < deadline:
        if _daemon_healthy(port):
            _write_lock(proc.pid, port)
            _log(f"Spawned detached HTTP daemon pid={proc.pid} port={port}")
            return proc.pid, port
        time.sleep(0.1)
    # If we got here, the daemon didn't come up. Kill and fail.
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    raise RuntimeError(f"Detached HTTP daemon failed to start on port {port} within 5s")


def ensure_dashboard_running() -> tuple[int, int]:
    """Guarantee a detached dashboard HTTP daemon is running.
    Returns (pid, port). Reuses an existing daemon if still alive+healthy.
    """
    lock = _read_lock()
    if lock:
        pid = int(lock.get("pid", 0))
        port = int(lock.get("port", 0))
        if pid and port and _pid_alive(pid) and _daemon_healthy(port):
            # Existing daemon is good. Reuse.
            return pid, port
        # Stale lock: daemon died or port is dead.
        _log(f"Stale dashboard lock (pid={pid} port={port}); respawning")
        _clear_lock()
    return _spawn_detached_daemon()


def start_http_server() -> int:
    """MCP-side entry: makes sure a detached daemon is running, returns its port."""
    _pid, port = ensure_dashboard_running()
    return port


def stop_http_server() -> None:
    """MCP-side cleanup — does NOT kill the detached daemon (user expects it to survive)."""
    global HTTP_SERVER, HTTP_PORT
    if HTTP_SERVER is not None:
        HTTP_SERVER.shutdown()
        HTTP_SERVER.server_close()
        HTTP_SERVER = None
        HTTP_PORT = None


def kill_detached_daemon() -> bool:
    """Explicit shutdown for `--stop-dashboard`. Returns True if killed."""
    lock = _read_lock()
    if not lock:
        return False
    pid = int(lock.get("pid", 0))
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait up to 2s for graceful exit
            for _ in range(20):
                if not _pid_alive(pid):
                    break
                time.sleep(0.1)
            if _pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _clear_lock()
    return True


def run_http_daemon(port: int) -> None:
    """Long-lived HTTP daemon. Spawned by the MCP via --http-daemon.
    Exits only on SIGTERM/SIGINT. Does NOT do MCP stdio.
    """
    global HTTP_SERVER, HTTP_PORT
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    HTTP_SERVER = ReusableTCPServer(("127.0.0.1", port), DashboardRequestHandler)
    HTTP_PORT = port
    _write_lock(os.getpid(), port)

    def _shutdown(signum, frame):
        try:
            if HTTP_SERVER is not None:
                HTTP_SERVER.shutdown()
        finally:
            _clear_lock()
            sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    try:
        HTTP_SERVER.serve_forever()
    finally:
        _clear_lock()


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
        "description": "Return the absolute data_dir, brands_dir, and — if run_id is provided — the run_dir, articles_dir, recommendations_dir, optimised_dir, media_dir, raw_dir, gaps_dir, competitors_dir, peec_cache_dir, state_json, decisions_json, gates_json, run_summary_md. Use this at the start of the slash command to resolve every path you'll pass to sub-agents — never hard-code relative paths.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
        },
    },
    {
        "name": "set_gate",
        "description": "Write/update a gate in gates.json for the run. Used by the main session to pause the pipeline for human review. status='pending' opens the gate (dashboard shows Continue button); status='resolved' closes it (auto-proceed used internally when timeout).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "gate": {"type": "string", "description": "e.g. 'crawl_gate', 'voice_gate', 'recommend_gate'"},
                "status": {"type": "string", "enum": ["pending", "resolved"]},
                "prompt": {"type": "string", "description": "Message shown to user in dashboard when gate is pending"},
                "user_action": {"type": "string", "description": "Only when status=resolved; usually 'proceed'"},
            },
            "required": ["run_id", "gate", "status"],
        },
    },
    {
        "name": "get_gates",
        "description": "Return current gates.json for a run. Main session polls this while waiting for the user's Continue click in the dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
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
    # Seed empty gates.json and decisions.json so agents and dashboard can read them without 404s.
    _write_json(run_dir / "gates.json", {})
    _write_json(run_dir / "decisions.json", {"articles": {}})
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
        "lock_file": str(LOCK_FILE),
    }
    if run_id:
        run_dir = RUNS_DIR / run_id
        if run_dir.exists():
            paths["run_dir"] = str(run_dir)
            paths["articles_dir"] = str(run_dir / "articles")
            paths["recommendations_dir"] = str(run_dir / "recommendations")
            paths["optimised_dir"] = str(run_dir / "optimised")
            paths["media_dir"] = str(run_dir / "media")
            paths["raw_dir"] = str(run_dir / "raw")
            paths["gaps_dir"] = str(run_dir / "gaps")
            paths["competitors_dir"] = str(run_dir / "competitors")
            paths["peec_cache_dir"] = str(run_dir / "peec-cache")
            paths["state_json"] = str(run_dir / "state.json")
            paths["decisions_json"] = str(run_dir / "decisions.json")
            paths["gates_json"] = str(run_dir / "gates.json")
            paths["run_summary_md"] = str(run_dir / "run-summary.md")
        else:
            paths["run_dir"] = None
            paths["error"] = f"Run {run_id} does not exist"
    return paths


def _tool_set_gate(args: dict) -> dict:
    """Main session writes/resolves a gate. gates.json is source of truth; dashboard polls it."""
    run_id = args["run_id"]
    gate_name = args["gate"]
    status = args.get("status", "pending")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    gates_path = run_dir / "gates.json"
    with STATE_LOCK:
        gates = _read_json(gates_path) or {}
        gate = gates.setdefault(gate_name, {})
        gate["status"] = status
        gate["prompt"] = args.get("prompt", gate.get("prompt", ""))
        if status == "pending":
            gate["pending_since"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            gate["resolved_at"] = None
            gate["user_action"] = None
        elif status == "resolved":
            gate["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            gate["user_action"] = args.get("user_action", "proceed")
        _write_json(gates_path, gates)
    return {"ok": True, "gate": gate}


def _tool_get_gates(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    gates = _read_json(run_dir / "gates.json") or {}
    return gates


TOOL_DISPATCH = {
    "open_dashboard": _tool_open_dashboard,
    "get_dashboard_url": _tool_get_dashboard_url,
    "register_run": _tool_register_run,
    "update_state": _tool_update_state,
    "list_runs": _tool_list_runs,
    "get_decisions": _tool_get_decisions,
    "show_banner": _tool_show_banner,
    "get_paths": _tool_get_paths,
    "set_gate": _tool_set_gate,
    "get_gates": _tool_get_gates,
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
    global PLUGIN_ROOT, RUNS_DIR, BRANDS_DIR, DATA_DIR, DASHBOARD_DIR, LOCK_FILE, HTTP_SERVER, HTTP_PORT

    parser = argparse.ArgumentParser(description="AI Search Blog Optimiser dashboard server")
    parser.add_argument("--plugin-root", type=str, default=str(PLUGIN_ROOT),
                        help="Absolute path to the plugin root (defaults to CLAUDE_PLUGIN_ROOT env). Read-only in Cowork sandbox — assets only.")
    parser.add_argument("--data-dir", type=str,
                        default=os.environ.get("AI_SEARCH_BLOG_OPTIMISER_DATA", str(Path.home() / ".ai-search-blog-optimiser")),
                        help="Writable data directory for runs/ and brands/ (default: ~/.ai-search-blog-optimiser/).")
    parser.add_argument("--http-only", action="store_true",
                        help="Dev/QA: HTTP only, no MCP, runs in foreground (old v0.1 behaviour).")
    parser.add_argument("--http-daemon", action="store_true",
                        help="Long-lived detached HTTP daemon. Spawned by the MCP via --http-daemon. Writes dashboard.lock. Does NOT do MCP stdio.")
    parser.add_argument("--stop-dashboard", action="store_true",
                        help="Kill any running detached HTTP daemon and clear the lock.")
    parser.add_argument("--port", type=int, default=0,
                        help="Fixed HTTP port (0 = auto).")
    args = parser.parse_args()

    PLUGIN_ROOT = Path(args.plugin_root).resolve()
    DASHBOARD_DIR = PLUGIN_ROOT / "dashboard"
    DATA_DIR = Path(args.data_dir).expanduser().resolve()
    RUNS_DIR = DATA_DIR / "runs"
    BRANDS_DIR = DATA_DIR / "brands"
    LOCK_FILE = DATA_DIR / "dashboard.lock"

    # Verify writability up-front.
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        BRANDS_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".writable-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        _log(f"FATAL: data dir {DATA_DIR} is not writable: {e}")
        _log("Set --data-dir or AI_SEARCH_BLOG_OPTIMISER_DATA to a writable path.")
        sys.exit(2)

    if args.stop_dashboard:
        killed = kill_detached_daemon()
        _log("daemon stopped" if killed else "no running daemon")
        return

    if args.http_daemon:
        # Detached long-lived HTTP daemon. Does NOT do MCP stdio.
        port = args.port or _free_port()
        _log(f"[http-daemon] pid={os.getpid()} port={port} plugin_root={PLUGIN_ROOT}")
        run_http_daemon(port)
        return

    if args.http_only:
        # Dev/QA: foreground HTTP without MCP.
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

    _log(f"plugin_root (read-only assets): {PLUGIN_ROOT}")
    _log(f"data_dir (writable state):      {DATA_DIR}")
    _log(f"lock_file:                      {LOCK_FILE}")
    try:
        _mcp_loop()
    except KeyboardInterrupt:
        stop_http_server()


if __name__ == "__main__":
    main()
