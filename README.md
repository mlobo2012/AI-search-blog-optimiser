# AI Search Blog Optimiser

A Claude Cowork desktop plugin for rewrite-only blog optimisation aimed at AI-search citation. It crawls an existing blog, builds a site-scoped brand voice baseline, generates evidence-grounded recommendations, and either produces an optimised rewrite or blocks the article truthfully in a local report dashboard.

## What changed in v0.5

This release is a clean break:

- new runs are registered before any dashboard tab opens
- the dashboard home page never redirects to the latest run
- local state lives in a new versioned data root
- brand voice reuse is keyed by site, not by Peec project id
- `register_run` returns the absolute paths the orchestration needs
- Peec is required for new runs
- dashboard review remains, but dashboard-driven continue gates are deprecated
- recommendation and draft generation now follow a stricter GEO rewrite contract
- site-scoped reviewers live alongside the site voice baseline
- evidence packs are first-class run artefacts
- draft manifests are now written by a deterministic validator, not by generator self-reporting
- core site/gap/competitor/draft writes now have typed host-owned MCP tools
- final run reports are generated from disk truth

## Command

```text
/blog-optimiser https://your-blog.com/blog [--refresh-voice] [--resume {run_id}] [--max-articles N]
```

## Storage

Writable root selection:

- `CLAUDE_PLUGIN_DATA` when Cowork provides it
- otherwise platform default roots below
- `BLOG_OPTIMISER_DATA_ROOT` overrides both for tests/dev only

Default fallback roots:

- macOS: `~/Library/Application Support/ai-search-blog-optimiser/v3`
- Linux: `~/.local/share/ai-search-blog-optimiser/v3`
- Windows: `%APPDATA%\ai-search-blog-optimiser\v3`

When `CLAUDE_PLUGIN_DATA` is used, the runtime performs a one-time import from the legacy default root if the new plugin data directory is empty. Set `BLOG_OPTIMISER_SKIP_LEGACY_IMPORT=1` to disable that import path in tests or debugging.

Layout:

```text
v3/
  runs/{run_id}/
    state.json
    gates.json
    run-summary.md
    outputs/
      articles/
      evidence/
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
    reviewers.json
  dashboard.lock
```

## Runtime rules

- The main session is the orchestrator.
- `open_dashboard` requires a concrete `run_id`.
- `register_run` is the bootstrap call for fresh runs.
- `register_run` requires `peec_project_id`.
- `get_paths` is no longer part of the normal flow.
- `state.json` is the source of truth.
- Same-site voice reuse is automatic unless `--refresh-voice` is set.
- Peec is required. Missing Peec should block the run or article instead of silently downgrading to a GEO-only rewrite.
- Peec MCP discovery is capability-based, not server-name-based. In Cowork, a valid external Peec MCP may appear under a UUID-style tool prefix instead of `mcp__peec__...`.
- The dashboard is a read-only report surface. It should not own orchestration or continue controls.
- `write_json_artifact` expects raw JSON objects or arrays. The runtime now normalizes accidentally stringified JSON payloads for backward compatibility.
- Core pipeline writes should use typed dashboard tools so artifact persistence and state updates happen atomically.

## Dashboard behavior

- `/` is a neutral home/history page
- `/runs/{run_id}/` is the run-bound dashboard page
- no route auto-selects the latest run

## Embedded MCP tools

- `open_dashboard`
- `get_dashboard_url`
- `register_run`
- `update_state`
- `record_crawl_discovery`
- `record_crawled_article`
- `finalize_crawl`
- `list_runs`
- `show_banner`
- `set_gate`
- `get_gates`
- `record_evidence_pack`
- `record_recommendations`
- `record_voice_baseline`
- `record_peec_gap`
- `record_competitor_snapshot`
- `record_draft_package`
- `fail_article_stage`
- `finalize_run_report`

## Development

Run the regression suite:

```bash
python3 tests/dashboard_e2e_test.py
```

Validate the server module:

```bash
python3 -m py_compile dashboard/server.py
```
