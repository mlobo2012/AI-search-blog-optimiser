# v0.6.1 Iteration 5 Bug Fixes (target: v0.6.2)

Origin: v0.6.1 smoke run `2026-04-25T20-12-28` (granola-chat-just-got-smarter + series-c). YELLOW verdict. Iteration 4's fixes verified at runtime for Bug 11 and Bug 12. Bug 13 partially fixed (only the named regression case). 2 new bugs surfaced.

The v0.6.0 architecture is solid — rubric_lint, framing block, all 5 trigger-driven categories, manifest cross-validation, synthesis_claims pairing — all working. These 3 bugs are validator-side seam issues + one generator format drift.

---

## Lane assignment (clean — zero file overlap)

- **Lane G** (Codex Agent G): Bugs 14 (trust_block promoted-reviewer path) + 16 (question_headings detection). File: `dashboard/quality_gate.py`.
- **Lane H** (Codex Agent H): Bug 15 (generator rec_implementation_map format drift). File: `agents/generator.md`.

Branch off `feat/v0.6.0-integration` head (commit `a3b47a3`). Worktrees `~/conductor/workspaces/ai-search-blog-optimiser/lane-g-iter5` and `~/conductor/workspaces/ai-search-blog-optimiser/lane-h-iter5` (lane-g already exists from a prior iteration; using suffix to avoid collision).

---

## Bug 14 — `trust_block` validator divergence on promoted-reviewer / weak-source-author path

**Owner: Lane G.**

### Symptom

In v0.6.1 smoke run `2026-04-25T20-12-28` for granola-chat-just-got-smarter:

- Source article author: "Jack" (first-name-only, weak byline)
- Promoted reviewer (from `site/reviewers.json`): "Chris Pedregal" (CEO & Co-founder)
- Validator output:
  - `author_validation.status: "passed"`
  - `author_validation.display_name: "Chris Pedregal"`
  - `trust_block.passed: false`
  - `trust_block.author_name: "Jack"` ← reading source author, not promoted reviewer

The series-c case (Bug 13's named regression) was fixed by Lane F because series-c had `reviewer_id: "chris-pedregal"` set explicitly. But granola-chat-just-got-smarter has the reviewer promoted at recommend time without the explicit `reviewer_id` field being set on the manifest. The trust_block reader fell back to source `trust.author.name` instead of consulting `author_validation.display_name`.

### Root cause

Lane F's consolidation in `dashboard/quality_gate.py` only picks up the promoted reviewer when the reviewer is matched explicitly by `reviewer_id` from `reviewers.json`. There's a second path — the recommender promotes the reviewer at recommendation time and the generator renders "Chris Pedregal" in the HTML, but the manifest carries the source author "Jack" in `trust.author.name`. The trust_block reader resolves through `trust.author.name` ahead of `author_validation.display_name`.

### Fix

In `dashboard/quality_gate.py`:

- The trust_block resolution must use `author_validation.display_name` as the source of truth whenever `author_validation.status == "passed"`.
- Specifically: when computing `trust_block.author_name`, prefer `author_validation.display_name` over `trust.author.name`.
- When `author_validation.status == "passed"`: `trust_block.passed = true`, `trust_block.author_name = author_validation.display_name`. This holds regardless of whether `reviewer_id` is set.
- When `author_validation.status != "passed"`: existing failure logic stays.
- The two paths must agree on whether an author exists — `trust_block.author_name == "" ⟺ author_validation.status != "passed"`.

This should subsume Lane F's earlier fix without breaking the series-c case.

### Acceptance test

Add `tests/bug_14_trust_block_promoted_reviewer_test.md`:

1. Fixture A (granola-chat regression case): article with `trust.author.name = "Jack"` (weak), promoted reviewer "Chris Pedregal" rendered in HTML, `author_validation.status = "passed"`, `author_validation.display_name = "Chris Pedregal"`.
2. After validate_article: `trust_block.passed == true`, `trust_block.author_name == "Chris Pedregal"`, no divergence with `author_validation.display_name`.
3. Fixture B (series-c case retained): article with explicit reviewer_id, full-name source author. Trust_block also resolves to display_name. Confirms Lane F's fix didn't regress.
4. Negative fixture: article with first-name-only author and no reviewer promotion. `author_validation.status == "failed"`, `trust_block.passed == false`, `trust_block.author_name == ""`. No divergence.

---

## Bug 16 — `question_headings` module detector fails to register valid question-format H2s

**Owner: Lane G.**

### Symptom

In v0.6.1 smoke run `2026-04-25T20-12-28` for granola-chat-just-got-smarter:

- Generator added 3 question-format H2s: "Which AI meeting assistant is best for searching across all past meetings?", "How does Granola Chat search across all your meeting notes?", "How Granola Chat differs from other meeting note-takers" (one is technically not interrogative).
- Validator's `question_headings` module check returned a failure status despite question-format H2s being present in the rendered HTML.
- This contributes to `quality_gate.passed: false` even though `audit_after: 36`.

### Root cause (hypothesis — Codex must verify)

Most likely candidates in `dashboard/quality_gate.py`:

1. The detector is regex-matching only literal "?" suffix and treating the third H2 as failing the check (which would still produce a "passed" status since 2 of 3 should be enough for the module).
2. The detector counts ALL H2s, including marketing-section H2s, against a minimum threshold; if some of the H2s are non-question, the module fails despite ≥1 question H2 being present.
3. The detector requires every H2 to be a question, not at least N of them, mismatching the GEO contract which requires question-format H2s to be the dominant form, not exclusive.

Codex must inspect `_validate_question_headings` (or equivalent) and identify the actual divergence.

### Fix

In `dashboard/quality_gate.py`:

- Question-headings module passes when AT LEAST 50% of H2s are in question format (matching the GEO contract's "question_headings should mirror likely user prompts whenever the article type allows").
- Alternative if 50% is too aggressive: ≥2 of the H2s are question-format AND total H2 count >= 3.
- Question detection: H2 ends with "?" OR starts with question-words (Which, How, What, Why, When, Where, Who, Can, Does, Is, Are, Should).
- The detector must NOT require every H2 to be a question.

### Acceptance test

Add `tests/bug_16_question_headings_detection_test.md`:

1. Fixture A (granola-chat regression case): rendered HTML with 4 H2s, 3 of which are question-format.
2. After validate_article: `module_checks.question_headings.status == "passed"`.
3. Fixture B (negative): rendered HTML with 4 H2s, 0 of which are question-format. Module fails.
4. Fixture C (boundary): rendered HTML with 4 H2s, 2 are question-format (50% threshold). Module passes.
5. The detector recognises question-words at the start of an H2 even when the literal "?" is missing.

---

## Bug 15 — Generator emits wrong `rec_implementation_map` entry shape

**Owner: Lane H.**

### Symptom

In v0.6.1 smoke run `2026-04-25T20-12-28` for series-c (and likely all articles):

- Generator wrote rec_implementation_map entries as:
  ```json
  {"rec-llm-001": {"status": "implemented", "note": "..."}}
  ```
- Validator expected (per v0.6.0 spec Improvement 10):
  ```json
  {"rec-llm-001": {"implemented": true, "section": "...", "anchor": "...", "schema_fields": [...], "evidence_inserted": [...], "notes": "..."}}
  ```
- Validator's rec_implementation checker rejects rec-llm-001 and rec-llm-005 → quality_gate.passed: false → audit_after loses 2 points.

### Root cause

The generator's prompt in `agents/generator.md` instructs it to populate rec_implementation_map but does not pin the EXACT field shape. The LLM defaulted to a `{"status": "...", "note": "..."}` shape that resembles other status fields elsewhere in the manifest — natural drift, not a hallucination.

### Fix

In `agents/generator.md`:

- Find the section that instructs the generator to populate `rec_implementation_map`.
- Replace any loose description with an explicit, exact JSON template the generator MUST follow:

```json
{
  "rec-001": {
    "implemented": true,
    "section": "<section_id_or_h2_anchor>",
    "anchor": "<HTML_anchor_or_heading_text>",
    "schema_fields": ["meta.description", "ld.FAQPage"],
    "evidence_inserted": ["peec_prompt_pr_xxx", "peec_signal_engine_pattern_asymmetry"],
    "notes": "<one-line summary of what the generator did>"
  },
  "rec-002": {
    "implemented": false,
    "reason": "non-applicable"
  }
}
```

- DO NOT use `status`. The field name is `implemented` and its value is BOOLEAN (`true` or `false`).
- For implemented:true entries: `section`, `anchor`, AND at least one of `schema_fields[]` or `evidence_inserted[]` are required.
- For implemented:false entries: `reason` is required and MUST be one of `"non-applicable"`, `"superseded_by_<rec_id>"`, `"data_missing"`.
- Do not invent any other fields.

Add an explicit warning line: "Do NOT use the field name 'status' or 'note' for rec_implementation_map entries. The field is 'implemented' (boolean) and entries must follow the exact shape above. The validator (`dashboard/quality_gate.py`) rejects any entry with a different shape."

### Acceptance test

Add `tests/bug_15_rec_implementation_format_test.md`:

1. Fixture: rec set with 2 critical LLM-source recs.
2. Run generator.
3. Manifest's `rec_implementation_map.rec-001` has key `implemented` (boolean true), NOT `status` (string).
4. Manifest's `rec_implementation_map.rec-001.section` is non-empty.
5. Manifest's `rec_implementation_map.rec-001.anchor` is non-empty.
6. Manifest's `rec_implementation_map.rec-001` has either `schema_fields[]` non-empty OR `evidence_inserted[]` non-empty.
7. Validator passes the manifest (`quality_gate.passed == true`).
8. Negative test: a manifest with the legacy `{"status": "implemented"}` shape fails validation with a blocking issue listing the format defect.

---

## Definition of done (whole iteration 5 spec)

- All 3 bug acceptance tests pass.
- Re-run the Granola 2-article smoke (granola-chat + series-c). Expected outcomes:
  - `trust_block.passed == true` on both articles.
  - `trust_block.author_name == author_validation.display_name` on both articles (zero divergence).
  - `module_checks.question_headings.status == "passed"` on granola-chat.
  - `rec_implementation_map` entries on both articles have `implemented` key (not `status`).
  - **`quality_gate.passed == true` on both articles.**
  - `audit_after >= 32` on both articles.
  - All 7 stages green; ZERO banner warnings; ZERO runtime errors; ZERO schema validation failures.
- `plugin.json` bumped to `0.6.2`.
- `CHANGELOG.md` documents the 3 bug fixes.
- Marketplace cache + `marketplace.json` synced to 0.6.2.
- After v0.6.2 ships, run a SECOND smoke on 2 NEW Granola articles (rotate in different blog posts) to stress-test the contract on uncovered ground per Marco's directive.

## Non-goals (explicit)

- Do NOT refactor the validator to a single resolved-author pipeline (parked for v0.7.0 architecture work).
- Do NOT change the rubric_lint item set or thresholds.
- Do NOT change record_recommendations validation rules (those are working at the seam).
- Do NOT touch agents/recommender.md, agents/peec-gap-reader.md, dashboard/server.py, or dashboard/rubric_lint.py.
