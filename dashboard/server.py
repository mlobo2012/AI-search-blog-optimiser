#!/usr/bin/env python3
"""
AI Search Blog Optimiser — local dashboard server (v0.5.6).

Two run modes:
  - Default (MCP stdio): Claude Cowork spawns this as its MCP server. The MCP
    side exposes tools for run bootstrap and state pushes. HTTP side runs as a
    DETACHED subprocess so it survives MCP restarts.
  - --http-daemon: long-lived HTTP server. Spawned by the MCP on first need;
    survives MCP lifecycle (idle kill, plugin reload, session transitions).
    Writes PID + port to the plugin data root's dashboard.lock.

Why detached: in Cowork, MCP stdio servers get killed on idle/session-boundary.
If the HTTP server were a thread in the MCP process, the browser tab would
break. Detached daemon keeps the dashboard alive regardless.

Stdlib only. Works on macOS Python 3.8+. Cross-platform where possible.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import http.server
import json
import os
import re
import signal
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

try:
    from dashboard.quality_gate import build_article_manifest
except ImportError:
    from quality_gate import build_article_manifest

# ---------------------------------------------------------------------------
# Paths + state
# ---------------------------------------------------------------------------
#
# Important: in Claude Cowork, ${CLAUDE_PLUGIN_ROOT} is mounted READ-ONLY for
# sub-agents. Static assets (HTML, CSS, fonts, logos) can be served from there,
# but all WRITABLE state (runs, voice baselines, gates) must live in a
# user-writable location. Default roots are platform-native and versioned under
# v3. Override with BLOG_OPTIMISER_DATA_ROOT for tests/dev only.

VERSION = "0.5.6"
DEFAULT_GATE_TIMEOUT_SECONDS = 300
BUNDLE_READ_ROOTS = ("references", "skills")
JSON_STRINGISH_PREFIXES = tuple('{["-0123456789tfn')
CRAWL_DISCOVERED_RE = re.compile(r"Crawler discovered (\d+) articles?")
LEGACY_DRAFT_STATUS_MAP = {
    "blocked": "failed",
    "completed": "completed",
    "draft_completed": "completed",
    "draft_failed": "failed",
    "failed": "failed",
    "generating": "running",
    "pending_validation": "running",
    "ready_for_review": "completed",
    "running": "running",
}


def _default_data_dir() -> Path:
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "ai-search-blog-optimiser" / "v3"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ai-search-blog-optimiser" / "v3"
    return Path.home() / ".local" / "share" / "ai-search-blog-optimiser" / "v3"


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _legacy_import_marker(data_dir: Path) -> Path:
    return data_dir / ".legacy-import.json"


def _write_legacy_import_marker(data_dir: Path, payload: dict[str, Any]) -> None:
    marker = _legacy_import_marker(data_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _import_legacy_runtime_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = _legacy_import_marker(data_dir)
    if marker.exists():
        return

    if _truthy_env("BLOG_OPTIMISER_SKIP_LEGACY_IMPORT"):
        _write_legacy_import_marker(data_dir, {
            "status": "skipped",
            "reason": "disabled-by-env",
            "at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        return

    legacy_dir = _default_data_dir()
    if legacy_dir == data_dir:
        _write_legacy_import_marker(data_dir, {
            "status": "skipped",
            "reason": "same-path",
            "at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        return

    if any(data_dir.iterdir()):
        _write_legacy_import_marker(data_dir, {
            "status": "skipped",
            "reason": "target-not-empty",
            "at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        return

    imported_paths: list[str] = []
    if legacy_dir.exists():
        for name in ("runs", "sites"):
            source = legacy_dir / name
            target = data_dir / name
            if not source.exists():
                continue
            shutil.copytree(source, target, dirs_exist_ok=True)
            imported_paths.append(name)

    _write_legacy_import_marker(data_dir, {
        "status": "imported" if imported_paths else "skipped",
        "reason": "copied" if imported_paths else "legacy-missing",
        "at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(legacy_dir),
        "copied_paths": imported_paths,
    })


def _resolve_data_dir() -> Path:
    override = os.environ.get("BLOG_OPTIMISER_DATA_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        data_dir = Path(plugin_data).expanduser().resolve()
        _import_legacy_runtime_data(data_dir)
        return data_dir
    return _default_data_dir()

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
DASHBOARD_DIR = PLUGIN_ROOT / "dashboard"

DATA_DIR = _resolve_data_dir()
RUNS_DIR = DATA_DIR / "runs"
SITES_DIR = DATA_DIR / "sites"
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


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically via .tmp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _coerce_json_payload(value: Any) -> tuple[Any, bool]:
    current = value
    changed = False
    for _ in range(4):
        if not isinstance(current, str):
            return current, changed
        candidate = current.strip()
        if not candidate or candidate[0].lower() not in JSON_STRINGISH_PREFIXES:
            return current, changed
        try:
            current = json.loads(candidate)
        except json.JSONDecodeError:
            return current, changed
        changed = True
    return current, changed


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    normalized, changed = _coerce_json_payload(data)
    if changed:
        try:
            _write_json(path, normalized)
        except Exception:
            pass
    return normalized


def _write_json(path: Path, data: Any) -> None:
    normalized, _ = _coerce_json_payload(data)
    _atomic_write(path, json.dumps(normalized, indent=2, ensure_ascii=False))


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(timestamp: Any) -> datetime | None:
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _normalize_timeout_seconds(value: Any) -> int:
    try:
        timeout_seconds = int(value)
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_GATE_TIMEOUT_SECONDS
    return max(1, min(timeout_seconds, 3600))


def _slugify_site_key(host: str) -> str:
    host = host.strip().lower()
    return host[4:] if host.startswith("www.") else host


def _canonicalize_blog_url(blog_url: str) -> str:
    parsed = urlparse(blog_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid blog URL: {blog_url}")
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    canonical = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        params="",
        query="",
        fragment="",
    )
    return urlunparse(canonical)


def _site_key_from_blog_url(blog_url: str) -> str:
    parsed = urlparse(blog_url)
    if not parsed.hostname:
        raise ValueError(f"Invalid blog URL: {blog_url}")
    return _slugify_site_key(parsed.hostname)


def _site_paths(site_key: str) -> dict[str, Path]:
    site_dir = SITES_DIR / site_key
    return {
        "site_dir": site_dir,
        "voice_markdown_path": site_dir / "brand-voice.md",
        "voice_meta_path": site_dir / "voice.json",
        "reviewers_path": site_dir / "reviewers.json",
    }


def _ensure_site_scaffold(site_key: str) -> dict[str, Path]:
    site_paths = _site_paths(site_key)
    site_paths["site_dir"].mkdir(parents=True, exist_ok=True)
    if not site_paths["reviewers_path"].exists():
        _write_json(site_paths["reviewers_path"], [])
    return site_paths


def _output_paths(run_dir: Path) -> dict[str, Path]:
    outputs_dir = run_dir / "outputs"
    return {
        "outputs_dir": outputs_dir,
        "articles_dir": outputs_dir / "articles",
        "evidence_dir": outputs_dir / "evidence",
        "recommendations_dir": outputs_dir / "recommendations",
        "optimised_dir": outputs_dir / "optimised",
        "media_dir": outputs_dir / "media",
        "raw_dir": outputs_dir / "raw",
        "gaps_dir": outputs_dir / "gaps",
        "competitors_dir": outputs_dir / "competitors",
        "peec_cache_dir": outputs_dir / "peec-cache",
    }


def _build_run_paths(run_dir: Path) -> dict[str, str]:
    output_paths = _output_paths(run_dir)
    paths: dict[str, str] = {
        "run_dir": str(run_dir),
        "state_path": str(run_dir / "state.json"),
        "gates_path": str(run_dir / "gates.json"),
        "run_summary_path": str(run_dir / "run-summary.md"),
    }
    paths.update({key: str(value) for key, value in output_paths.items()})
    return paths


def _next_run_id() -> str:
    base = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    candidate = base
    counter = 1
    while (RUNS_DIR / candidate).exists():
        candidate = f"{base}-{counter:02d}"
        counter += 1
    return candidate


def _read_voice_baseline(site_key: str, refresh_voice: bool) -> dict[str, Any]:
    paths = _site_paths(site_key)
    voice_meta = _read_json(paths["voice_meta_path"])
    exists = False
    if isinstance(voice_meta, dict) and voice_meta.get("site_key") == site_key and paths["voice_markdown_path"].exists():
        exists = True
    baseline = {
        "exists": exists,
        "site_key_match": exists,
        "will_reuse": exists and not refresh_voice,
        "site_dir": str(paths["site_dir"]),
        "markdown_path": str(paths["voice_markdown_path"]),
        "meta_path": str(paths["voice_meta_path"]),
        "summary": voice_meta.get("summary") if exists else None,
        "updated_at": voice_meta.get("updated_at") if exists else None,
        "source_run_id": voice_meta.get("source_run_id") if exists else None,
    }
    return baseline


def _list_runs() -> list[dict]:
    """List all runs in the runs/ directory, newest first."""
    if not RUNS_DIR.exists():
        return []
    entries: list[dict] = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        state_file = run_dir / "state.json"
        state = _load_state(state_file)
        entries.append({
            "run_id": run_dir.name,
            "path": str(run_dir),
            "state": state,
        })
    return entries


ARTIFACT_NAMESPACES = [
    "run",
    "site",
    "articles",
    "evidence",
    "recommendations",
    "optimised",
    "raw",
    "gaps",
    "competitors",
    "peec_cache",
    "media",
]

JSON_WRITE_NAMESPACES = [
    "site",
    "articles",
    "evidence",
    "recommendations",
    "optimised",
    "gaps",
    "competitors",
    "peec_cache",
]


def _artifact_base_dir(run_id: str, namespace: str) -> Path:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        raise ValueError(f"Run {run_id} does not exist")
    state = _load_state(run_dir / "state.json")
    output_paths = _output_paths(run_dir)
    mapping = {
        "run": run_dir,
        "site": Path(
            (state.get("outputs") or {}).get("site_dir")
            or _site_paths(state.get("site_key", ""))["site_dir"]
        ),
        "articles": output_paths["articles_dir"],
        "evidence": output_paths["evidence_dir"],
        "recommendations": output_paths["recommendations_dir"],
        "optimised": output_paths["optimised_dir"],
        "raw": output_paths["raw_dir"],
        "gaps": output_paths["gaps_dir"],
        "competitors": output_paths["competitors_dir"],
        "peec_cache": output_paths["peec_cache_dir"],
        "media": output_paths["media_dir"],
    }
    if namespace not in mapping:
        raise ValueError(f"Unknown artifact namespace: {namespace}")
    return mapping[namespace].resolve()


def _resolve_artifact_path(run_id: str, namespace: str, relative_path: str) -> tuple[Path, Path]:
    if not relative_path:
        raise ValueError("relative_path is required")
    relative = Path(relative_path)
    if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
        raise ValueError(f"Unsafe relative_path: {relative_path}")
    base_dir = _artifact_base_dir(run_id, namespace)
    target = (base_dir / relative).resolve()
    if not str(target).startswith(str(base_dir) + os.sep):
        raise ValueError(f"Path escapes namespace root: {relative_path}")
    return base_dir, target


def _resolve_bundle_path(relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("relative_path is required")
    relative = Path(relative_path)
    if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
        raise ValueError(f"Unsafe relative_path: {relative_path}")
    if not relative.parts or relative.parts[0] not in BUNDLE_READ_ROOTS:
        allowed = ", ".join(sorted(BUNDLE_READ_ROOTS))
        raise ValueError(f"Bundle reads are limited to: {allowed}")
    plugin_root = PLUGIN_ROOT.resolve()
    target = (plugin_root / relative).resolve()
    if not str(target).startswith(str(plugin_root) + os.sep):
        raise ValueError(f"Path escapes plugin root: {relative_path}")
    return target


def _validate_text_write(namespace: str, relative_path: str) -> None:
    if namespace == "run" and relative_path != "run-summary.md":
        raise ValueError("run namespace text writes are limited to run-summary.md")
    if namespace == "site" and relative_path != "brand-voice.md":
        raise ValueError("site namespace text writes are limited to brand-voice.md")


def _validate_json_write(namespace: str, relative_path: str) -> None:
    if namespace == "run":
        raise ValueError("run namespace JSON writes are not allowed via artifact tools")
    if namespace == "site" and relative_path not in {"voice.json", "reviewers.json"}:
        raise ValueError("site namespace JSON writes are limited to voice.json and reviewers.json")


def _require_object(value: Any, label: str) -> dict[str, Any]:
    normalized, _ = _coerce_json_payload(value)
    if not isinstance(normalized, dict):
        raise ValueError(f"{label} must be a JSON object")
    return normalized


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _crawl_discovered_count(crawl: Any) -> int | None:
    if not isinstance(crawl, dict):
        return None
    for candidate in (
        crawl.get("discovered_count"),
        crawl.get("articles_found"),
    ):
        count = _safe_int(candidate)
        if count is not None:
            return max(0, count)
    detail = crawl.get("detail")
    if isinstance(detail, str):
        match = CRAWL_DISCOVERED_RE.search(detail)
        if match:
            return int(match.group(1))
    count = _safe_int(crawl.get("article_count"))
    if count is not None:
        return max(0, count)
    return None


def _article_thumbnail(article: dict[str, Any]) -> str | None:
    thumbnail = article.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail:
        return thumbnail
    media = article.get("media")
    if isinstance(media, dict):
        candidate = media.get("thumbnail")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _article_state_fragment(article: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    slug = article["slug"]
    fragment = dict(existing) if isinstance(existing, dict) else {"slug": slug}
    fragment["slug"] = slug
    if isinstance(article.get("url"), str) and article["url"]:
        fragment["url"] = article["url"]
    if isinstance(article.get("title"), str) and article["title"]:
        fragment["title"] = article["title"]
    thumbnail = _article_thumbnail(article)
    if thumbnail:
        fragment["thumbnail"] = thumbnail
    stages = fragment.setdefault("stages", {})
    if not isinstance(stages, dict):
        stages = {}
        fragment["stages"] = stages
    crawl_stage = stages.setdefault("crawl", {})
    if not isinstance(crawl_stage, dict):
        crawl_stage = {}
        stages["crawl"] = crawl_stage
    crawl_stage["status"] = "completed"
    structure = article.get("structure")
    if isinstance(structure, dict):
        word_count = _safe_int(structure.get("word_count"))
        if word_count is not None and word_count >= 0:
            crawl_stage["word_count"] = word_count
    return fragment


def _persisted_article_records(run_dir: Path) -> list[dict[str, Any]]:
    articles_dir = _output_paths(run_dir)["articles_dir"]
    records: list[dict[str, Any]] = []
    for path in sorted(articles_dir.glob("*.json")):
        payload = _read_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("slug"), str) and payload.get("slug"):
            records.append(payload)
    return records


def _render_markdown_preview(markdown: str) -> str:
    lines = (markdown or "").splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        text = " ".join(part.strip() for part in paragraph if part.strip())
        if text:
            blocks.append(f"<p>{html.escape(text)}</p>")
        paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        items = "".join(f"<li>{html.escape(item)}</li>" for item in list_items)
        blocks.append(f"<ul>{items}</ul>")
        list_items = []

    def flush_code() -> None:
        nonlocal code_lines
        if not code_lines:
            return
        code = html.escape("\n".join(code_lines))
        blocks.append(f"<pre><code>{code}</code></pre>")
        code_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            continue

        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            list_items.append(stripped[2:].strip())
            continue

        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    flush_code()
    return "\n".join(blocks)


def _render_article_preview_html(article: dict[str, Any]) -> str:
    title = article.get("title") or article.get("slug") or "Article"
    slug = article.get("slug") or ""
    author = ((article.get("trust") or {}).get("author") or {}).get("name") or "Unknown author"
    role = ((article.get("trust") or {}).get("author") or {}).get("role") or ""
    published_at = ((article.get("trust") or {}).get("published_at")) or ""
    word_count = ((article.get("structure") or {}).get("word_count")) or ""
    source_url = article.get("url") or ""
    body_md = article.get("body_md") or ""
    body_html = _render_markdown_preview(body_md)
    meta_bits = [bit for bit in [author, role, published_at, f"{word_count} words" if word_count else ""] if bit]
    meta_line = " · ".join(meta_bits)
    source_link = (
        f'<a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">Open original page</a>'
        if source_url
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)} · Source Preview</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #111827;
      --muted: #6b7280;
      --border: #e5e7eb;
      --surface: #f8fafc;
      --accent: #00aeef;
      --accent-soft: #e6f7fd;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: white;
      line-height: 1.6;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      margin-bottom: 32px;
      padding-bottom: 20px;
    }}
    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #0369a1;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 16px 0 10px;
      font-size: clamp(2rem, 5vw, 2.8rem);
      line-height: 1.1;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .meta a {{
      color: #0369a1;
    }}
    article h2 {{
      margin-top: 32px;
      font-size: 1.35rem;
    }}
    article h3 {{
      margin-top: 24px;
      font-size: 1.1rem;
    }}
    article p {{
      margin: 0 0 14px;
    }}
    article ul {{
      margin: 0 0 18px 20px;
    }}
    article pre {{
      overflow-x: auto;
      padding: 14px 16px;
      border-radius: 12px;
      background: #0f172a;
      color: #e2e8f0;
      font-size: 0.9rem;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">Captured article</div>
      <h1>{html.escape(title)}</h1>
      <div class="meta">{html.escape(meta_line)}{' · ' if meta_line and source_link else ''}{source_link}</div>
      <div class="meta" style="margin-top: 8px;">Slug: <code>{html.escape(slug)}</code></div>
    </header>
    <article>{body_html or '<p>No article body was captured for this run.</p>'}</article>
  </main>
</body>
</html>"""


def _hydrate_gates(run_dir: Path) -> dict[str, Any]:
    gates_path = run_dir / "gates.json"
    with STATE_LOCK:
        gates = _read_json(gates_path) or {}
        changed = False
        now = datetime.utcnow()
        for gate in gates.values():
            if not isinstance(gate, dict):
                continue
            timeout_seconds = _normalize_timeout_seconds(gate.get("timeout_seconds"))
            gate["timeout_seconds"] = timeout_seconds
            pending_since = _parse_iso(gate.get("pending_since"))
            if pending_since:
                expires_at = pending_since + timedelta(seconds=timeout_seconds)
                gate["expires_at"] = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if gate.get("status") == "pending" and now >= expires_at:
                    gate["status"] = "resolved"
                    gate["resolved_at"] = _now_iso()
                    gate["user_action"] = "timeout-auto-proceed"
                    changed = True
            elif gate.get("status") == "pending":
                gate["pending_since"] = _now_iso()
                gate["expires_at"] = (datetime.utcnow() + timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
                changed = True
        if changed:
            _write_json(gates_path, gates)
        return gates


def _refresh_pipeline_aggregates(state: dict[str, Any]) -> None:
    pipeline = state.setdefault("pipeline", {})
    articles = [article for article in state.get("articles", []) if isinstance(article, dict) and article.get("slug")]
    if not articles:
        return

    for stage_name in ("analysis", "evidence", "recommendations", "draft"):
        existing = pipeline.get(stage_name)
        aggregate = dict(existing) if isinstance(existing, dict) else {}
        statuses = [
            ((article.get("stages") or {}).get(stage_name) or {}).get("status", "pending")
            for article in articles
        ]
        total = len(statuses)
        completed = sum(status == "completed" for status in statuses)
        running = sum(status == "running" for status in statuses)
        failed = sum(status == "failed" for status in statuses)
        partial = sum(status == "partial" for status in statuses)

        if total and completed == total:
            status = "completed"
        elif running:
            status = "running"
        elif aggregate.get("status") == "running" and completed < total and not failed:
            status = "running"
        elif completed or failed or partial:
            status = "partial"
        else:
            status = "pending"

        aggregate["status"] = status
        aggregate["completed_articles"] = completed
        aggregate["total"] = total
        if failed:
            aggregate["failed_articles"] = failed
        else:
            aggregate.pop("failed_articles", None)
        pipeline[stage_name] = aggregate

    pipeline.setdefault("crawl", {})
    if isinstance(pipeline["crawl"], dict):
        pipeline["crawl"]["article_count"] = len(articles)


def _article_manifest_if_present(run_dir: Path, article_slug: str) -> dict[str, Any] | None:
    manifest_path = _output_paths(run_dir)["optimised_dir"] / f"{article_slug}.manifest.json"
    manifest = _read_json(manifest_path)
    return manifest if isinstance(manifest, dict) else None


def _article_terminal_label(article: dict[str, Any], manifest: dict[str, Any] | None = None) -> str:
    stages = article.get("stages") if isinstance(article.get("stages"), dict) else {}
    draft_stage = stages.get("draft") if isinstance(stages, dict) and isinstance(stages.get("draft"), dict) else {}
    if manifest and ((manifest.get("quality_gate") or {}).get("status") == "passed"):
        return "draft-ready"
    if draft_stage.get("status") == "completed" and draft_stage.get("quality_gate") == "passed":
        return "draft-ready"
    if draft_stage.get("status") == "failed":
        return "blocked"
    if draft_stage.get("status") == "running":
        return "drafting"
    if (stages.get("recommendations") or {}).get("status") == "completed":
        return "ready-to-draft"
    return "pending"


def _run_terminal_status(state: dict[str, Any]) -> str:
    articles = [item for item in state.get("articles", []) if isinstance(item, dict) and item.get("slug")]
    if not articles:
        return state.get("status", "running")

    terminal = 0
    passed = 0
    failed = 0
    for article in articles:
        draft_stage = ((article.get("stages") or {}).get("draft") or {})
        status = draft_stage.get("status")
        if status in {"completed", "failed"}:
            terminal += 1
        if status == "completed":
            passed += 1
        elif status == "failed":
            failed += 1

    if terminal < len(articles):
        return "running"
    if passed and failed:
        return "partial"
    if failed and not passed:
        return "failed"
    return "completed"


def _render_run_report(state: dict[str, Any], run_dir: Path) -> str:
    articles = [item for item in state.get("articles", []) if isinstance(item, dict) and item.get("slug")]
    draft_ready = 0
    blocked = 0
    lines = [
        "# AI Search Blog Optimiser Report",
        "",
        f"- Run ID: `{state.get('run_id', run_dir.name)}`",
        f"- Blog URL: {state.get('canonical_blog_url') or state.get('blog_url') or 'Unknown'}",
        f"- Generated at: {_now_iso()}",
        f"- Run status: `{_run_terminal_status(state)}`",
        "",
    ]

    if articles:
        for article in articles:
            manifest = _article_manifest_if_present(run_dir, str(article.get("slug")))
            label = _article_terminal_label(article, manifest)
            if label == "draft-ready":
                draft_ready += 1
            elif label == "blocked":
                blocked += 1
        lines.extend([
            "## Summary",
            "",
            f"- Articles processed: {len(articles)}",
            f"- Draft-ready: {draft_ready}",
            f"- Blocked: {blocked}",
            "",
            "## Articles",
            "",
        ])
        for article in articles:
            slug = str(article.get("slug"))
            title = str(article.get("title") or slug)
            draft_stage = ((article.get("stages") or {}).get("draft") or {})
            manifest = _article_manifest_if_present(run_dir, slug)
            label = _article_terminal_label(article, manifest)
            blocker = ""
            if manifest:
                blocker = next(iter((manifest.get("quality_gate") or {}).get("blocking_issues") or []), "")
            if not blocker:
                blocker = str(draft_stage.get("blocker_summary") or "")
            lines.append(f"- `{slug}`: {title} [{label}]")
            if blocker:
                lines.append(f"  Reason: {blocker}")
        lines.append("")
    else:
        lines.extend([
            "## Summary",
            "",
            "- No article records were persisted for this run.",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve dashboard HTML + a small JSON API, handle gate POSTs.

    Routes:
      GET  /                         → home / history page
      GET  /runs/{run_id}/           → specific run dashboard
      GET  /api/runs                 → list of all runs (JSON)
      GET  /api/runs/{run_id}/state  → state.json for a run
      GET  /api/runs/{run_id}/articles/{slug}  → article record
      GET  /api/runs/{run_id}/article-preview/{slug}.html  → rendered source article preview
      GET  /api/runs/{run_id}/evidence/{slug}  → evidence pack for an article
      GET  /api/runs/{run_id}/recommendations/{slug}  → recs for an article
      POST /api/runs/{run_id}/gate  → resolve a human review gate
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
                return self._serve_home()
            if path == "/api/runs":
                return self._serve_json(_list_runs())
            if path.startswith("/api/runs/"):
                return self._serve_run_api(path)
            if path.startswith("/runs/"):
                return self._serve_run_index(path)
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/health":
                return self._serve_json({"status": "ok", "version": VERSION})
            self.send_error(404, "Not Found")
        except Exception as e:
            _log(f"GET {self.path} failed: {e}\n{traceback.format_exc()}")
            self.send_error(500, str(e))

    def do_POST(self):  # type: ignore[override]
        try:
            path = self.path.split("?")[0].rstrip("/")
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body) if body else {}
            if path.startswith("/api/runs/") and path.endswith("/gate"):
                return self._handle_gate(path, payload)
            self.send_error(404, "Not Found")
        except Exception as e:
            _log(f"POST {self.path} failed: {e}\n{traceback.format_exc()}")
            self.send_error(500, str(e))

    # ---- serving -----------------------------------------------------------

    def _serve_home(self):
        return self._serve_static("welcome.html")

    def _serve_run_index(self, path: str):
        # /runs/{run_id}/ → serves dashboard/index.html
        parts = path.strip("/").split("/")
        if len(parts) < 2:
            self.send_error(400, "Malformed run path")
            return
        run_id = parts[1]
        if not (RUNS_DIR / run_id).exists():
            self.send_error(404, f"Run {run_id} not found")
            return
        return self._serve_static("index.html")

    def _serve_static(self, relative: str):
        target = DASHBOARD_DIR / relative
        if not target.exists() or not target.is_file():
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
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html_string(self, content: str, status: int = 200):
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_run_api(self, path: str):
        # /api/runs/{run_id}/state
        # /api/runs/{run_id}/articles/{slug}
        # /api/runs/{run_id}/article-preview/{slug}.html
        # /api/runs/{run_id}/evidence/{slug}
        # /api/runs/{run_id}/recommendations/{slug}
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
            state = _load_state(run_dir / "state.json")
            return self._serve_json(state)
        if remainder == ["gates"]:
            gates = _hydrate_gates(run_dir)
            return self._serve_json(gates)
        output_paths = _output_paths(run_dir)
        if len(remainder) == 2 and remainder[0] == "articles":
            data = _read_json(output_paths["articles_dir"] / f"{remainder[1]}.json")
            if data is None:
                self.send_error(404, "Article not found")
                return
            return self._serve_json(data)
        if len(remainder) == 2 and remainder[0] == "evidence":
            data = _read_json(output_paths["evidence_dir"] / f"{remainder[1]}.json")
            if data is None:
                self.send_error(404, "Evidence not found")
                return
            return self._serve_json(data)
        if len(remainder) == 2 and remainder[0] == "article-preview":
            slug = remainder[1]
            if slug.endswith(".html"):
                slug = slug[:-5]
            data = _read_json(output_paths["articles_dir"] / f"{slug}.json")
            if data is None:
                self.send_error(404, "Article not found")
                return
            return self._serve_html_string(_render_article_preview_html(data))
        if len(remainder) == 2 and remainder[0] == "recommendations":
            data = _read_json(output_paths["recommendations_dir"] / f"{remainder[1]}.json")
            if data is None:
                self.send_error(404, "Recommendations not found")
                return
            return self._serve_json(data)
        if len(remainder) >= 2 and remainder[0] in {"optimised", "media", "raw"}:
            # Serve files under runs/{run_id}/outputs/... (HTML previews, media).
            rel = "/".join(remainder[1:])
            base_dir = output_paths[f"{remainder[0]}_dir"].resolve()
            target = (base_dir / rel).resolve()
            if not str(target).startswith(str(base_dir)):
                self.send_error(403, "Path traversal rejected")
                return
            if not target.exists() or not target.is_file():
                self.send_error(404, "File not found")
                return
            ext = target.suffix.lower()
            if ext == ".json":
                payload = _read_json(target)
                if payload is not None:
                    return self._serve_json(payload)
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

    # ---- gates -------------------------------------------------------------

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
            gate["resolved_at"] = _now_iso()
            gate["user_action"] = gate_action
            if note:
                gate["user_note"] = note
            _write_json(gates_path, gates)
        self._serve_json({"ok": True, "gates": gates})

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
        "started_at": _now_iso(),
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
    SITES_DIR.mkdir(parents=True, exist_ok=True)
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
#   - get_dashboard_url: return the HTTP server URL (starting it if needed)
#
# Follows the MCP protocol 2024-11-05 (stdio transport). Responses are minimal but spec-compliant.

MCP_TOOLS = [
    {
        "name": "open_dashboard",
        "description": "Start the local dashboard HTTP server (if not running) and open the user's default browser to a specific run dashboard. Requires a concrete run_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run id to open."},
                "open_browser": {"type": "boolean", "description": "Whether to auto-open the browser. Default true.", "default": True},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "get_dashboard_url",
        "description": "Return the home URL of the dashboard HTTP server, starting it if necessary.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "register_run",
        "description": "Initialise a new run directory at {data_dir}/runs/{run_id}/. Creates state.json, outputs/ sub-directories, and compatibility gate/report files. Peec is required for new runs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blog_url": {"type": "string"},
                "peec_project_id": {"type": "string"},
                "refresh_voice": {"type": "boolean", "default": False},
            },
            "required": ["blog_url", "peec_project_id"],
        },
    },
    {
        "name": "set_gate",
        "description": "Deprecated compatibility tool. Write/update a gate in gates.json for a run. The dashboard no longer uses gate-driven control flow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "gate": {"type": "string", "description": "e.g. 'crawl_gate', 'voice_gate', 'recommend_gate'"},
                "status": {"type": "string", "enum": ["pending", "resolved"]},
                "prompt": {"type": "string", "description": "Message shown to user in dashboard when gate is pending"},
                "timeout_seconds": {"type": "integer", "description": "Optional. Defaults to 300 seconds for pending gates.", "default": 300},
                "user_action": {"type": "string", "description": "Only when status=resolved; usually 'proceed'"},
            },
            "required": ["run_id", "gate", "status"],
        },
    },
    {
        "name": "get_gates",
        "description": "Deprecated compatibility tool. Return current gates.json for a run.",
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
        "name": "record_crawl_discovery",
        "description": "Persist the number of article URLs discovered during crawl before per-article fetches begin. Does not create article rows by itself.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "discovered_count": {"type": "integer", "minimum": 0},
            },
            "required": ["run_id", "discovered_count"],
        },
    },
    {
        "name": "record_crawled_article",
        "description": "Atomically write one captured article record to articles/{slug}.json and refresh its crawl stage in state.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article": {"type": "object"},
            },
            "required": ["run_id", "article"],
        },
    },
    {
        "name": "finalize_crawl",
        "description": "Reconcile crawl state against the real articles/*.json files on disk. Prunes ghost article rows, updates crawl counts, and returns the persisted slugs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "get_artifact_path",
        "description": "Resolve a safe absolute host path for a run artifact namespace. Use this when another MCP tool needs an output_path on the host machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "namespace": {"type": "string", "enum": ARTIFACT_NAMESPACES},
                "relative_path": {"type": "string"},
            },
            "required": ["run_id", "namespace", "relative_path"],
        },
    },
    {
        "name": "list_artifacts",
        "description": "List files already written under a run artifact namespace or the site namespace for that run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "namespace": {"type": "string", "enum": ARTIFACT_NAMESPACES},
                "suffix": {"type": "string", "description": "Optional filename suffix filter such as .json or .md"},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["run_id", "namespace"],
        },
    },
    {
        "name": "read_text_artifact",
        "description": "Read a UTF-8 text artifact from a run or site namespace on the host machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "namespace": {"type": "string", "enum": ARTIFACT_NAMESPACES},
                "relative_path": {"type": "string"},
                "max_chars": {"type": "integer", "default": 200000},
            },
            "required": ["run_id", "namespace", "relative_path"],
        },
    },
    {
        "name": "read_json_artifact",
        "description": "Read and parse a JSON artifact from a run or site namespace on the host machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "namespace": {"type": "string", "enum": ARTIFACT_NAMESPACES},
                "relative_path": {"type": "string"},
            },
            "required": ["run_id", "namespace", "relative_path"],
        },
    },
    {
        "name": "read_bundle_text",
        "description": "Read a UTF-8 text file bundled with the installed plugin. Use this for read-only plugin references such as references/*.md and skills/*/SKILL.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "relative_path": {"type": "string"},
                "max_chars": {"type": "integer", "default": 200000},
            },
            "required": ["relative_path"],
        },
    },
    {
        "name": "write_text_artifact",
        "description": "Write a UTF-8 text artifact into a run or site namespace on the host machine. Use this instead of Bash/Write for host-side run files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "namespace": {"type": "string", "enum": ["run", "site", "optimised", "raw"]},
                "relative_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["run_id", "namespace", "relative_path", "content"],
        },
    },
    {
        "name": "write_json_artifact",
        "description": "Write a JSON artifact into a run or site namespace on the host machine. Use this instead of Bash/Write for host-side run files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "namespace": {"type": "string", "enum": JSON_WRITE_NAMESPACES},
                "relative_path": {"type": "string"},
                "data": {},
            },
            "required": ["run_id", "namespace", "relative_path", "data"],
        },
    },
    {
        "name": "record_evidence_pack",
        "description": "Atomically write evidence/{slug}.json and refresh articles[].stages.evidence from the saved payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "evidence": {"type": "object"},
            },
            "required": ["run_id", "article_slug", "evidence"],
        },
    },
    {
        "name": "record_recommendations",
        "description": "Atomically write recommendations/{slug}.json, enforce the compact recommendation contract, and refresh articles[].stages.recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "recommendations": {"type": "object"},
            },
            "required": ["run_id", "article_slug", "recommendations"],
        },
    },
    {
        "name": "record_voice_baseline",
        "description": "Atomically write the site-scoped brand voice baseline and refresh pipeline.voice plus state.voice.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "markdown": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["run_id", "markdown", "metadata"],
        },
    },
    {
        "name": "record_peec_gap",
        "description": "Atomically write gaps/{slug}.json and refresh articles[].stages.analysis with Peec admissibility truth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "gap": {"type": "object"},
            },
            "required": ["run_id", "article_slug", "gap"],
        },
    },
    {
        "name": "record_competitor_snapshot",
        "description": "Atomically write competitors/{slug}.json and refresh articles[].stages.analysis with competitor comparison metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "snapshot": {"type": "object"},
            },
            "required": ["run_id", "article_slug", "snapshot"],
        },
    },
    {
        "name": "record_draft_package",
        "description": "Atomically write optimised draft artifacts for one article, run the validator, and refresh articles[].stages.draft from validator truth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "package": {"type": "object"},
            },
            "required": ["run_id", "article_slug", "package"],
        },
    },
    {
        "name": "fail_article_stage",
        "description": "Mark an article stage as failed/blocked with a truthful reason. Use this instead of inventing successful output when prerequisites or evidence do not support drafting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "stage": {"type": "string", "enum": ["analysis", "evidence", "recommendations", "draft"]},
                "reason": {"type": "string"},
                "detail": {"type": "string"},
                "code": {"type": "string"},
            },
            "required": ["run_id", "article_slug", "stage", "reason"],
        },
    },
    {
        "name": "finalize_run_report",
        "description": "Write the final run-summary.md report from disk truth and set the terminal run status accordingly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "validate_article",
        "description": "Deterministically validate one article's reviewer, evidence, HTML, and schema artifacts. Overwrites optimised/{slug}.manifest.json and refreshes draft stage truth in state.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slug": {"type": "string"},
                "audit_after": {"type": "integer"},
            },
            "required": ["run_id", "article_slug"],
        },
    },
    {
        "name": "validate_run",
        "description": "Deterministically validate every generated article in a run, overwriting manifest files and refreshing draft stage truth from validator output.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "article_slugs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "download_media_asset",
        "description": "Download a remote media URL into the run's media namespace on the host machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "source_url": {"type": "string"},
                "relative_path": {"type": "string"},
                "timeout_seconds": {"type": "integer", "default": 15},
            },
            "required": ["run_id", "source_url", "relative_path"],
        },
    },
    {
        "name": "list_runs",
        "description": "List all runs in the runs/ directory (newest first) with their state summary.",
        "inputSchema": {"type": "object", "properties": {}},
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


def _normalize_status_values(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "status" and isinstance(value, str) and value == "complete":
                node[key] = "completed"
            else:
                _normalize_status_values(value)
    elif isinstance(node, list):
        for item in node:
            _normalize_status_values(item)


def _merge_article_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        slug = fragment.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        if slug in merged:
            _deep_merge(merged[slug], fragment)
        else:
            merged[slug] = fragment
            order.append(slug)
    return [_normalize_article_fragment(merged[slug]) for slug in order]


def _normalize_article_fragment(article: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(article)
    draft_fields = {
        "audit_after",
        "audit_before",
        "draft_status",
        "generated_at",
        "quality_gate",
        "status",
        "validation_error",
    }
    stages = normalized.get("stages")
    has_draft_stage = isinstance(stages, dict) and isinstance(stages.get("draft"), dict)
    if not has_draft_stage and not any(field in normalized for field in draft_fields):
        return normalized

    if not isinstance(stages, dict):
        stages = {}
    else:
        stages = dict(stages)
    draft_stage = stages.get("draft")
    if not isinstance(draft_stage, dict):
        draft_stage = {}
    else:
        draft_stage = dict(draft_stage)
    stages["draft"] = draft_stage
    normalized["stages"] = stages

    for field in ("audit_before", "audit_after", "generated_at"):
        if normalized.get(field) is not None and field not in draft_stage:
            draft_stage[field] = normalized[field]

    quality_gate = normalized.get("quality_gate")
    if isinstance(quality_gate, str) and quality_gate and "quality_gate" not in draft_stage:
        draft_stage["quality_gate"] = quality_gate.lower()

    validation_error = normalized.get("validation_error")
    if isinstance(validation_error, str) and validation_error and "blocker_summary" not in draft_stage:
        draft_stage["blocker_summary"] = validation_error

    legacy_status = normalized.get("draft_status")
    if not legacy_status and isinstance(normalized.get("status"), str):
        legacy_status = normalized["status"]
    mapped_status = LEGACY_DRAFT_STATUS_MAP.get(str(legacy_status or "").lower())
    if not mapped_status and draft_stage.get("quality_gate") == "passed":
        mapped_status = "completed"
    elif not mapped_status and draft_stage.get("quality_gate") == "failed":
        mapped_status = "failed"
    elif not mapped_status and draft_stage.get("audit_after") is not None:
        mapped_status = "completed"
    elif not mapped_status and validation_error:
        mapped_status = "failed"
    if mapped_status and "status" not in draft_stage:
        draft_stage["status"] = mapped_status

    return normalized


def _normalize_state_fragment(fragment: Any) -> Any:
    if not isinstance(fragment, dict):
        return fragment

    normalized = dict(fragment)
    article_fragments: list[dict[str, Any]] = []

    incoming_articles = normalized.get("articles")
    if isinstance(incoming_articles, list):
        article_fragments.extend(item for item in incoming_articles if isinstance(item, dict))
    elif isinstance(incoming_articles, dict):
        for slug, article_data in incoming_articles.items():
            if not isinstance(article_data, dict):
                continue
            article_fragment = {"slug": slug}
            article_fragment.update(article_data)
            article_fragments.append(article_fragment)

    incoming_stage_map = normalized.pop("stages", None)
    if isinstance(incoming_stage_map, dict):
        for stage_name, per_article in incoming_stage_map.items():
            if not isinstance(per_article, dict):
                continue
            for slug, stage_payload in per_article.items():
                if not isinstance(stage_payload, dict):
                    continue
                article_fragments.append({
                    "slug": slug,
                    "stages": {
                        stage_name: stage_payload,
                    },
                })

    if article_fragments:
        normalized["articles"] = _merge_article_fragments(article_fragments)

    _normalize_status_values(normalized)
    return normalized


def _load_state(state_path: Path) -> dict[str, Any]:
    state = _read_json(state_path) or {}
    if not isinstance(state, dict):
        state = {}
    normalized = _normalize_state_fragment(state)
    if normalized != state:
        _write_json(state_path, normalized)
    return normalized


def _find_or_create_article(state: dict[str, Any], article_slug: str) -> dict[str, Any]:
    articles = state.setdefault("articles", [])
    for article in articles:
        if isinstance(article, dict) and article.get("slug") == article_slug:
            return article
    article = {"slug": article_slug, "stages": {}}
    articles.append(article)
    return article


def _tool_open_dashboard(args: dict) -> dict:
    run_id = args.get("run_id")
    if not run_id:
        raise ValueError("run_id is required for open_dashboard")
    if not (RUNS_DIR / run_id).exists():
        raise ValueError(f"Run {run_id} does not exist")
    port = start_http_server()
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
    blog_url = args["blog_url"]
    peec_project_id = str(args.get("peec_project_id") or "").strip()
    if not peec_project_id:
        raise ValueError("peec_project_id is required for register_run")
    canonical_blog_url = _canonicalize_blog_url(blog_url)
    site_key = _site_key_from_blog_url(canonical_blog_url)
    refresh_voice = bool(args.get("refresh_voice", False))
    run_id = _next_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_paths = _output_paths(run_dir)
    for path in output_paths.values():
        path.mkdir(parents=True, exist_ok=True)
    SITES_DIR.mkdir(parents=True, exist_ok=True)
    port = start_http_server()
    dashboard_url = f"http://127.0.0.1:{port}/runs/{run_id}/"
    voice_baseline = _read_voice_baseline(site_key, refresh_voice)
    site_paths = _ensure_site_scaffold(site_key)
    voice_mode = "reused" if voice_baseline["will_reuse"] else "pending"
    run_paths = _build_run_paths(run_dir)
    run_paths.update({
        "site_dir": str(site_paths["site_dir"]),
        "voice_markdown_path": str(site_paths["voice_markdown_path"]),
        "voice_meta_path": str(site_paths["voice_meta_path"]),
        "reviewers_path": str(site_paths["reviewers_path"]),
    })
    initial_state = {
        "run_id": run_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": "running",
        "blog_url": blog_url,
        "canonical_blog_url": canonical_blog_url,
        "site_key": site_key,
        "dashboard_url": dashboard_url,
        "peec_project": {
            "id": peec_project_id,
            "mode": "peec-required",
            "status": "connected",
            "required": True,
        },
        "session": {"mode": "fresh", "launched_at": _now_iso()},
        "voice_baseline": voice_baseline,
        "voice": {
            "mode": voice_mode,
            "source_run_id": voice_baseline.get("source_run_id") if voice_baseline["will_reuse"] else None,
            "updated_at": voice_baseline.get("updated_at") if voice_baseline["will_reuse"] else None,
            "summary": voice_baseline.get("summary") if voice_baseline["will_reuse"] else None,
            "markdown_path": voice_baseline["markdown_path"],
            "meta_path": voice_baseline["meta_path"],
        },
        "outputs": run_paths,
        "pipeline": {
            "prereqs": {"status": "completed", "detail": "Validated before run bootstrap"},
            "crawl": {"status": "pending"},
            "voice": {
                "status": "completed" if voice_baseline["will_reuse"] else "pending",
                "detail": (
                    f"Reused brand voice from {voice_baseline['updated_at']}"
                    if voice_baseline["will_reuse"] and voice_baseline.get("updated_at")
                    else ("Reused existing brand voice baseline" if voice_baseline["will_reuse"] else "")
                ),
            },
            "analysis": {"status": "pending"},
            "evidence": {"status": "pending"},
            "recommendations": {"status": "pending"},
            "draft": {"status": "pending"},
        },
        "articles": [],
        "banners": (
            [{
                "severity": "info",
                "message": f"Reusing saved brand voice baseline for {site_key}. Use --refresh-voice to rebuild it.",
                "at": _now_iso(),
            }]
            if voice_baseline["will_reuse"]
            else []
        ),
    }
    _write_json(run_dir / "state.json", initial_state)
    # Seed empty gates.json so agents and dashboard can read it without 404s.
    _write_json(run_dir / "gates.json", {})
    response = {
        "run_id": run_id,
        "dashboard_url": dashboard_url,
        "data_dir": str(DATA_DIR),
        "state_path": str(run_dir / "state.json"),
        "site_key": site_key,
        "canonical_blog_url": canonical_blog_url,
        "peec_project_id": peec_project_id,
        "voice_baseline": voice_baseline,
        "reviewers_path": str(site_paths["reviewers_path"]),
    }
    response.update(run_paths)
    return response


def _tool_update_state(args: dict) -> dict:
    run_id = args["run_id"]
    fragment = _normalize_state_fragment(args["fragment"])
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _load_state(state_path)
        _deep_merge(state, fragment)
        state = _normalize_state_fragment(state)
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {"ok": True}


def _tool_record_crawl_discovery(args: dict) -> dict:
    run_id = args["run_id"]
    discovered_count = max(0, int(args["discovered_count"]))
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _load_state(state_path)
        crawl = (state.setdefault("pipeline", {})).setdefault("crawl", {})
        crawl["discovered_count"] = discovered_count
        crawl.setdefault("status", "running")
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {"ok": True, "run_id": run_id, "discovered_count": discovered_count}


def _tool_record_crawled_article(args: dict) -> dict:
    run_id = args["run_id"]
    article = _require_object(args["article"], "article")
    slug = article.get("slug")
    if not isinstance(slug, str) or not slug:
        raise ValueError("article.slug is required")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    article_path = _output_paths(run_dir)["articles_dir"] / f"{slug}.json"
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        _write_json(article_path, article)
        state = _load_state(state_path)
        existing = next((item for item in state.get("articles", []) if isinstance(item, dict) and item.get("slug") == slug), None)
        fragment = {"articles": [_article_state_fragment(article, existing)]}
        _deep_merge(state, fragment)
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": slug,
        "relative_path": f"{slug}.json",
        "absolute_path": str(article_path),
    }


def _tool_finalize_crawl(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _load_state(state_path)
        existing_by_slug = {
            item.get("slug"): item
            for item in state.get("articles", [])
            if isinstance(item, dict) and isinstance(item.get("slug"), str)
        }
        records = _persisted_article_records(run_dir)
        persisted_rows = [_article_state_fragment(record, existing_by_slug.get(record["slug"])) for record in records]
        persisted_slugs = [row["slug"] for row in persisted_rows]
        dropped_slugs = [slug for slug in existing_by_slug.keys() if slug not in set(persisted_slugs)]
        state["articles"] = persisted_rows
        pipeline = state.setdefault("pipeline", {})
        crawl = pipeline.setdefault("crawl", {})
        discovered_count = _crawl_discovered_count(crawl)
        persisted_count = len(persisted_rows)
        if discovered_count is not None:
            crawl["discovered_count"] = discovered_count
        crawl["article_count"] = persisted_count
        crawl["persisted_count"] = persisted_count
        crawl.pop("articles_found", None)
        state.pop("crawl", None)
        if persisted_count == 0:
            crawl["status"] = "failed"
            crawl["detail"] = (
                f"Crawler discovered {discovered_count} articles but wrote none to disk."
                if discovered_count is not None
                else "Crawler wrote no article JSON files to disk."
            )
            state["status"] = "failed"
        elif discovered_count is not None and persisted_count < discovered_count:
            crawl["status"] = "partial"
            crawl["detail"] = f"Crawler discovered {discovered_count} articles but only {persisted_count} JSON files were written to disk."
        else:
            crawl["status"] = "completed"
            crawl["detail"] = f"{persisted_count} article JSON files written to disk."
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "run_id": run_id,
        "status": crawl["status"],
        "discovered_count": discovered_count,
        "persisted_count": persisted_count,
        "article_slugs": persisted_slugs,
        "dropped_slugs": dropped_slugs,
    }


def _tool_get_artifact_path(args: dict) -> dict:
    run_id = args["run_id"]
    namespace = args["namespace"]
    relative_path = args["relative_path"]
    _, target = _resolve_artifact_path(run_id, namespace, relative_path)
    return {
        "run_id": run_id,
        "namespace": namespace,
        "relative_path": relative_path,
        "absolute_path": str(target),
    }


def _tool_list_artifacts(args: dict) -> dict:
    run_id = args["run_id"]
    namespace = args["namespace"]
    suffix = args.get("suffix")
    limit = max(1, min(int(args.get("limit", 200)), 1000))
    base_dir = _artifact_base_dir(run_id, namespace)
    if not base_dir.exists():
        return {"run_id": run_id, "namespace": namespace, "artifacts": []}
    artifacts: list[dict[str, Any]] = []
    for target in sorted(base_dir.rglob("*")):
        if not target.is_file():
            continue
        relative_path = target.relative_to(base_dir).as_posix()
        if suffix and not relative_path.endswith(suffix):
            continue
        artifacts.append({
            "relative_path": relative_path,
            "absolute_path": str(target),
            "size_bytes": target.stat().st_size,
        })
        if len(artifacts) >= limit:
            break
    return {"run_id": run_id, "namespace": namespace, "artifacts": artifacts}


def _tool_read_text_artifact(args: dict) -> dict:
    run_id = args["run_id"]
    namespace = args["namespace"]
    relative_path = args["relative_path"]
    max_chars = max(1, min(int(args.get("max_chars", 200000)), 2_000_000))
    _, target = _resolve_artifact_path(run_id, namespace, relative_path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"Artifact not found: {namespace}/{relative_path}")
    content = target.read_text(encoding="utf-8")
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return {
        "run_id": run_id,
        "namespace": namespace,
        "relative_path": relative_path,
        "absolute_path": str(target),
        "content": content,
        "truncated": truncated,
    }


def _tool_read_json_artifact(args: dict) -> dict:
    run_id = args["run_id"]
    namespace = args["namespace"]
    relative_path = args["relative_path"]
    _, target = _resolve_artifact_path(run_id, namespace, relative_path)
    data = _read_json(target)
    if data is None:
        raise ValueError(f"JSON artifact not found or invalid: {namespace}/{relative_path}")
    return {
        "run_id": run_id,
        "namespace": namespace,
        "relative_path": relative_path,
        "absolute_path": str(target),
        "data": data,
    }


def _tool_read_bundle_text(args: dict) -> dict:
    relative_path = args["relative_path"]
    max_chars = max(1, min(int(args.get("max_chars", 200000)), 2_000_000))
    target = _resolve_bundle_path(relative_path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"Bundled file not found: {relative_path}")
    content = target.read_text(encoding="utf-8")
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return {
        "relative_path": relative_path,
        "absolute_path": str(target),
        "content": content,
        "truncated": truncated,
        "plugin_root": str(PLUGIN_ROOT),
    }


def _tool_write_text_artifact(args: dict) -> dict:
    run_id = args["run_id"]
    namespace = args["namespace"]
    relative_path = args["relative_path"]
    content = args["content"]
    _validate_text_write(namespace, relative_path)
    _, target = _resolve_artifact_path(run_id, namespace, relative_path)
    _atomic_write(target, content)
    return {
        "ok": True,
        "run_id": run_id,
        "namespace": namespace,
        "relative_path": relative_path,
        "absolute_path": str(target),
        "size_bytes": len(content.encode("utf-8")),
    }


def _tool_write_json_artifact(args: dict) -> dict:
    run_id = args["run_id"]
    namespace = args["namespace"]
    relative_path = args["relative_path"]
    data = args["data"]
    _validate_json_write(namespace, relative_path)
    _, target = _resolve_artifact_path(run_id, namespace, relative_path)
    _write_json(target, data)
    return {
        "ok": True,
        "run_id": run_id,
        "namespace": namespace,
        "relative_path": relative_path,
        "absolute_path": str(target),
    }


def _tool_record_evidence_pack(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    evidence = _require_object(args["evidence"], "evidence")
    payload_slug = evidence.get("article_slug")
    if payload_slug is None:
        evidence["article_slug"] = article_slug
    elif payload_slug != article_slug:
        raise ValueError("evidence.article_slug must match article_slug")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    evidence_path = _output_paths(run_dir)["evidence_dir"] / f"{article_slug}.json"
    sources = evidence.get("sources")
    source_count = len([item for item in sources if isinstance(item, dict)]) if isinstance(sources, list) else 0
    reviewer_candidate_id = evidence.get("reviewer_candidate_id")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        _write_json(evidence_path, evidence)
        state = _load_state(state_path)
        _deep_merge(state, {
            "articles": [
                {
                    "slug": article_slug,
                    "stages": {
                        "evidence": {
                            "status": "completed",
                            "source_count": source_count,
                            "reviewer_candidate_id": reviewer_candidate_id,
                        }
                    },
                }
            ]
        })
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": article_slug,
        "source_count": source_count,
        "relative_path": f"{article_slug}.json",
        "absolute_path": str(evidence_path),
    }


def _tool_record_recommendations(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    recommendations = _require_object(args["recommendations"], "recommendations")
    payload_slug = recommendations.get("article_slug")
    if payload_slug is None:
        recommendations["article_slug"] = article_slug
    elif payload_slug != article_slug:
        raise ValueError("recommendations.article_slug must match article_slug")
    items = recommendations.get("recommendations")
    if not isinstance(items, list):
        raise ValueError("recommendations.recommendations must be an array")
    if len(items) != 4:
        raise ValueError("recommendations.recommendations must contain exactly 4 items")
    matched_prompts = recommendations.get("matched_prompts")
    if isinstance(matched_prompts, list) and len(matched_prompts) > 2:
        raise ValueError("recommendations.matched_prompts must contain at most 2 items")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    rec_path = _output_paths(run_dir)["recommendations_dir"] / f"{article_slug}.json"
    audit = recommendations.get("audit") if isinstance(recommendations.get("audit"), dict) else {}
    critical_count = recommendations.get("critical_count")
    if not isinstance(critical_count, int):
        critical_count = len([item for item in items if isinstance(item, dict) and (item.get("required") or item.get("critical") or item.get("severity") == "critical")])
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        _write_json(rec_path, recommendations)
        state = _load_state(state_path)
        _deep_merge(state, {
            "articles": [
                {
                    "slug": article_slug,
                    "stages": {
                        "recommendations": {
                            "status": "completed",
                            "score_before": audit.get("score_before"),
                            "score_target": audit.get("score_target"),
                            "score_max": audit.get("score_max"),
                            "recommendation_count": len(items),
                            "critical_count": critical_count,
                            "mode": recommendations.get("mode"),
                        }
                    },
                }
            ]
        })
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": article_slug,
        "recommendation_count": len(items),
        "critical_count": critical_count,
        "relative_path": f"{article_slug}.json",
        "absolute_path": str(rec_path),
    }


def _persist_manifest_and_update_draft_state(run_dir: Path, article_slug: str, manifest: dict[str, Any]) -> Path:
    manifest_path = _output_paths(run_dir)["optimised_dir"] / f"{article_slug}.manifest.json"
    _write_json(manifest_path, manifest)
    state_path = run_dir / "state.json"
    state = _load_state(state_path)
    article = _find_or_create_article(state, article_slug)
    draft_stage = (article.setdefault("stages", {})).setdefault("draft", {})
    draft_stage["status"] = "completed" if manifest["quality_gate"]["status"] == "passed" else "failed"
    if manifest.get("audit_before") is not None:
        draft_stage["audit_before"] = manifest["audit_before"]
    if manifest.get("audit_after") is not None:
        draft_stage["audit_after"] = manifest["audit_after"]
    draft_stage["quality_gate"] = manifest["quality_gate"]["status"]
    if manifest["quality_gate"]["blocking_issues"]:
        draft_stage["blocker_summary"] = manifest["quality_gate"]["blocking_issues"][0]
    else:
        draft_stage.pop("blocker_summary", None)
    _refresh_pipeline_aggregates(state)
    state["updated_at"] = _now_iso()
    _write_json(state_path, state)
    return manifest_path


def _tool_record_voice_baseline(args: dict) -> dict:
    run_id = args["run_id"]
    markdown = str(args["markdown"])
    metadata = _require_object(args["metadata"], "metadata")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    state = _load_state(state_path)
    site_key = str(state.get("site_key") or "")
    if not site_key:
        raise ValueError(f"Run {run_id} is missing site_key")
    site_paths = _ensure_site_scaffold(site_key)
    stored_metadata = dict(metadata)
    stored_metadata.setdefault("site_key", site_key)
    stored_metadata.setdefault("canonical_blog_url", state.get("canonical_blog_url"))
    stored_metadata.setdefault("source_run_id", run_id)
    stored_metadata.setdefault("updated_at", _now_iso())
    stored_metadata.setdefault("version", 1)
    with STATE_LOCK:
        _atomic_write(site_paths["voice_markdown_path"], markdown)
        _write_json(site_paths["voice_meta_path"], stored_metadata)
        state = _load_state(state_path)
        summary = stored_metadata.get("summary")
        state["voice"] = {
            "mode": "generated",
            "source_run_id": stored_metadata.get("source_run_id"),
            "updated_at": stored_metadata.get("updated_at"),
            "summary": summary,
            "markdown_path": str(site_paths["voice_markdown_path"]),
            "meta_path": str(site_paths["voice_meta_path"]),
        }
        pipeline = state.setdefault("pipeline", {})
        pipeline["voice"] = {
            "status": "completed",
            "detail": str(summary or "Voice baseline recorded."),
        }
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "site_key": site_key,
        "markdown_path": str(site_paths["voice_markdown_path"]),
        "meta_path": str(site_paths["voice_meta_path"]),
        "updated_at": stored_metadata["updated_at"],
    }


def _tool_record_peec_gap(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    gap = _require_object(args["gap"], "gap")
    payload_slug = gap.get("article_slug")
    if payload_slug is None:
        gap["article_slug"] = article_slug
    elif payload_slug != article_slug:
        raise ValueError("gap.article_slug must match article_slug")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    gap_path = _output_paths(run_dir)["gaps_dir"] / f"{article_slug}.json"
    matched_prompts = gap.get("matched_prompts")
    matched_prompt_count = len([item for item in matched_prompts if isinstance(item, dict)]) if isinstance(matched_prompts, list) else 0
    admissible = bool(gap.get("admissible", matched_prompt_count > 0))
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        _write_json(gap_path, gap)
        state = _load_state(state_path)
        analysis_stage = {
            "status": "completed" if admissible else "failed",
            "matched_prompt_count": matched_prompt_count,
            "admissible": admissible,
        }
        if isinstance(gap.get("freshness"), str):
            analysis_stage["freshness"] = gap["freshness"]
        if isinstance(gap.get("blocker_reason"), str) and gap["blocker_reason"]:
            analysis_stage["blocker_summary"] = gap["blocker_reason"]
        _deep_merge(state, {
            "articles": [
                {
                    "slug": article_slug,
                    "stages": {
                        "analysis": analysis_stage,
                    },
                }
            ]
        })
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": article_slug,
        "matched_prompt_count": matched_prompt_count,
        "admissible": admissible,
        "relative_path": f"{article_slug}.json",
        "absolute_path": str(gap_path),
    }


def _tool_record_competitor_snapshot(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    snapshot = _require_object(args["snapshot"], "snapshot")
    payload_slug = snapshot.get("article_slug")
    if payload_slug is None:
        snapshot["article_slug"] = article_slug
    elif payload_slug != article_slug:
        raise ValueError("snapshot.article_slug must match article_slug")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    snapshot_path = _output_paths(run_dir)["competitors_dir"] / f"{article_slug}.json"
    competitors = snapshot.get("competitors")
    competitor_count = len([item for item in competitors if isinstance(item, dict)]) if isinstance(competitors, list) else 0
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        _write_json(snapshot_path, snapshot)
        state = _load_state(state_path)
        article = _find_or_create_article(state, article_slug)
        stages = article.setdefault("stages", {})
        analysis_stage = stages.setdefault("analysis", {})
        analysis_stage["status"] = "completed"
        analysis_stage["competitor_count"] = competitor_count
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": article_slug,
        "competitor_count": competitor_count,
        "relative_path": f"{article_slug}.json",
        "absolute_path": str(snapshot_path),
    }


def _tool_record_draft_package(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    package = _require_object(args["package"], "package")
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    output_paths = _output_paths(run_dir)
    markdown = package.get("markdown")
    html_text = package.get("html")
    schema = package.get("schema")
    diff_markdown = package.get("diff_markdown")
    handoff_markdown = package.get("handoff_markdown")
    audit_after = _safe_int(package.get("audit_after"))
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("package.markdown is required")
    if not isinstance(html_text, str) or not html_text.strip():
        raise ValueError("package.html is required")
    if not isinstance(schema, dict):
        raise ValueError("package.schema must be a JSON object")
    if not isinstance(diff_markdown, str) or not diff_markdown.strip():
        raise ValueError("package.diff_markdown is required")
    if not isinstance(handoff_markdown, str) or not handoff_markdown.strip():
        raise ValueError("package.handoff_markdown is required")

    with STATE_LOCK:
        _atomic_write(output_paths["optimised_dir"] / f"{article_slug}.md", markdown)
        _atomic_write(output_paths["optimised_dir"] / f"{article_slug}.html", html_text)
        _write_json(output_paths["optimised_dir"] / f"{article_slug}.schema.json", schema)
        _atomic_write(output_paths["optimised_dir"] / f"{article_slug}.diff.md", diff_markdown)
        _atomic_write(output_paths["optimised_dir"] / f"{article_slug}.handoff.md", handoff_markdown)
        state_path = run_dir / "state.json"
        state = _load_state(state_path)
        article = _find_or_create_article(state, article_slug)
        draft_stage = (article.setdefault("stages", {})).setdefault("draft", {})
        draft_stage["status"] = "running"
        if audit_after is not None:
            draft_stage["audit_after"] = audit_after
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)

    with STATE_LOCK:
        manifest = build_article_manifest(run_dir, article_slug, audit_after=audit_after)
        manifest_path = _persist_manifest_and_update_draft_state(run_dir, article_slug, manifest)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": article_slug,
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "quality_gate_status": manifest["quality_gate"]["status"],
    }


def _tool_fail_article_stage(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    stage = args["stage"]
    reason = str(args["reason"]).strip()
    detail = str(args.get("detail") or "").strip()
    code = str(args.get("code") or "").strip() or None
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _load_state(state_path)
        article = _find_or_create_article(state, article_slug)
        stage_state = (article.setdefault("stages", {})).setdefault(stage, {})
        stage_state["status"] = "failed"
        stage_state["blocker_summary"] = reason
        if detail:
            stage_state["detail"] = detail
        if code:
            stage_state["code"] = code
        if stage == "draft":
            stage_state["quality_gate"] = "failed"
        _refresh_pipeline_aggregates(state)
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "article_slug": article_slug,
        "stage": stage,
        "reason": reason,
    }


def _tool_finalize_run_report(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _load_state(state_path)
        report_markdown = _render_run_report(state, run_dir)
        report_path = run_dir / "run-summary.md"
        _atomic_write(report_path, report_markdown)
        state["status"] = _run_terminal_status(state)
        state["report"] = {
            "generated_at": _now_iso(),
            "path": str(report_path),
        }
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {
        "ok": True,
        "run_id": run_id,
        "status": state["status"],
        "report_path": str(report_path),
    }


def _tool_validate_article(args: dict) -> dict:
    run_id = args["run_id"]
    article_slug = args["article_slug"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    with STATE_LOCK:
        manifest = build_article_manifest(run_dir, article_slug, audit_after=args.get("audit_after"))
        _persist_manifest_and_update_draft_state(run_dir, article_slug, manifest)
    return manifest


def _tool_validate_run(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state = _load_state(run_dir / "state.json")
    output_paths = _output_paths(run_dir)
    requested = args.get("article_slugs")
    if isinstance(requested, list) and requested:
        article_slugs = [str(item) for item in requested if str(item)]
    else:
        article_slugs = [
            str(article.get("slug"))
            for article in state.get("articles", [])
            if isinstance(article, dict) and article.get("slug")
            and (output_paths["optimised_dir"] / f"{article.get('slug')}.html").exists()
            and (output_paths["optimised_dir"] / f"{article.get('slug')}.schema.json").exists()
        ]
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    for article_slug in article_slugs:
        manifest = _tool_validate_article({"run_id": run_id, "article_slug": article_slug})
        results.append({
            "article_slug": article_slug,
            "status": manifest["quality_gate"]["status"],
            "missing_required_modules": manifest["missing_required_modules"],
        })
        if manifest["quality_gate"]["status"] == "passed":
            passed += 1
        else:
            failed += 1
    return {
        "run_id": run_id,
        "results": results,
        "passed": passed,
        "failed": failed,
    }


def _tool_download_media_asset(args: dict) -> dict:
    run_id = args["run_id"]
    source_url = args["source_url"]
    relative_path = args["relative_path"]
    timeout_seconds = max(1, min(int(args.get("timeout_seconds", 15)), 60))
    _, target = _resolve_artifact_path(run_id, "media", relative_path)
    request = urllib.request.Request(source_url, headers={
        "User-Agent": f"Mozilla/5.0 (compatible; AI Search Blog Optimiser/{VERSION})"
    })
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
    _atomic_write_bytes(target, payload)
    return {
        "ok": True,
        "run_id": run_id,
        "namespace": "media",
        "relative_path": relative_path,
        "absolute_path": str(target),
        "size_bytes": len(payload),
        "source_url": source_url,
    }


def _tool_list_runs(_args: dict) -> dict:
    return {"runs": _list_runs()}


def _tool_show_banner(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise ValueError(f"Run {run_id} does not exist")
    state_path = run_dir / "state.json"
    with STATE_LOCK:
        state = _load_state(state_path)
        banners = state.setdefault("banners", [])
        banners.append({
            "severity": args["severity"],
            "message": args["message"],
            "action_url": args.get("action_url"),
            "action_label": args.get("action_label"),
            "at": _now_iso(),
        })
        state["updated_at"] = _now_iso()
        _write_json(state_path, state)
    return {"ok": True}


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
            timeout_seconds = _normalize_timeout_seconds(args.get("timeout_seconds"))
            gate["pending_since"] = _now_iso()
            gate["resolved_at"] = None
            gate["user_action"] = None
            gate["timeout_seconds"] = timeout_seconds
            pending_since = _parse_iso(gate["pending_since"]) or datetime.utcnow()
            gate["expires_at"] = (pending_since + timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif status == "resolved":
            gate["resolved_at"] = _now_iso()
            gate["user_action"] = args.get("user_action", "proceed")
            gate["timeout_seconds"] = _normalize_timeout_seconds(gate.get("timeout_seconds"))
        _write_json(gates_path, gates)
    return {"ok": True, "gate": gate}


def _tool_get_gates(args: dict) -> dict:
    run_id = args["run_id"]
    run_dir = RUNS_DIR / run_id
    gates = _hydrate_gates(run_dir)
    return gates


TOOL_DISPATCH = {
    "open_dashboard": _tool_open_dashboard,
    "get_dashboard_url": _tool_get_dashboard_url,
    "register_run": _tool_register_run,
    "update_state": _tool_update_state,
    "record_crawl_discovery": _tool_record_crawl_discovery,
    "record_crawled_article": _tool_record_crawled_article,
    "finalize_crawl": _tool_finalize_crawl,
    "get_artifact_path": _tool_get_artifact_path,
    "list_artifacts": _tool_list_artifacts,
    "read_text_artifact": _tool_read_text_artifact,
    "read_json_artifact": _tool_read_json_artifact,
    "read_bundle_text": _tool_read_bundle_text,
    "write_text_artifact": _tool_write_text_artifact,
    "write_json_artifact": _tool_write_json_artifact,
    "record_evidence_pack": _tool_record_evidence_pack,
    "record_recommendations": _tool_record_recommendations,
    "record_voice_baseline": _tool_record_voice_baseline,
    "record_peec_gap": _tool_record_peec_gap,
    "record_competitor_snapshot": _tool_record_competitor_snapshot,
    "record_draft_package": _tool_record_draft_package,
    "fail_article_stage": _tool_fail_article_stage,
    "finalize_run_report": _tool_finalize_run_report,
    "validate_article": _tool_validate_article,
    "validate_run": _tool_validate_run,
    "download_media_asset": _tool_download_media_asset,
    "list_runs": _tool_list_runs,
    "show_banner": _tool_show_banner,
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
                    "serverInfo": {"name": "blog-optimiser-dashboard", "version": VERSION},
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
    global PLUGIN_ROOT, RUNS_DIR, SITES_DIR, DATA_DIR, DASHBOARD_DIR, LOCK_FILE, HTTP_SERVER, HTTP_PORT

    parser = argparse.ArgumentParser(description="AI Search Blog Optimiser dashboard server")
    parser.add_argument("--plugin-root", type=str, default=str(PLUGIN_ROOT),
                        help="Absolute path to the plugin root (defaults to CLAUDE_PLUGIN_ROOT env). Read-only in Cowork sandbox — assets only.")
    parser.add_argument("--http-only", action="store_true",
                        help="Dev/QA: HTTP only, no MCP, runs in foreground.")
    parser.add_argument("--http-daemon", action="store_true",
                        help="Long-lived detached HTTP daemon. Spawned by the MCP via --http-daemon. Writes dashboard.lock. Does NOT do MCP stdio.")
    parser.add_argument("--stop-dashboard", action="store_true",
                        help="Kill any running detached HTTP daemon and clear the lock.")
    parser.add_argument("--port", type=int, default=0,
                        help="Fixed HTTP port (0 = auto).")
    args = parser.parse_args()

    PLUGIN_ROOT = Path(args.plugin_root).resolve()
    DASHBOARD_DIR = PLUGIN_ROOT / "dashboard"
    DATA_DIR = _resolve_data_dir()
    RUNS_DIR = DATA_DIR / "runs"
    SITES_DIR = DATA_DIR / "sites"
    LOCK_FILE = DATA_DIR / "dashboard.lock"

    # Verify writability up-front.
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        SITES_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".writable-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        _log(f"FATAL: data dir {DATA_DIR} is not writable: {e}")
        _log("Set BLOG_OPTIMISER_DATA_ROOT to a writable path.")
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
