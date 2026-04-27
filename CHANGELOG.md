# Changelog

All notable changes to the AI Search Blog Optimiser plugin.

## [0.7.0] — 2026-04-27

Crawler support plus Claude Code and Claude Cowork distribution clarity.

- Documented Crawl4AI MCP as the primary tested crawl/fetch backend, using the official local server at `http://localhost:11235/mcp/sse` connected as `c4ai-sse`.
- Added macOS-oriented Crawl4AI MCP setup guidance for Claude Code and Claude Desktop/Cowork.
- Added capability-based Firecrawl discovery (`firecrawl_scrape` + `firecrawl_map`) so the plugin can still use a connected Firecrawl MCP server even when Cowork exposes it under a UUID-style prefix.
- Persisted the selected crawl backend in run state and pass it through to the crawler and evidence-fetching agents.
- Hardened recommendation prompt-id validation and generator scope checks based on the Firecrawl smoke run.
- Added a Claude Code marketplace catalog at `.claude-plugin/marketplace.json`.
- Updated README guidance for separate Claude Code and Claude Cowork installation paths, including Crawl4AI MCP and Firecrawl MCP setup.
- Bumped plugin metadata to `0.7.0` so the Claude Code marketplace install and Cowork release page use the same public version.

## [0.6.9] — 2026-04-26

Regression recovery build for the exact-article Granola MCP and Microsoft article flow.

- Restored the dashboard article-detail presentation pattern so recommendation and draft panels render like the earlier richer review UI.
- Added deterministic optimized-article iframe styling with large readable headings, a blue TL;DR block, reviewer/evidence card, styled tables, and comfortable article spacing.
- Rebalanced recommender guidance toward nuanced article-specific recommendations, keeping project-level off-page opportunities as companion handoff actions instead of replacing visible on-page recommendations.
- Relaxed the trust-block validator to accept visible human-readable dates as well as ISO dates.

## [0.6.7] — 2026-04-26

Dashboard hotfix for Claude Cowork run reports.

- Fixed article detail expansion so "View recommendations" renders the saved recommendation artifact instead of an empty row.
- Fixed "View draft article" so completed drafts render the optimized HTML iframe for the selected article.
- Prevented hidden article rows from preloading missing recommendation/draft artifacts, removing noisy 404s for articles that were intentionally blocked.
- Bumped dashboard/runtime version display to `0.6.7` for install clarity.

## [0.6.6] — 2026-04-26

Iteration 9 — final integration of the v0.6 release line. Closes the
4 residual issues from the v0.6.5 verification smoke YELLOW (manifest
contract drift on rec_implementation_map non-applicable entries, trust
block source mislabeling for the visible-reviewer-block promotion path,
and recurring recommender retry banners on count-bound and per-rec prompt
minimum). Spec at `specs/2026-04-26-bugs-iteration9.md`.

This is the FIRST iteration to use the new `parallel-agent-orchestration`
skill (`~/.claude/skills/parallel-agent-orchestration/SKILL.md`,
synchronized to `~/.codex/skills/`). Two Codex agents (gpt-5.5,
reasoning_effort high) ran in parallel in fully isolated git worktrees
(`lane-m-iter9` and `lane-n-iter9` off `feat/v0.6.0-integration`). Zero
cross-contamination between lanes — the iter8 worktree-sharing footgun is
now closed.

### Lane M — validator (dashboard/quality_gate.py)
- **Bug 22** — rec_implementation_map validator now accepts BOTH the
  implemented shape from Bug 15 (`{implemented: true, section, anchor,
  schema_fields, evidence_inserted, notes}`) AND the non-applicable
  sentinel shape (`{implemented: false, reason: <enum>}` where reason ∈
  `{"non-applicable", "deferred", "out-of-scope"}`, case-insensitive,
  hyphen and underscore both accepted). Entries with `implemented: false`
  but no `reason` field are rejected with a clear banner; undocumented
  reason values are also rejected. The verifier's downstream C2 check
  no longer flags valid sentinel entries as shape failures.
- **Bug 23** — when the optimised draft contains BOTH a source author
  byline (typically rejected as weak role) AND a "Reviewed by" / "Edited
  by" / "Verified by" / "Reviewer:" block (case-insensitive, anchored to
  start of line or paragraph), the validator now labels
  `trust_block.source = "reviewers_promoted"` and adds an
  `author_validation.detail` entry that explains the promotion. Bug 18's
  source contract is extended: `source ∈ {"author_validation",
  "reviewers_json", "reviewers_promoted", "article_author_fallback"}`.
  `"reviewers_json"` remains for Bug 19's data-table promotion path;
  `"reviewers_promoted"` is the new visible-block promotion path.

### Lane N — recommender (agents/recommender.md)
- **Bug 24** — recommender prompt now explicitly enforces the 3-8
  LLM-source recommendation count for `peec-prompt-matched` articles
  with merge-or-drop guidance for the lowest-priority candidates. Closes
  the recurring "LLM-source recommendation count must be 3-8 for
  peec-prompt-matched; got 9 (or 10)" validator retry banner that
  appeared in every smoke run from Round 4 through v0.6.5 verification.
- **Bug 25** — recommender prompt now requires `addresses_prompts` ≥ 3
  per recommendation, with explicit guidance on broadening to adjacent
  prompts in the same topic cluster or engine, or dropping the rec if
  too narrow to be cost-effective. Closes the recurring "rec-NNN
  addresses_prompts must contain at least 3 prompt ids" validator retry
  banner.

### Acceptance tests
- tests/bug_22_rec_map_non_applicable_shape_test.md (Lane M)
- tests/bug_23_trust_block_visible_reviewer_source_test.md (Lane M)
- tests/bug_24_recommender_count_cap_test.md (Lane N)
- tests/bug_25_addresses_prompts_minimum_test.md (Lane N)

### Origin
v0.6.5 verification smoke `2026-04-26T11-26-06`. Spec at
`specs/2026-04-26-bugs-iteration9.md`. First iteration to validate the
`parallel-agent-orchestration` skill end-to-end.

## [0.6.5] — 2026-04-26

Iteration 8 fixes from the v0.6.4 verification smoke `2026-04-26T10-13-57`
(canonical pair: granola-chat-just-got-smarter + series-c). v0.6.4 closed
the trust-author work but the smoke surfaced 3 system bugs blocking the
quality gate even when the recommender produced correct recs and the
generator applied them. Spec at `specs/2026-04-26-bugs-iteration8.md`.
Two parallel Codex agents (gpt-5.5, reasoning_effort high).

### Lane K — validator (dashboard/quality_gate.py)
- **Bug 19** — `_validate_trust_block` now promotes a strong reviewer from
  `reviewers_json` when the source author byline fails author validation.
  Previously the validator could reject "Jack Whitton, Marketing" as too
  weak even when reviewers.json carried "Chris Pedregal, CEO &
  Co-founder" with bio + LinkedIn — the reviewer was the actual trust
  signal but the validator never consulted it. The promotion mutates
  `author_validation.status` to `"passed"` with reviewer display_name /
  display_role / reviewer_id and a detail field that explains the
  promotion. Bug 18 source contract preserved (`reviewers_json` is
  explicitly the source for the reviewer-promoted path).
- **Bug 20** — internal-source classifier now uses apex-domain equality
  instead of exact host string match. `docs.granola.ai` and
  `app.granola.ai` are now correctly counted as internal sources for
  `https://www.granola.ai/blog`. The 2-internal-source minimum is
  unchanged; only the classifier was wrong. Substring tricks
  (`granolafake.com` vs `granola.ai`) still fail the apex check.

### Lane L — generator (agents/generator.md)
- **Bug 21** — generator now enforces the GEO question_headings contract
  when the rec list contains any `engine_specific` or `geo_hygiene`
  recommendation that mentions FAQ, question H2, or question-format
  headings. Previously the generator treated FAQ recs as additive (add a
  separate FAQ block) rather than transformational (rewrite existing H2s
  in question form). The new rule requires ≥50% of body H2s (excluding
  the literal "FAQ" label) to be in question form when applicable, with
  example transformations cited.

### Acceptance tests
- tests/bug_19_trust_block_reviewer_promotion_test.md (Lane K)
- tests/bug_20_internal_source_subdomain_test.md (Lane K)
- tests/bug_21_question_h2_enforcement_test.md (Lane L)

### Origin
v0.6.4 verification smoke `2026-04-26T10-13-57`. Spec at
`specs/2026-04-26-bugs-iteration8.md`. Validation contract drift surfaced
during Marco's diagnostic review of v0.6.4 smoke YELLOW.

## [0.6.4] — 2026-04-26

Iteration 7 single-bug pre-emptive fix from Codex GPT-5.5 static audit
`specs/2026-04-26-iter7-static-audit.md` (R2 finding). The latent branch was
closed before Round 5 stress-test rotation could surface a YELLOW for
non-canonical reviewer-backed articles.

### Lane J — validator (dashboard/quality_gate.py)
- **Bug 18** — `_validate_trust_block` now always reports
  `trust_block.source == "author_validation"` whenever
  `author_validation.status == "passed"` and `display_name` is non-empty.
  Previously it wrote `trust_block.source = "reviewers_json"` when
  `reviewer_id` was non-null, despite author validation already being the
  accepted source of truth. Reviewer provenance remains preserved in
  `author_validation.reviewer_id`.

### Acceptance test
- tests/bug_18_trust_block_source_consistency_test.md (Lane J)

### Origin
Codex GPT-5.5 static audit
`specs/2026-04-26-iter7-static-audit.md` (R2 finding) — pre-empted before
Round 5 stress-test rotation could surface YELLOW.

## [0.6.3] — 2026-04-25

Iteration 6 single-bug fix from the v0.6.2 smoke run `2026-04-25T21-32-17`
(post pycache-purge re-run). Lane G's `_validate_trust_block` fix in
v0.6.2 was correct, but a second writer in `dashboard/server.py` —
`_apply_trust_author_fallback` — was clobbering the result.

### Lane I — server (dashboard/server.py)
- **Bug 17** — `_apply_trust_author_fallback` now early-returns when
  `author_validation.status == "passed"` AND `display_name` is non-empty.
  Previously it always ran after `build_article_manifest` and
  unconditionally rewrote `trust_block`, which clobbered Lane G's correct
  resolution when the source article's `trust.author` was null (granola-chat
  case where the crawler did not capture a source byline). The function's
  original purpose — applying `article_author_fallback` for empty-reviewers
  + full-name-source-author cases — is preserved when the validator has not
  yet accepted the author.

### Acceptance test
- tests/bug_17_trust_author_fallback_guard_test.md (Lane I)

### Origin
v0.6.2 smoke run `2026-04-25T21-32-17`. Spec at
`specs/2026-04-25-bugs-iteration6.md`.

## [0.6.2] — 2026-04-25

Iteration 5 bug fixes from the v0.6.1 smoke run `2026-04-25T20-12-28`.
Iteration 4 verified Bugs 11 and 12 fixed at runtime; Bug 13 was partially
fixed but covered only the explicit-reviewer-id path. Two new bugs
surfaced. Two parallel Codex agents (gpt-5.5, reasoning-effort high) on
two non-overlapping files.

### Lane G — validator (dashboard/quality_gate.py)
- **Bug 14** — `trust_block` resolution now prefers
  `author_validation.display_name` whenever `author_validation.status ==
  "passed"`, regardless of whether `reviewer_id` is set explicitly. This
  subsumes Lane F's iteration-4 fix and covers the promoted-reviewer /
  weak-source-author path that Lane F missed (granola-chat case where
  source author was "Jack" first-name-only and reviewer "Chris Pedregal"
  was promoted at recommend time without setting reviewer_id on the
  manifest). The two paths can no longer disagree on whether an author
  exists: `(trust_block.author_name == "") ⟺ (author_validation.status !=
  "passed")`.
- **Bug 16** — `question_headings` module now passes when at least 50% of
  H2s are in question format (or ≥2 question H2s when H2 count ≥ 3),
  matching the GEO contract intent. Previously the detector required every
  H2 to be a question, which caused valid articles with mixed
  question/declarative H2s to fail the module check despite hitting the
  contract spirit. Question detection recognises both literal `?` suffix
  AND H2s that start with question-words (Which/How/What/Why/When/Where/
  Who/Can/Does/Is/Are/Should), case-insensitive.

### Lane H — generator (agents/generator.md)
- **Bug 15** — generator instructions now pin the EXACT
  `rec_implementation_map` JSON shape with explicit field names. The
  v0.6.0/v0.6.1 generator drifted to writing
  `{"status": "implemented", "note": "..."}` which the validator's
  rec-implementation checker (Lane D, commit a4a7d24) rejects because it
  expects `{"implemented": true, "section": "...", "anchor": "...",
  "schema_fields": [...], "evidence_inserted": [...], "notes": "..."}`. The
  generator now follows the locked shape with explicit warnings against
  the legacy `status` and `note` field names.

### Acceptance tests
- tests/bug_14_trust_block_promoted_reviewer_test.md (Lane G)
- tests/bug_15_rec_implementation_format_test.md (Lane H)
- tests/bug_16_question_headings_detection_test.md (Lane G)

### Origin
v0.6.1 smoke run `2026-04-25T20-12-28`. Spec at
`specs/2026-04-25-bugs-iteration5.md`.

## [0.6.1] — 2026-04-25

Iteration 4 bug fixes from the v0.6.0 smoke run `2026-04-25T19-21-10`. The
v0.6.0 architecture (rubric_lint stage, framing block, trigger-driven rec
categories, manifest cross-validation) is working — both articles passed
quality_gate at audit_after 34/40 — but the smoke surfaced 3 cleanup bugs
that v0.6.1 closes. Two parallel Codex agents (gpt-5.5, reasoning-effort
high).

### Lane E — recommender + record_recommendations seam
- **Bug 11** — recommender now writes a top-level `synthesis_claims[]` entry
  alongside every `category: "claim_synthesis"` recommendation. The two
  write paths are paired: one without the other is a contract violation.
  Threshold aligned at ≥3 prompts (matching Improvement 4) — the v0.6.0
  seam check incorrectly used ≥4. `record_recommendations` now enforces:
  every claim_synthesis rec's `addresses_prompts` array MUST appear in at
  least one `synthesis_claims[].addresses_prompts`. On failure: warning
  banner + ValueError + recommender retries.

### Lane F — validator (dashboard/quality_gate.py)
- **Bug 12** — `validate_article.audit_after` now returns an integer in
  `[0, 40]` whenever module checks pass. The numeric scoring path was
  silently returning null when one of the sub-score inputs was unavailable
  for an article preset. Sub-scores now default to ZERO when their input is
  missing; missing-critical-input cases raise a specific error rather than
  null-coalescing. Regression-tested against the v0.6.0 smoke output for
  granola-chat-just-got-smarter (was null, now an integer ≥ 32).
- **Bug 13** — `trust_block` validator path consolidated with
  `author_validation`. When `reviewer_id == null` AND
  `author_validation.status == "passed"`,
  `trust_block.author_name = author_validation.display_name` and
  `trust_block.passed = true`. The two paths can no longer disagree on
  whether an author exists. The series-c case (full-name "Chris Pedregal"
  with `reviewer_id: null` failing trust_block while passing
  author_validation) is fixed.

### Acceptance tests
- tests/bug_11_synthesis_claims_pair_test.md (Lane E)
- tests/bug_12_audit_after_numeric_test.md (Lane F)
- tests/bug_13_trust_block_author_consistency_test.md (Lane F)

### Origin
v0.6.0 smoke run `2026-04-25T19-21-10`. Spec at
`specs/2026-04-25-bugs-iteration4.md`.

## [0.6.0] — 2026-04-25

Peec MCP recommendation engine overhaul. v0.5.9 closed the bug-fix loop with
both articles passing quality_gate, but a hard review of the v0.5.9 outputs
against real Peec data showed the recommender contract was too loose: same
agent produced rich `geo_gap_actions` for one article and a generic 4-item
list for another in the same run. v0.6.0 hardens the recommender's contract
end-to-end so the Peec data demonstrably translates into ranking-improving
recommendations every run.

GEO rubric hygiene is preserved via a new deterministic linter stage — not
removed.

Two parallel Codex agents (gpt-5.5, reasoning-effort high) implemented the
work across two lanes with zero file overlap.

### Lane C — Peec gap-reader hardening (input layer)
- **Improvement 1 (coverage fallback)** — when `matched_prompts == 0`, the
  gap-reader now pulls `peec_actions(scope=overview)`, source-domain gap
  report, and engine-level brand sentiment, writing them under
  `topic_level_signals.{category_gap, surface_gap, dominant_competitor_domains,
  engine_sentiment}`. Engineering posts no longer fall back to GEO-rubric-only
  output.
- **Improvement 2 (signal richness)** — `position_per_engine`,
  `sentiment_per_engine`, `citation_score_per_engine` are now always emitted
  (null-keyed when unavailable, never absent). Every `cited_competitor` is
  tagged with a classification ∈
  `{COMPETITOR | EDITORIAL | CORPORATE | UGC | REFERENCE}`. `top_gap_chats[]`
  is required non-empty for every prompt where `engines_lost.length >= 2` —
  fixes the inconsistency where one article's gap data had chat excerpts and
  another's did not in the same run.

### Lane D — Recommender output overhaul (output layer)
- **Improvement 3 (sentiment-driven recs)** — when any engine's sentiment is
  below the 65 floor, the recommender MUST emit a `category: "sentiment"` rec
  with the engine, the gap-to-floor, and a verbatim `top_gap_chats` excerpt as
  evidence. The "ChatGPT sentiment 64 — invisible in the output" failure is
  now a contract violation.
- **Improvement 4 (claim-level synthesis)** — when ≥3 prompts share a clear
  underlying claim, the recommender groups them into one
  `category: "claim_synthesis"` rec with the synthesised positioning sentence,
  the addressed prompts, and section target. Replaces 5 atomic same-cluster
  recs.
- **Improvement 5 (rubric demotion)** — new module `dashboard/rubric_lint.py`
  with 13 enumerated deterministic checks (meta description, OG/Twitter tags,
  JSON-LD, FAQ schema, BreadcrumbList, Person, Organization, CTA, byline,
  updated_at, internal links). New MCP tool `rubric_lint(run_id, slug)` runs
  pre-recommender and writes `rubric/{slug}.json`. The recommender consumes
  this artefact and is explicitly forbidden from regenerating rubric items —
  its tokens go to synthesis only.
- **Improvement 6 (category/brand/competition framing)** — required output
  fields `category_lens`, `brand_lens`, `competition_lens` synthesise where
  the article sits in the topic cluster, the brand-level engine pattern, and
  the competition-class strategy implication. Each lens has structured
  aggregations plus a 2–3 sentence summary.
- **Improvement 7 (engine-specific tactics)** — when
  `max(visibility_per_engine) - min(visibility_per_engine) >= 0.40` for any
  prompt, recommender MUST emit a rec with distinct `per_engine_lift`
  narratives per engine. Engine-tactic templates encoded:
  ChatGPT-dark→editorial-listicles+FAQ; Perplexity-dark→inline-evidence+author-trust;
  Google-AIO-strong→maintain-schema+word-count.
- **Improvement 8 (off-page action lane)** — new `category: "off_page"` rec
  type and top-level `off_page_actions[]` array. Triggered when
  `peec_actions.overview_top_opportunities` shows
  `gap_percentage >= 50 AND relative_score >= 2`. Off-page recs are not
  counted against the on-page rec budget.
- **Improvement 9 (source-classification → strategy mapping)** — when ≥4
  prompts dominated by `EDITORIAL` competitors, recommender emits a
  `category: "source_displacement"` rec with `competitors_displaced[]` and an
  off-page outreach play. Maps to the dominant classification: EDITORIAL →
  outreach + owned listicle; COMPETITOR → comparison/positioning; CORPORATE/
  REFERENCE → entity/schema; UGC → distribution.
- **Improvement 10 (manifest cross-validation)** — the optimised manifest now
  carries a required `rec_implementation_map` keyed by rec ID, with `section`,
  `anchor`, `schema_fields[]` or `evidence_inserted[]`, and notes for
  implemented recs. The validator (`dashboard/quality_gate.py`) FAILS the
  article if any `priority: critical` LLM-source rec is missing or
  unimplemented without a valid `reason`. Brilliant recs that the generator
  silently ignored are now caught at validation time.

### Schema enforcement
- `record_recommendations` no longer just validates "exactly 4 items." Replaced
  with full v0.6.0 contract: required top-level fields (category_lens,
  brand_lens, competition_lens, engine_gap_strategy, primary_gaps, mode,
  audit, summary, recommendations); LLM-source rec count in [3, 8] for Peec
  modes, [2, 6] for voice-rubric; per-rec required fields (id, source,
  category, severity, priority, signal_types[≥1], evidence[≥1]); LLM-source
  recs additionally need target_engines[≥1] + per_engine_lift; ≥3 distinct
  signal_types across the LLM set in Peec modes; sentiment / engine-asymmetry
  / off-page / source-displacement / claim-synthesis triggers all enforced at
  the seam. Validation failure surfaces a banner via `show_banner` and
  rejects the write; the recommender retries up to 2 times.

### Acceptance tests
- tests/improvement_01_coverage_fallback_test.md (Lane C)
- tests/improvement_02_signal_richness_test.md (Lane C)
- tests/improvement_03_sentiment_recs_test.md (Lane D)
- tests/improvement_04_claim_synthesis_test.md (Lane D)
- tests/improvement_05_rubric_lint_test.md (Lane D)
- tests/improvement_06_framing_block_test.md (Lane D)
- tests/improvement_07_engine_specific_test.md (Lane D)
- tests/improvement_08_off_page_lane_test.md (Lane D)
- tests/improvement_09_source_displacement_test.md (Lane D)
- tests/improvement_10_manifest_cross_val_test.md (Lane D)

### Origin
v0.5.9 smoke run `2026-04-25T17-49-21` (granola-chat-just-got-smarter +
series-c) plus the earlier 3-article run `2026-04-25T10-45-39`. Spec at
`specs/2026-04-25-peec-improvements-v2.md`.

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
