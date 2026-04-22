# AI Search Blog Optimiser

A Claude Cowork desktop plugin for blog optimisation aimed at AI-search citation. It crawls a blog, builds a site-scoped brand voice baseline, generates article recommendations, and produces optimised drafts in a local dashboard.

## What changed in v0.3

This release is a clean break:

- new runs are registered before any dashboard tab opens
- the dashboard home page never redirects to the latest run
- local state lives in a new versioned data root
- brand voice reuse is keyed by site, not by Peec project id
- `register_run` returns the absolute paths the orchestration needs

## Command

```text
/blog-optimiser https://your-blog.com/blog [--refresh-voice] [--resume {run_id}] [--max-articles N] [--no-gates]
```

## Storage

Default writable roots:

- macOS: `~/Library/Application Support/ai-search-blog-optimiser/v3`
- Linux: `~/.local/share/ai-search-blog-optimiser/v3`
- Windows: `%APPDATA%\ai-search-blog-optimiser\v3`

Optional override for tests/dev only:

- `BLOG_OPTIMISER_DATA_ROOT`

Layout:

```text
v3/
  runs/{run_id}/
    state.json
    decisions.json
    gates.json
    outputs/
      articles/
      recommendations/
      optimised/
      media/
      raw/
      gaps/
      competitors/
      peec-cache/
  sites/{site_key}/
    brand-voice.md
    voice.json
  dashboard.lock
```

## Runtime rules

- The main session is the orchestrator.
- `open_dashboard` requires a concrete `run_id`.
- `register_run` is the bootstrap call for fresh runs.
- `get_paths` is no longer part of the normal flow.
- `state.json` is the source of truth.
- Same-site voice reuse is automatic unless `--refresh-voice` is set.

## Dashboard behavior

- `/` is a neutral home/history page
- `/runs/{run_id}/` is the run-bound dashboard page
- no route auto-selects the latest run

## Embedded MCP tools

- `open_dashboard`
- `get_dashboard_url`
- `register_run`
- `update_state`
- `list_runs`
- `get_decisions`
- `show_banner`
- `set_gate`
- `get_gates`

## Development

Run the regression suite:

```bash
python3 tests/dashboard_e2e_test.py
```

Validate the server module:

```bash
python3 -m py_compile dashboard/server.py
```
