# Bug-fix Spec — Iteration 3 (target: v0.5.9)

Source: live `claude -p` smoke run on 2026-04-25 against `granola.ai/blog --max-articles 2`, plugin v0.5.8. Run id `2026-04-25T16-51-56`.

The v0.5.8 fixes mostly held: JSON-LD embedding ✅, subdomain links ✅, author fallback ✅. **Both articles' `audit_after` now ≥ 32** (granola=36, series=35) — exit criterion (c) is met. But `quality_gate` still says **failed** on both because of two specific gaps the v0.5.8 spec didn't fully cover. This iteration closes those two so quality_gate goes "passed".

Both fixes are in `dashboard/quality_gate.py`. Single lane (Lane G), one Codex agent, two atomic commits.

---

## Bug 9 — Validator's HTML snapshot parser must extract FAQ questions from `<dl><dt>` elements

### Reproduction (run `2026-04-25T16-51-56`)

- Generator (v0.5.8 Bug 7 fix) correctly emits FAQ as `<dl><dt>question</dt><dd>answer</dd></dl>` — confirmed by the v0.5.8 smoke report ("html_types = BlogPosting, BreadcrumbList, FAQPage, Organization, Person, Question, Answer").
- Validator returns `faq_questions_visible: []` for both articles.
- Cause: `_HTMLSnapshotParser` in `dashboard/quality_gate.py` (lines ~304+) only collects FAQ candidates from `<h1>`–`<h3>` heading text. It does not track `<dt>` elements when nested in `<dl>`.

### Fix scope

`dashboard/quality_gate.py` only:

- Extend `_HTMLSnapshotParser` to track `<dl>` nesting depth and `<dt>` element text content.
- Add `dt_questions: list[str]` to `HTMLSnapshot` (or merge into the existing `faq_questions` list).
- Update the `faq_questions` property (line ~304) to return the union of `<h1>`-`<h3>` heading-style FAQs AND `<dt>` elements (deduplicated, in document order).
- Question heuristic: a `<dt>` text counts as a FAQ question if it ends with `?` OR if it follows the same heading-style pattern already in use for `<h1>`-`<h3>` extraction.
- Don't break existing heading-based FAQ extraction (some articles use heading-form FAQs).

### Acceptance test

`tests/bug_09_dt_faq_extraction_test.md` (NEW):

1. Construct an HTML fixture with both styles:
   ```html
   <h2>What is Granola Chat?</h2>
   <p>An agentic chat interface for your meeting notes.</p>

   <dl>
     <dt>How do I add my team?</dt>
     <dd>Open Settings → Team Space and invite by email.</dd>
     <dt>Does Granola work offline?</dt>
     <dd>Yes, Granola caches notes locally.</dd>
   </dl>
   ```
2. Pass through `_HTMLSnapshotParser`. Assert `faq_questions` (or new combined property) contains all 3 questions in document order.
3. Run `validate_article` on a Granola fixture article that uses `<dl><dt><dd>` FAQ blocks (per Bug 7 generator output). Assert manifest `faq_questions_visible.length >= 1`.

---

## Bug 10 — Trust block accepts single-name authors when `trust.author.role` is populated

### Reproduction

- `granola-chat-just-got-smarter` has byline `"Jack"` (single name).
- v0.5.8 Bug 8 added an `article_author_fallback` that requires the author name to contain a space (i.e., first + last name) to qualify when `reviewers.json` is empty.
- For engineering-team posts on granola.ai (and many similar sites) the convention is first-name-only. The author has a documented `role` (e.g. "Engineering Lead", "Software Engineer") in `articles/{slug}.json` `trust.author.role`. That role is itself a real trust signal — the post is from a named, role-bearing employee.
- Result: `trust_block.passed = false` for the granola-chat article in v0.5.8 even though the author is identified.

### Fix scope

`dashboard/quality_gate.py` only — likely in `_validate_author` or wherever the author validation status is determined (the v0.5.8 fallback added in server.py does post-processing; the underlying `author_validation["status"]` is computed in quality_gate.py):

- Modify the author validation logic so an author qualifies when:
  - The author has first + last name (existing rule), OR
  - The author has a single name AND a non-empty `trust.author.role` field that contains a real role (≥ 4 characters; not a common stop-word like "and"/"the").
- When the single-name+role path is taken, set `author_validation.detail` (or equivalent) to surface that this is a single-name-with-role match so the manifest is honest about why it passed.
- The server.py post-processor's `article_author_fallback` should continue to flow naturally; if quality_gate.py's `_validate_author` now passes single-name+role, the post-processor sees `author_validation["status"] == "passed"` and the trust_block result follows.

### Acceptance test

`tests/bug_10_single_name_with_role_trust_test.md` (NEW):

1. Construct a fixture article with `trust.author = {"name": "Jack", "role": "Engineering Lead"}` and `reviewers.json = []`.
2. Run `validate_article`. Assert `trust_block.passed == true` and `author_validation.status == "passed"` and `author_validation.detail` mentions single-name-with-role.
3. Construct a fixture with `trust.author = {"name": "Jack", "role": ""}` (no role). Assert `trust_block.passed == false` (single name without role still fails).
4. Construct a fixture with `trust.author = {"name": "Chris Pedregal", "role": ""}` (full name, no role). Assert `trust_block.passed == true` (full name still works without role, per Bug 8).
5. Re-run the smoke against the live `granola-chat-just-got-smarter` article. Assert `trust_block.passed == true`.

---

## Lane assignment

- **Lane G** (Codex Agent G): Bugs 9 + 10. Branch `fix/v0.5.9-lane-g` off `fix/v0.5.8-bugs-integration`. Worktree `~/conductor/workspaces/ai-search-blog-optimiser/lane-g`.
- Files: `dashboard/quality_gate.py` (both bugs), two new acceptance test files. **Do NOT touch** `dashboard/server.py`, `agents/generator.md`, or `skills/`.

Two atomic commits, conventional messages.

After the lane closes: merge into `fix/v0.5.9-bugs-integration`, bump `plugin.json` to `0.5.9`, update CHANGELOG, sync to marketplace cache, re-run the 2-article smoke.

## Definition of done (whole iteration 3)

- Both acceptance tests pass.
- Re-run smoke produces:
  - `granola-chat-just-got-smarter`: `quality_gate == "passed"`, `audit_after ≥ 32`, `trust_block.passed == true`, `faq_questions_visible.length ≥ 1`.
  - `series-c`: `quality_gate == "passed"`, `audit_after ≥ 32`, `faq_questions_visible.length ≥ 1`.
- All four exit criteria for the v0.5.4 bug-fix loop go GREEN.
- `plugin.json` bumped to `0.5.9`.
- CHANGELOG documents iteration 3.
