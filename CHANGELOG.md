# Changelog

All notable changes to the AI Search Blog Optimiser plugin.

## [0.3.2] — 2026-04-22

Dashboard review release focused on making the inline article workflow actually usable.

### Added
- Rebuilt the expanded article row into a persistent inline inspector with a recommendation rail plus `Optimized article`, `Structure`, and `Image` tabs.
- Added richer implementation proof inside the dashboard: heading plan, internal link review, implementation notes, schema/meta summaries, and inline hero image treatment.

### Changed
- Kept the existing AI Heroes table shell and light theme, but made the expanded row behave more like an Airtable/Notion detail panel.
- Kept raw artifact links as secondary actions while making recommendations and the optimized article the primary review surface.

## [0.3.1] — 2026-04-22

Runtime fix focused on Cowork sandbox correctness during the crawl and downstream leaf-agent stages.

### Fixed
- Added host-side artifact read/write tools to the local dashboard MCP so leaf agents no longer try to persist run files through sandboxed `/Users/...` paths.
- Replaced the broken crawler persistence contract that was falling back to `~/mnt/outputs` inside Cowork workers.
- Tightened the crawler prompt to discover article URLs only from real hrefs and canonical URLs, not title-inferred slugs.
- Added a fixed article fetch order of `md raw -> html -> execute_js` for JS-heavy blogs such as Granola.
- Updated voice, gap, competitor, recommendation, and generator agents to use MCP-backed storage instead of direct host-path reads and writes.
- Added a post-crawl invariant in the main playbook: if the real `articles` namespace is empty, the pipeline fails instead of continuing with stale or missing data.

## [0.3.0] — 2026-04-22

Clean-break release focused on fresh-run correctness.

### Changed
- Fresh runs now register first and open the browser second. `open_dashboard` requires `run_id`.
- Dashboard home page is now neutral history. `/` no longer redirects to the latest run.
- Local storage moved to a new versioned root under `ai-search-blog-optimiser/v3`.
- Run outputs now live under `runs/{run_id}/outputs/`.
- Voice reuse is site-scoped under `sites/{site_key}/`, not Peec-project-scoped.
- `register_run` now returns the full absolute path set needed by orchestration. `get_paths` is no longer part of the normal flow.
- Pipeline contract now uses strict stage names: `prereqs`, `crawl`, `voice`, `analysis`, `recommendations`, `draft`.

### Fixed
- Stale historical dashboards no longer appear when starting a new run.
- Stage 0 no longer uses `mcp__c4ai-sse__ask` as a Crawl4AI healthcheck.
- Same-site voice reuse is now explicit and visible in state and dashboard UI.

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
