# Changelog

All notable changes to the AI Search Blog Optimiser plugin.

## [0.5.9] — 2026-04-25

Iteration 3 bug-fix release. v0.5.8 smoke landed both articles' audit_after >= 32
but `quality_gate` still failed on two specific edge cases. This closes them.

### Validator (Lane G)
- **Bug 9** — `_HTMLSnapshotParser` in `dashboard/quality_gate.py` now extracts
  FAQ questions from `<dl><dt>` definition lists in addition to `<h1>-<h3>`
  headings. Generator's v0.5.8 FAQ-as-definition-list output is now visible to
  the validator (previously `faq_questions_visible: []` despite valid `<dl>`
  markup in the rendered HTML).
- **Bug 10** — `_validate_author` accepts single-name authors (e.g. "Jack" on
  engineering posts) when `trust.author.role` is populated with a substantive
  role (>= 4 chars, not a stop-word). Single name without a role still fails;
  full-name authors continue to pass without a role per Bug 8's existing
  fallback.

### Acceptance tests
- tests/bug_09_dt_faq_extraction_test.md
- tests/bug_10_single_name_with_role_trust_test.md

## [0.5.8] — 2026-04-25

Iteration 2 bug-fix release. Driven by the v0.5.7 live smoke against the Granola
blog where both articles failed quality_gate on legitimate generator+validator
contract gaps. Two parallel Codex agents (gpt-5.5, reasoning-effort high) on
isolated worktrees executed the iteration-2 spec.

### Generator output (Lane E)
- **Bug 5** — embed JSON-LD inside the rendered HTML in a
  `<script type="application/ld+json">` block, not just as a side artefact.
  The standalone schema.json file remains; the embedded copy is the
  source of truth for `validate_article`'s `schema_checks.passed_embedded_jsonld`.
- **Bug 7** — render FAQ blocks as `<dl><dt>question</dt><dd>answer</dd></dl>`
  definition lists so the validator can extract `faq_questions_visible`.

### Validator strictness (Lane F)
- **Bug 6** — internal-link host check now accepts `*.<site_key>` subdomains
  (e.g. `docs.granola.ai` and `app.granola.ai` count as internal for `granola.ai`).
- **Bug 8** — when `site/reviewers.json` is empty AND the article author has
  at least a first + last name, the trust block falls back to the article
  author with `trust_block.source = "article_author_fallback"`. Single-name
  authors still fail the trust block.

### Acceptance tests
- tests/bug_05_jsonld_embedded_in_html_test.md
- tests/bug_06_internal_link_domain_test.md
- tests/bug_07_faq_visible_test.md
- tests/bug_08_trust_block_author_fallback_test.md

## [0.5.7] — 2026-04-25

Bug-fix release driven by 2026-04-25 live test run on the Granola blog. Two parallel
Codex agents (gpt-5.5, reasoning-effort high) executed the bug spec.

### Fixed
- **Bug 1 — crawler run-id discipline**: blog-crawler agent prompt tightened to forbid
  calling register_run; must accept run_id from orchestrator prompt and abort on missing.
  Prevents the duplicate-run / lost-Peec-association failure mode seen on 2026-04-25.
- **Bug 3 — evidence artifact namespace**: extracted JSON_WRITE_NAMESPACES constant in
  dashboard/server.py to keep write/read/list namespace lists in sync. The v0.5.6 source
  already included  in both lists; this commit hardens that against drift.

### Validated (no source change required)
- **Bug 2 — evidence-builder agent registration**: plugin.json correctly omits an explicit
  agents allow-list (auto-discovery), and agents/evidence-builder.md frontmatter is valid.
  The earlier `Agent type not found` error was a stale Claude Code session-cache issue,
  not a packaging defect. Acceptance test added under tests/.
- **Bug 4 — validate_article tool**: v0.5.6 source already implements the tool at
  dashboard/server.py:1694 (definition) / 2683 (impl) / 2843 (dispatcher). The earlier
  `No validate_article tool exists` error was a stale v0.5.3 desktop bundle. Lane A's
  initial Path B (self-rubric replacement) was reverted as it conflicted with the
  controller-generated manifest design that the v0.5.6 source already supports.

### Acceptance tests
- tests/bug_01_crawler_run_id_discipline_test.md
- tests/bug_02_evidence_builder_registered_test.md
- tests/bug_03_evidence_namespace_test.md
- tests/bug_04_validate_article_test.md

## [0.5.6] — 2026-04-23

Crawl-state hardening release after live runs reported discovered articles that never persisted as host artifacts.

### Fixed
- Replaced the crawler's split write path with typed dashboard tools so crawl discovery, per-article article JSON writes, and crawl finalization are persisted through one host-owned contract.
- Added `finalize_crawl` reconciliation so the run state is pruned back to the real `outputs/articles/*.json` set instead of letting ghost crawl rows leak into evidence, recommendation, and draft stages.
- Added typed evidence and recommendation writers so downstream stage state is updated atomically with the artifact write instead of relying on prompt-authored `update_state` payloads.
- Added regression coverage for crawl reconciliation, typed evidence writes, typed recommendation writes, and recommendation-count enforcement.

## [0.5.5] — 2026-04-23

Cowork gate and artifact-hardening fix after a live recommendation-to-draft failure.

### Fixed
- Gates now treat Claude Cowork chat as the primary control surface. The dashboard is review-only and the runtime prompts now tell the user to reply `continue` in Cowork instead of relying on a dashboard button.
- Hardened JSON artifact reads and writes so accidental stringified payloads are normalized instead of breaking recommendation rendering or validator calls.
- Added legacy state repair so older draft status shapes are mapped back into `articles[].stages.draft`, keeping the dashboard table and validator aligned.
- Added regressions for stringified JSON artifacts, repaired draft-state reads, and Cowork-first gate wording.

## [0.5.4] — 2026-04-23

Cowork compatibility fix for user-installed Peec MCP connections.

### Fixed
- Stopped assuming the external Peec MCP server prefix is literally `mcp__peec__...`.
- Updated the slash command, main pipeline playbook, and Peec gap-reader contract to discover Peec tools by capability via `ToolSearch`, so UUID-named Cowork MCP servers are treated as valid Peec connections.
- Documented the capability-based Peec discovery rule in the runtime docs to keep future prompt changes from regressing to server-name assumptions.

## [0.5.3] — 2026-04-23

Installed Cowork runtime fix focused on getting the recommendation stage to complete reliably under
real desktop runs.

### Fixed
- Tightened the recommender contract so it uses only the top Peec prompt slices instead of copying large gap payloads into the rewrite artifact.
- Shrunk the recommendation JSON shape to the minimum generator and validator inputs needed for draft generation, reducing long stalled tool-call emissions in the installed plugin runtime.
- Added prompt guardrails that force terse recommendation rows, shorter blueprint fields, and compact evidence references instead of long copied excerpts.

## [0.5.2] — 2026-04-23

Installed Cowork runtime hardening focused on keeping Peec gap reads robust under live plugin runs.

### Fixed
- Locked the Peec gap-read recipe to `get_actions(scope=overview)` so installed Cowork runs no longer depend on follow-up action branches that were intermittently returning live `422` errors.
- Tightened the prompt regression suite to keep the gap-read contract on the overview-only path.

## [0.5.1] — 2026-04-23

Installed Cowork runtime fix focused on keeping workers inside the supported host-vs-bundle file model.

### Fixed
- `register_run` now scaffolds `sites/{site_key}/reviewers.json` as an empty array so fresh installs do not fail on a missing optional reviewer file.
- Added a bundled reference reader to the dashboard MCP so workers can load `references/*.md` and `skills/*/SKILL.md` from the installed plugin without abusing run artifact namespaces.
- Updated gap-reader, recommender, and generator prompts to use the bundled reader for plugin-static references instead of attempting unsafe host-path traversal.
- Tightened reviewer-file guidance in evidence, recommendation, and draft stages so workers treat site reviewers as a site-scoped JSON array that may be empty, not as an optional file they need to probe ad hoc.

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
