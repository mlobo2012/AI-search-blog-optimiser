# v0.6.0 Iteration 4 Bug Fixes (target: v0.6.1)

Origin: v0.6.0 smoke run `2026-04-25T19-21-10` (granola-chat-just-got-smarter + series-c). YELLOW verdict — architecture works, both articles pass quality_gate at audit_after 34/40, but 3 specific bugs prevent GREEN.

The 3 bugs do NOT regress the v0.6.0 architecture. They're cleanup work at the seams.

---

## Lane assignment (clean — zero file overlap)

- **Lane E** (Codex Agent E): Bug 11 (synthesis_claims population + threshold consistency). Files: `agents/recommender.md`, `dashboard/server.py`.
- **Lane F** (Codex Agent F): Bugs 12+13 (audit_after null + trust_block divergence). Files: `dashboard/quality_gate.py`.

Branch off `feat/v0.6.0-integration` head (commit `0ab540b`). Worktrees `~/conductor/workspaces/ai-search-blog-optimiser/lane-e` and `~/conductor/workspaces/ai-search-blog-optimiser/lane-f`.

---

## Bug 11 — `synthesis_claims[]` not populated when claim_synthesis rec fires

**Owner: Lane E.**

### Symptom

In v0.6.0 smoke run `2026-04-25T19-21-10`:

- granola-chat-just-got-smarter `recommendations/{slug}.json`:
  - `recommendations[]` contains rec-016 with `category: "claim_synthesis"` and `addresses_prompts: [pr_xxx, pr_yyy, pr_zzz]` (3 prompts in cross-meeting-search cluster)
  - Top-level `synthesis_claims[]` is `[]` (empty)
- series-c `recommendations/{slug}.json`:
  - `recommendations[]` contains 3 claim_synthesis recs (rec-015, rec-016, rec-017)
  - Top-level `synthesis_claims[]` correctly contains 3 entries

The contract requires both: a `claim_synthesis` rec AND a corresponding `synthesis_claims[]` entry. Inconsistent execution between articles.

Plus an internal spec inconsistency: `specs/2026-04-25-peec-improvements-v2.md` says under Improvement 4 "Cluster threshold: ≥3 prompts that share a clear semantic claim → 1 synthesised rec" but the record_recommendations seam validation says "≥4 prompts share a common claim cluster → ... claim_synthesis rec ... AND ... synthesis_claims[] entry." Two thresholds for the same feature.

### Root cause

Two issues:

1. **`agents/recommender.md`** — the prompt instructs the LLM to emit a claim_synthesis rec when ≥3 prompts cluster but does not explicitly require the LLM to ALSO write a top-level `synthesis_claims[]` entry. The LLM produces the rec correctly but skips the parallel write path.
2. **`dashboard/server.py`** — `_tool_record_recommendations` uses ≥4 as the cluster threshold for the `synthesis_claims` validation check, but the recommender prompt uses ≥3. Mismatched thresholds mean the seam can pass even when the architecture is half-implemented.

### Fix

In `agents/recommender.md`:

- Add explicit instruction: "When you emit a `category: \"claim_synthesis\"` recommendation, you MUST ALSO add a corresponding entry to top-level `synthesis_claims[]` with the same `addresses_prompts` array, the synthesised `claim` sentence, the `section_target`, and `evidence_refs`. The two write paths must be paired — one without the other is a contract violation."
- Lock the threshold at ≥3 prompts (matching Improvement 4's "Cluster threshold: ≥3 prompts").

In `dashboard/server.py`:

- Update the validation rule in `_tool_record_recommendations`:
  - Change cluster threshold from ≥4 to ≥3 to align with the recommender prompt.
  - Add a strict pair check: if any rec has `category == "claim_synthesis"`, then `synthesis_claims[]` MUST be non-empty AND every claim_synthesis rec's `addresses_prompts` MUST appear in at least one `synthesis_claims[].addresses_prompts` array.
  - On failure: call `show_banner` with `level: "warning"` and details; raise ValueError; recommender retries.

### Acceptance test

Add `tests/bug_11_synthesis_claims_pair_test.md`:

1. Fixture: 3 prompts share a clear claim cluster.
2. Run recommender.
3. `recommendations/{slug}.json` contains ≥1 rec with `category == "claim_synthesis"`.
4. Top-level `synthesis_claims[]` is non-empty.
5. For every claim_synthesis rec, its `addresses_prompts` array appears in at least one `synthesis_claims[].addresses_prompts`.
6. Reject path: if `synthesis_claims[]` is left empty after a claim_synthesis rec is emitted, the record_recommendations validation FAILS (banner + ValueError) and rejects the write.

---

## Bug 12 — `validate_article.audit_after` returns null

**Owner: Lane F.**

### Symptom

In v0.6.0 smoke run `2026-04-25T19-21-10`:

- granola-chat-just-got-smarter:
  - Generator self-reported `audit_after: 34`
  - `validate_article` returned `audit_after: null`
  - Module checks all green (FAQ, schema, byline, internal_links, etc.)
  - quality_gate.passed: true (because module checks all green; numeric score is not in the gate path)

- series-c:
  - Generator self-reported `audit_after: 34`
  - `validate_article` returned `audit_after: 34` (correct)

Inconsistent: same validator code path returns the score for one article and null for the other, even though both articles pass module checks.

### Root cause (hypothesis — Codex must verify)

Most likely candidates in `dashboard/quality_gate.py`:

1. The numeric scoring path checks for an HTML/markdown render that's missing for one article (e.g., the HTML field name differs between announcement_update and series-c presets).
2. A try/except silently catches the scoring failure and returns null.
3. A missing field guard (`if X: score += 1`) that returns null instead of zero when X is None.

Codex must inspect `_validate_article` / `build_article_manifest` numeric scoring code paths and identify the actual divergence.

### Fix

In `dashboard/quality_gate.py`:

- Identify why `audit_after` is null for granola-chat-just-got-smarter and 34 for series-c when both pass module checks.
- Make the numeric scoring path deterministic and resilient: when a check can't compute its sub-score, the sub-score is zero, NOT null. The aggregate score is always an integer in [0, 40].
- If a critical input (rendered HTML, schema package, manifest) is missing, raise a specific error, do not silently null-coalesce.

### Acceptance test

Add `tests/bug_12_audit_after_numeric_test.md`:

1. Fixture: rendered article with all module checks passing.
2. Run `validate_article`.
3. `validate_article` result has `audit_after` as an integer in [0, 40].
4. `audit_after` is NEVER null when `quality_gate.passed == true`.
5. `audit_after` is NEVER null when `module_checks.failed_count == 0`.
6. Regression case: re-run validation on the v0.6.0 smoke output for granola-chat-just-got-smarter; `audit_after` returns an integer ≥ 32, not null.

---

## Bug 13 — `trust_block` validator divergence when `reviewer_id` is null

**Owner: Lane F.**

### Symptom

In v0.6.0 smoke run `2026-04-25T19-21-10` for series-c:

- `validate_article.trust_block.passed: false`
- `validate_article.trust_block.author_name: ""`
- `validate_article.author_validation.status: "passed"`
- `validate_article.author_validation.display_name: "Chris Pedregal"`
- HTML byline: "Chris Pedregal, CEO & Co-founder"
- Manifest: `reviewer_id: null` (no reviewer needed because article author is full-name passing on its own)

The validator has two author-checking paths that diverge:

- `author_validation.*` reads the visible byline directly. Sees "Chris Pedregal" → passes.
- `trust_block.*` reads `reviewer_id` to look up `reviewers.json`. When `reviewer_id` is null, falls through to `author_name: ""` instead of falling back to `author_validation.display_name`.

### Root cause

`trust_block` validator path doesn't have a fallback to `author_validation.display_name` when `reviewer_id` is null. It treats `reviewer_id == null` as "no author", which is wrong — `reviewer_id` is null because the source author is full-name passing and doesn't need a reviewer substitution.

### Fix

In `dashboard/quality_gate.py`:

- Consolidate `_validate_trust_block` and `_validate_author` to share a single resolved-author source of truth.
- When `reviewer_id` is null AND `author_validation.status == "passed"`: `trust_block.author_name = author_validation.display_name`.
- When `reviewer_id` is set: `trust_block.author_name` resolves through `reviewers.json` as today.
- When neither is valid: `trust_block.passed = false, trust_block.author_name = ""` — current behaviour, retained.
- The two paths should never disagree on whether an author exists.

### Acceptance test

Add `tests/bug_13_trust_block_author_consistency_test.md`:

1. Fixture: article with `reviewer_id: null` and a full-name author "Chris Pedregal" in HTML.
2. Run `validate_article`.
3. `trust_block.passed == true`.
4. `trust_block.author_name == "Chris Pedregal"`.
5. `trust_block.author_name == author_validation.display_name` (no divergence).
6. Negative fixture: article with first-name-only byline "Jack" and `reviewer_id: null` — both `trust_block.passed` and `author_validation.status` should be false (consistent failure).

---

## Definition of done (whole iteration 4 spec)

- All 3 bug acceptance tests pass.
- Re-run the Granola 2-article smoke (granola-chat + series-c). Expected outcomes:
  - All 4 v0.5.4 exit criteria green: stages clean, no banner warnings, audit_after >= 32 both, quality_gate passed both.
  - `synthesis_claims[]` populated whenever a `category: claim_synthesis` rec exists (granola-chat now passes this check).
  - `audit_after` returns an integer (not null) for both articles.
  - `trust_block.author_name` matches `author_validation.display_name` for both articles.
- `plugin.json` bumped to `0.6.1`.
- `CHANGELOG.md` documents the 3 bug fixes.
- Marketplace cache + `marketplace.json` synced to 0.6.1.
- After v0.6.1 ships, run a SECOND smoke on 2 NEW articles (rotate in 2 different Granola articles) to stress-test the v0.6.0 contract on uncovered ground per Marco's directive.

## Non-goals (explicit, per Marco's "park quality misses in v0.7.0" policy)

- Do NOT attempt to re-architect the validator or recommender beyond these 3 bugs.
- Do NOT add the author-substitution banner (parked for v0.7.0).
- Do NOT add the audit_before regression normalisation (parked for v0.7.0).
- Do NOT change rubric_lint thresholds or item set.
