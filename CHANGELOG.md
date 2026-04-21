# Changelog

All notable changes to the AI Search Blog Optimiser plugin.

## [0.2.0] — 2026-04-21

Major architectural refactor after live-run feedback. The pipeline now actually delivers the human-in-the-loop dashboard experience that was broken in v0.1.

### Fixed
- **Orchestrator sub-agent removed.** The slash command now runs orchestration directly in the main Claude session — no handoff. This fixes: dashboard never auto-opened (only main-session MCP calls spawn browser side effects), parallel Task dispatch was serialised, and mid-pipeline context compaction from redundant sub-agent indirection.
- **Dashboard HTTP daemon detached from MCP lifecycle.** The MCP process can now be killed/restarted (normal Cowork idle behaviour) without killing the browser tab. Daemon writes `dashboard.lock` (PID + port); next MCP startup reuses if alive, respawns if dead. URL stays stable across MCP restarts.
- **Per-article stage status display.** Dashboard no longer shows "pending" on completed articles just because the pipeline-wide stage hasn't finished the last batch. New `articleStage()` helper uses per-article data when present and infers sensibly from pipeline-wide status otherwise.
- **Dashboard Continue-button flow.** New `POST /api/runs/{id}/gate` endpoint; dashboard polls `gates.json` and renders a prominent Continue banner when a gate is pending.
- **Accept/reject buttons round-trip immediately.** Immediate re-fetch after POST so the UI reflects the decision without waiting for the 1.5s tick.

### Added
- New MCP tools: `set_gate`, `get_gates` for the main session to pause pipeline between stages for human review. Dashboard polls and user clicks Continue to resolve.
- `--http-daemon` mode (spawned by MCP, long-lived, independent).
- `--stop-dashboard` flag to kill the daemon cleanly.
- Lock file at `~/.ai-search-blog-optimiser/dashboard.lock` with PID + port.
- `tests/dashboard_e2e_test.py` — smoke test for daemon + gate + accept/reject flow.
- `--no-gates` flag on `/blog-optimiser` to skip all human gates (for autonomous runs).

### Changed
- `commands/blog-optimiser.md`: now tells main session to run orchestration directly, not hand off.
- `skills/blog-optimiser-pipeline/SKILL.md`: rewritten as the main-session playbook (was: sub-agent orchestrator instructions). Adds explicit gate mechanism, parallelism-in-single-message rule, ≤300 token sub-agent summary cap.
- `agents/orchestrator.md`: **DELETED**. Its logic moved into the skill.
- `dashboard/server.py`: detached daemon, 10 MCP tools (added `set_gate`, `get_gates`; `get_paths` now returns `gates_json` and `run_summary_md`).
- `dashboard/index.html`: v0.2.0 gate banner, `articleStage()` helper, re-fetch after POST.

### Migration from v0.1.x
- `~/.ai-search-blog-optimiser/` paths unchanged — v0.1 runs still readable.
- If you had a v0.1 dashboard process running, `--stop-dashboard` cleans it up. Next v0.2 run spawns a fresh detached daemon.

## [0.1.1] — 2026-04-21

### Fixed
- **Critical**: Cowork mounts the plugin install directory as read-only for sub-agents, so writes to `${CLAUDE_PLUGIN_ROOT}/runs/` silently no-op. All writable state (runs, brand-voice artefacts, decisions) now lives in `~/.ai-search-blog-optimiser/` (override via `--data-dir` or `AI_SEARCH_BLOG_OPTIMISER_DATA` env var). Dashboard static assets still served from the plugin root (read access is fine).
- Added a new MCP tool `get_paths` that returns absolute `data_dir`, `runs_dir`, `brands_dir`, and per-run sub-directories. Orchestrator calls this at stage start and passes absolute paths to every sub-agent.
- Server performs a writability probe on startup and exits with a clear error if the data dir isn't writable.

### Changed
- Default data root: `~/.ai-search-blog-optimiser/` (previously under plugin root).
- All agent prompts updated to reference `{articles_dir}`, `{recommendations_dir}`, `{brands_dir}`, `{run_dir}` etc. as placeholders filled in from orchestrator-passed absolute paths, not hardcoded relative paths.

## [0.1.0] — Initial draft

First public release. Peec AI MCP Challenge submission.

### Added
- 4-stage pipeline: crawl → voice → recommend → generate.
- 7 specialised agents with tiered model allocation (Opus for orchestrator/recommender/generator; Sonnet for voice/peec-gap-reader; Haiku for crawlers).
- Live local dashboard (python3 stdlib HTTP server + Tailwind/Alpine CDN + AI Heroes brand theme).
- Deep structural capture via Crawl4AI: heading tree, tables, images (downloaded locally), videos, schema gaps, trust signals, link graph, CTAs.
- Peec gap evidence trail per recommendation: matched prompts, brand visibility per engine, cited competitor URLs, verbatim AI response excerpts.
- Brand voice extraction: persistent, namespaced by Peec project ID + role, structural fingerprint + lexicon + tone rules + exemplar pairs.
- 40-point article audit rubric with type-adaptive presets (listicle / how-to / comparison / glossary / case-study / pillar / opinion / product).
- Recommender produces 5–7 recommendations per article, each with complete evidence trail (Peec gap + GEO rule + competitor example + Step 1 field) and structured `auto_fix` payload.
- Generator preserves all original claims, quotes, images, links; augments, never rewrites. Self-checks ≥ 32/40 before shipping.
- Outputs per article: optimised markdown + styled HTML + JSON-LD schema + handoff doc + diff vs original + self-contained media folder.
- Resumable via `/blog-optimiser --resume {run_id}`. Atomic disk writes.
- Dashboard accept/reject toggles per recommendation; re-run per article without re-running the whole pipeline.
- Generic mode fallback when Peec MCP isn't connected.
