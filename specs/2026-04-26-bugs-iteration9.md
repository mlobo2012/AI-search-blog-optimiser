# v0.6.5 Iteration 9 Bug Fixes (target: v0.6.6 — final ship)

Origin: v0.6.5 verification smoke `2026-04-26T11-26-06`. Both articles
shipped with `quality_gate.passed = true` and 40/40 score, but the verdict
file flagged C1=N (granola-chat) and C2=N (both) because the manifest
contract drift on `rec_implementation_map.non-applicable` shape and the
`trust_block.source` labeling for generator-promoted-as-author cases. Plus
4 recurring recommender retry warnings that don't block but should be
silenced for clean ops.

This is iteration 9 — the last iteration. Per Marco's brief: finish this
plugin once and for all and ship v0.6.6 to main.

Test target: continues to be the canonical pair (`granola-chat-just-got-smarter`
+ `series-c`) on Sonnet via `claude --print --model sonnet --max-articles 2`.
Same regression baseline as iter8.

---

## Lane assignment (uses parallel-agent-orchestration skill)

Per the `parallel-agent-orchestration` skill's Rule 1 (one worktree per
lane) and Rule 2 (one file per lane):

- **Lane M** (Codex Agent M): Bugs 22 + 23 — both touch
  `dashboard/quality_gate.py`. Single lane, single file. Worktree at
  `/Users/marco/conductor/workspaces/ai-search-blog-optimiser/lane-m-iter9/`.
  Branch `fix/v0.6.6-lane-m` off `feat/v0.6.0-integration` HEAD.
- **Lane N** (Codex Agent N): Bugs 24 + 25 — both touch
  `agents/recommender.md`. Single lane, single file. Worktree at
  `/Users/marco/conductor/workspaces/ai-search-blog-optimiser/lane-n-iter9/`.
  Branch `fix/v0.6.6-lane-n` off `feat/v0.6.0-integration` HEAD.

Lanes are file-disjoint (`quality_gate.py` ≠ `recommender.md`). Lanes will
push to origin separately. Orchestrator (Richard) will merge both into
integration after both report done.

---

## Bug 22 — `rec_implementation_map` validator rejects non-applicable sentinel

**Owner: Lane M.**

### Symptom

In v0.6.5 verification smoke, the verdict file reports `rec_map_shape=N`
for both articles even though `quality_gate.passed = true` (40/40 for both).
Reading the manifests: every recommendation that the generator marked
non-applicable encodes as:

```json
"rec-008": { "implemented": false, "reason": "non-applicable" }
```

This is the documented sentinel for "the recommendation does not apply to
this article" (e.g., a `claim_synthesis` rec for an article whose Peec
matched-prompt count is below the threshold). It deliberately omits the
implemented-shape keys (`section`, `anchor`, `schema_fields`,
`evidence_inserted`, `notes`) because those keys describe WHERE the rec
was implemented in the optimised draft — and the rec was NOT implemented.

The verifier's C2 check (Bug 15 strict shape rule) treats every entry as
needing all six keys, which causes the manifest-contract drift even though
the underlying behavior is correct.

### Root cause

`dashboard/quality_gate.py` validates `rec_implementation_map` entries using
a single shape (Bug 15's pinned implemented shape). Entries with
`implemented: false` and a `reason` field are neither rejected nor accepted
explicitly — they pass the gate but trip the verifier's downstream check.

### Fix

In `dashboard/quality_gate.py`, the rec-implementation-map validator must
accept TWO shapes:

1. **Implemented shape** (existing, Bug 15):
   `{implemented: true, section, anchor, schema_fields, evidence_inserted, notes}`

2. **Non-applicable shape** (new, sentinel):
   `{implemented: false, reason: <one of an enum>}`
   
   Allowed values for `reason` (case-insensitive, hyphen or underscore):
   - `"non-applicable"` — rec does not apply to this article (e.g.,
     claim_synthesis with insufficient matched prompts)
   - `"deferred"` — rec applies but generator did not implement it (logged
     as warning)
   - `"out-of-scope"` — rec was generated but is structurally outside the
     optimiser's editing surface (e.g., recommendation to change the site's
     navigation menu)
   
   Other `reason` values: validator rejects with a banner.

A `{implemented: false}` entry with NO `reason` field is also rejected —
the spec previously allowed silent omission, which made debugging hard.

### Acceptance test

Add `tests/bug_22_rec_map_non_applicable_shape_test.md` (4 cases):

1. Entry `{implemented: true, section, anchor, schema_fields,
   evidence_inserted, notes}` → passes (existing Bug 15 contract).
2. Entry `{implemented: false, reason: "non-applicable"}` → passes (new
   sentinel contract).
3. Entry `{implemented: false}` (no reason) → rejected with a clear banner.
4. Entry `{implemented: false, reason: "made-up-string"}` → rejected.

### Non-goals

- Do NOT change the implemented-shape contract from Bug 15.
- Do NOT modify the recommender's output behavior — the sentinel is already
  emitted correctly.

---

## Bug 23 — `trust_block.source` mislabeled when generator inlines reviewer as author

**Owner: Lane M.**

### Symptom

In v0.6.5 verification smoke, granola-chat's optimised draft contains both:

```
By **Jack Whitton**, Marketing, Granola · Published 21 April 2026
Reviewed by **Chris Pedregal**, CEO & Co-founder, Granola ([LinkedIn](...))
— Chris Pedregal is CEO and Co-founder of Granola...
```

The validator detected Chris Pedregal in the rendered trust block and
classified it as a normal `author_validation` pass:

```json
"author_validation": {
  "status": "passed",
  "display_name": "Chris Pedregal",
  "reviewer_id": null,
  "detail": "Chris Pedregal is a visible full-name reviewer with a rendered role line."
},
"trust_block": {
  "passed": true,
  "source": "author_validation",
  "author_name": "Chris Pedregal"
}
```

The verdict expected `source = "reviewers_promoted"` because Chris Pedregal
came from the reviewer block (not the source author byline). The trust
signal is correct in the rendered draft; the manifest just doesn't
distinguish the promotion path.

### Root cause

The validator's author-detection logic in `dashboard/quality_gate.py` reads
the rendered draft top-down and picks the first strong-role full-name byline
it finds. When the optimised draft has BOTH a source author byline (weak)
and a reviewer block (strong), the validator picks the reviewer name but
labels it as `author_validation` because it doesn't track WHICH visible
block the name came from.

### Fix

In `dashboard/quality_gate.py`, when the author-detection logic accepts a
name from a "Reviewed by" block (or any block that begins with
"Reviewed by", "Edited by", "Verified by", "Reviewer:" — case-insensitive),
set `trust_block.source = "reviewers_promoted"` and add an
`author_validation.detail` entry explaining the promotion (e.g.,
`"Chris Pedregal promoted as trust signal from rendered reviewer block (source author 'Jack Whitton, Marketing' rejected as weak role)."`).

When the accepted name comes from the standard "By NAME, Role" byline
(no reviewer prefix), keep `source = "author_validation"` (existing path).

This change preserves Bug 18's contract (`source ∈ {"author_validation",
"reviewers_json", "reviewers_promoted", "article_author_fallback"}`). The
new value `"reviewers_promoted"` is the visible-block promotion path; the
existing `"reviewers_json"` value remains for the data-table promotion path
(Bug 19's case where the validator promotes from `reviewers.json` config).

### Acceptance test

Add `tests/bug_23_trust_block_visible_reviewer_source_test.md` (4 cases):

1. Optimised draft has only "By Jane Doe, VP Engineering" → trust_block.source
   = `"author_validation"`, no reviewer detail.
2. Optimised draft has "By Jack Whitton, Marketing" + "Reviewed by Chris
   Pedregal, CEO" → trust_block.source = `"reviewers_promoted"`,
   author_name = `"Chris Pedregal"`, detail mentions the rejected source
   author.
3. Optimised draft has "By Chris Pedregal, CEO" + no reviewer block →
   source = `"author_validation"`.
4. Optimised draft has only "Edited by Chris Pedregal, CEO" (no source
   byline) → source = `"reviewers_promoted"`, detail mentions the absent
   source author.

### Non-goals

- Do NOT modify the generator (the rendered draft shape is correct as-is).
- Do NOT change the underlying `_validate_trust_block` reviewer-promotion
  helper that Bug 19 added (that handles the data-table promotion case).
  This bug is about the visible-block promotion case only.
- Do NOT remove the `"reviewers_json"` source value — Bug 19's path still
  uses it.

---

## Bug 24 — recommender LLM-source rec count exceeds 3-8 bound

**Owner: Lane N.**

### Symptom

In every smoke run (Round 4, Round 5, iter8 verification, iter8 final),
the recommender produces 9-10 recommendations on at least one article and
the validator emits a banner:

```
LLM-source recommendation count must be 3-8 for peec-prompt-matched; got 10
```

Validator forces a retry; recommender re-runs and usually converges. Non-
blocking but noisy — every smoke run has 4 of these warning banners. They
also slow the pipeline by 30-90s per retry.

### Root cause

`agents/recommender.md` does not state the upper bound (3-8) explicitly in
the recommender's instructions. The recommender LLM produces as many recs
as it considers necessary, sometimes exceeding 8.

### Fix

Edit `agents/recommender.md`. In the "Recommendation count" or equivalent
section, add an explicit hard cap:

> **Recommendation count discipline.** For `peec-prompt-matched` articles,
> generate exactly 3-8 LLM-source recommendations (inclusive). Do NOT
> generate 9 or more. If you have more than 8 candidate recs, MERGE the
> two lowest-priority candidates into a single composite rec, or DROP the
> lowest-priority candidate. The validator enforces this bound and will
> reject and retry if you exceed it — saving the retry cycle is worth a
> bit of merging.

Place this rule where the agent's count expectations live. Match existing
generator/recommender prompt style.

### Acceptance test

Add `tests/bug_24_recommender_count_cap_test.md`:

1. Article with strong rec coverage where recommender previously produced
   10 → after fix, recommender produces exactly 8 (or fewer). No retry
   banner.
2. Article with weak rec coverage where recommender previously produced 4
   → after fix, recommender still produces 4 (no artificial inflation).

### Non-goals

- Do NOT change the validator's 3-8 bound. The bound is correct; the
  recommender just needs to respect it.

---

## Bug 25 — recommender `addresses_prompts` count occasionally below 3

**Owner: Lane N.**

### Symptom

In smoke runs, occasionally a single rec entry has `addresses_prompts`
count of 2 (instead of the required minimum of 3) and the validator emits:

```
rec-005 addresses_prompts must contain at least 3 prompt ids
```

Validator forces a retry. Same noise pattern as Bug 24.

### Root cause

`agents/recommender.md` does not state the `addresses_prompts >= 3`
constraint explicitly. The recommender LLM sometimes produces a rec
addressing only 2 prompts (e.g., when the rec is engine-specific to one
prompt and the recommender picks the immediately related prompt).

### Fix

In `agents/recommender.md`, in the same recommendation-count section as
Bug 24's fix, add:

> **`addresses_prompts` minimum.** Every recommendation MUST address at
> least 3 prompt ids in its `addresses_prompts` array. If a rec is
> targeting a single specific prompt, find 2 related prompts that the same
> rec also helps (e.g., adjacent prompts in the same topic cluster, or
> prompts in the same engine where the rec applies broadly). If you cannot
> find 3 related prompts for a candidate rec, drop the rec — it is too
> narrow to be cost-effective.

### Acceptance test

Add `tests/bug_25_addresses_prompts_minimum_test.md`:

1. Article where recommender previously produced a rec with 2 prompt ids →
   after fix, that rec either has 3+ prompt ids OR is dropped.
2. Article where every rec already had 3+ prompt ids → no change.

### Non-goals

- Do NOT change the validator's `>= 3` minimum.

---

## Definition of done

- All 4 acceptance tests added under `tests/`.
- `dashboard/quality_gate.py` modified for Bugs 22 + 23 (Lane M).
- `agents/recommender.md` modified for Bugs 24 + 25 (Lane N).
- `feat/v0.6.0-integration` head is a release commit "release: v0.6.6
  (iteration 9 final integration)".
- `plugin.json` and `marketplace.json` bumped to 0.6.6.
- `CHANGELOG.md` documents Bugs 22-25.
- Marketplace cache rsync'd to 0.6.6 with explicit `__pycache__` exclusion.
- Smoke on Sonnet against the canonical pair (`--model sonnet --max-articles 2`)
  verifies:
  - **C1** trust_block.passed=true on BOTH articles, granola-chat
    additionally has `source = "reviewers_promoted"` (Bug 23 acceptance).
  - **C2** every `rec_implementation_map` entry validates against the
    two-shape contract (Bug 22 acceptance). No verdict flag for
    `rec_map_shape=N`.
  - **C3** internal_source_count, score_breakdown, module_checks all clean
    (Bugs 20 + 21 regression check).
  - **C4** quality_gate.passed=true on BOTH.
  - **C5** ZERO recommender-validation retry banners (Bugs 24 + 25
    acceptance — clean ops).
- If smoke is GREEN: ship to main as v0.6.6, tag, brief Marco. Plugin
  declared DONE.
- If smoke is YELLOW: read residual issues, decide if iter10 is warranted
  or accept and ship anyway.

## Loop policy (per Marco's iter8 brief, unchanged)

- Test runner: `claude --print --model sonnet`.
- Article cap: `--max-articles 2`. Same canonical pair.
- Codex lane size: 1 file per lane, 2 lanes max in parallel.
- This iteration uses the new `parallel-agent-orchestration` skill —
  separate worktrees per Rule 1, file-disjoint per Rule 2.
- Marco notification: at integration boundary AND at smoke verdict. Quiet
  during execution.
- Ship gate: GREEN smoke OR explicit Marco "ship anyway" call.
