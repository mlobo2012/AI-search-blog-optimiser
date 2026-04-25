# v0.6.2 Iteration 6 Bug Fix (target: v0.6.3)

Origin: v0.6.2 smoke run `2026-04-25T21-32-17` after pycache purge. Lane G's fix in `dashboard/quality_gate.py::_validate_trust_block` is correct and verified at the import/function level. But a SECOND trust_block writer in `dashboard/server.py::_apply_trust_author_fallback` runs immediately after `build_article_manifest` in the `validate_article` MCP tool path and overwrites Lane G's correct trust_block with stale data.

This is a one-line-class fix in one file, but it's the last thing blocking GREEN.

---

## Lane assignment

- **Lane I** (Codex Agent I): Bug 17 — `_apply_trust_author_fallback` early-return guard. File: `dashboard/server.py`.

Branch off `feat/v0.6.0-integration` head (commit `cdcafa2`). Worktree `~/conductor/workspaces/ai-search-blog-optimiser/lane-i-iter6`.

---

## Bug 17 — `_apply_trust_author_fallback` overwrites correct trust_block

**Owner: Lane I.**

### Symptom

In v0.6.2 smoke run `2026-04-25T21-32-17`:

- Both articles: `author_validation = {status: "passed", display_name: "Chris Pedregal", reviewer_id: null, ...}` (correct)
- Both articles: `trust_block = {passed: false, source: "reviewers_json", author_name: ""}` (WRONG — should be `{passed: true, source: "author_validation", author_name: "Chris Pedregal"}`)
- Quality gate scoring is unaffected (`trust_author` check uses `author_validation.status` directly, awards 6/6) so the gate passes.
- BUT the diagnostic `trust_block` field violates the contract.

### Root cause (verified)

In `dashboard/server.py::_tool_validate_article` (around line 3290):

```python
manifest = build_article_manifest(run_dir, article_slug, audit_after=args.get("audit_after"))
_apply_internal_link_domain_fix(run_dir, article_slug, manifest)
_apply_trust_author_fallback(run_dir, article_slug, manifest)   # ← overwrites trust_block
_persist_manifest_and_update_draft_state(run_dir, article_slug, manifest)
```

`build_article_manifest` calls `_validate_trust_block` (Lane G's fix) which correctly sets `trust_block = {passed: True, source: "author_validation", author_name: "Chris Pedregal"}`.

Immediately after, `_apply_trust_author_fallback` (defined at `dashboard/server.py:2940`) runs:

```python
def _apply_trust_author_fallback(run_dir, article_slug, manifest):
    article = _read_json(...)
    author = (article.get("trust") or {}).get("author") or {}
    author_name = str(author.get("name") or "").strip()
    # ...
    if reviewers or not _has_first_and_last_name(author_name):
        trust_block.update({
            "passed": False,
            "source": "reviewers_json" if reviewers else None,
            "author_name": author_name,
        })
        return
```

For granola-chat-just-got-smarter in this run, `article.trust.author` is `null` (the crawler did not extract a source author). So `author = {}`, `author_name = ""`. `reviewers` is non-empty (Chris Pedregal exists in reviewers.json). `not _has_first_and_last_name("")` is True. The condition `reviewers or not _has_first_and_last_name(author_name)` short-circuits to True (reviewers truthy). Falls into the failure branch and OVERWRITES Lane G's correct trust_block with `{passed: false, source: "reviewers_json", author_name: ""}`.

The function does not check whether `author_validation.status == "passed"` before clobbering.

### Fix

Add an early-return guard at the top of `_apply_trust_author_fallback`:

```python
def _apply_trust_author_fallback(run_dir, article_slug, manifest):
    # If the validator already accepted the author via author_validation, do not override.
    # The existing trust_block from _validate_trust_block is the source of truth in that case.
    author_validation = manifest.get("author_validation")
    if isinstance(author_validation, dict) \
       and author_validation.get("status") == "passed" \
       and str(author_validation.get("display_name") or "").strip():
        return

    # ... existing logic unchanged
```

This preserves the function's existing fallback purpose (handling cases where the crawler captured a full-name source author and reviewers.json is empty) while respecting Lane G's `_validate_trust_block` resolution when it has already passed.

### Acceptance test

Add `tests/bug_17_trust_author_fallback_guard_test.md`:

1. Fixture A (Lane G success path): article where `author_validation.status == "passed"`, `display_name == "Chris Pedregal"`, `reviewer_id` may be null, `article.trust.author` may be null or have a different name. After validate_article: `trust_block.passed == true`, `trust_block.author_name == "Chris Pedregal"`. The fallback function does NOT override.

2. Fixture B (preserved fallback path — empty reviewers + full-name source author): `author_validation.status == "passed"` but coming from article author (no reviewers configured). After validate_article: `trust_block.source == "article_author_fallback"`, `trust_block.author_name == <source_author_name>`, `trust_block.passed == true`. Verifies the function still works for its original use case.

3. Fixture C (genuine failure: source author missing AND author_validation failed AND reviewers exist): After validate_article: `trust_block.passed == false`. The function applies its existing failure logic. Confirms the guard does not break failure cases.

4. Negative regression: `trust_block.author_name == ""` only when `author_validation.status != "passed"`.

---

## Definition of done

- Acceptance test passes.
- Re-run the Granola 2-article smoke (granola-chat + series-c). Expected outcomes:
  - `trust_block.passed == true` on both articles.
  - `trust_block.author_name == author_validation.display_name` on both articles (zero divergence).
  - All v0.6.0 architecture intact.
  - All iteration 4 + 5 fixes still hold.
  - **Both articles pass `quality_gate` AND `audit_after >= 32`.**
  - Zero banner warnings, zero runtime errors, zero schema validation failures.
- `plugin.json` bumped to `0.6.3`.
- `CHANGELOG.md` documents Bug 17 fix.
- Marketplace cache + `marketplace.json` synced to 0.6.3 with explicit `__pycache__` exclusion in rsync.
- After v0.6.3 ships and smoke verifies GREEN on the canonical pair: rotate in 2 NEW Granola articles for the stress-test smoke per Marco's loop policy.

## Non-goals (explicit)

- Do NOT remove `_apply_trust_author_fallback` entirely — it still serves the empty-reviewers + full-name-source-author case.
- Do NOT refactor `_validate_trust_block` — Lane G's fix is correct.
- Do NOT touch `dashboard/quality_gate.py`, `dashboard/rubric_lint.py`, or any other file.
- Do NOT address the granola-chat evidence pack 404 (TechTarget URL during crawl) — park for v0.7.0 robustness work.

## Side note for v0.7.0 (non-blocking, parking-lot items)

- Evidence-builder fallback when a configured external citation source returns 404 during crawl (granola-chat hit this in run 21-32-17, only 1 of 2 required external sources made it through).
- Add visible operator banner when generator promotes a reviewer over a weak source author (so the author-substitution behavior is auditable).
- Decide whether the v0.5.9 → v0.6.0 audit_before scoring shift (now stricter via rubric_lint) deserves a normalisation note in the dashboard.
