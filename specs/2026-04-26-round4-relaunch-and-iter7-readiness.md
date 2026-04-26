# Round 4 smoke re-launch + iteration 7 readiness (target: GREEN on v0.6.3)

Date: 2026-04-26
Author: Richard (Discord session)
Branch context: `feat/v0.6.0-integration` HEAD = `fe864c6` "release: v0.6.3
(iteration 6 bug-fix integration)". Marketplace cache + `marketplace.json`
both at `0.6.3`.

---

## Where we are (state on 2026-04-26 09:30 UTC)

- **Bug 17 fix is shipped** in `dashboard/server.py::_apply_trust_author_fallback`
  (lines 2940-2947 in zurich + marketplace cache). The early-return guard is in
  place: `author_validation.status == "passed"` AND non-empty `display_name` →
  the function bails out before it can clobber Lane G's `_validate_trust_block`
  result.
- **v0.6.3 is integrated** on `feat/v0.6.0-integration` (`fe864c6`) and pushed
  to `origin/feat/v0.6.0-integration`. Marketplace cache at
  `~/.claude/plugins/marketplaces/local-desktop-app-uploads/ai-search-blog-optimiser/`
  was synced after the integration commit (`server.py` mtime 2026-04-25 23:14 PT).
- **`main` has NOT been fast-forwarded** to v0.6.3. It still trails. We do not
  ship to main until Round 4 smoke verifies GREEN.
- **Round 4 smoke never completed.** The two attempted runs from 2026-04-25
  (`22-16-38` and `22-17-53`) stalled at the `analysis` stage:
  - `state.json.pipeline.analysis = "running"` (22-17-53) or `"completed"` (22-16-38).
  - `state.json.pipeline.evidence` / `recommendations` / `draft` = `"pending"`.
  - `gates.json` = `{}`.
  - Subagent `peec-gap-reader` jsonl logs stop writing at 23:22 PT, ~5 min
    after the parent Richard Discord session ended. The bg `claude` jobs were
    killed when the parent process exited.
- We have **no GREEN verdict** on v0.6.3.

## What "GREEN" means for v0.6.3 (definition of done)

Run the canonical 2-article Granola smoke (`granola-chat-just-got-smarter` +
`series-c`) against the marketplace cache install of v0.6.3. Pass criteria
(all must hold for both articles):

1. **Bug 17 specifically**: `trust_block.passed == true` AND
   `trust_block.author_name == author_validation.display_name` AND
   `trust_block.source == "author_validation"` (NOT `"reviewers_json"` and NOT
   empty `author_name`).
2. **Iteration 4 + 5 regression**: `audit_after >= 32` (numeric, never null —
   Bug 12); `synthesis_claims[]` paired with each `claim_synthesis` rec (Bug
   11); `rec_implementation_map` in correct field shape (Bug 15); question
   headings module passes when ≥50% H2s are questions (Bug 16).
3. **v0.6.0 architecture regression**: `rubric_lint` runs and produces
   non-empty output; `framing_block` present; trigger-driven rec categories
   fire correctly; manifest cross-validation passes.
4. **Quality gate**: `quality_gate.passed == true` for both articles.
5. **Operational hygiene**: zero banner warnings of severity ≥ warning, zero
   runtime errors, zero schema validation failures.

If 1-5 all hold → **GREEN**. Otherwise → **YELLOW** and we spec iteration 7.

## Plan

### Lane R — Re-launch Round 4 smoke (Richard, this session)

Re-launch the canonical 2-article smoke against the marketplace cache install
of v0.6.3 as a background headless `claude` job. Working directory:
`/Users/marco/conductor/workspaces/ai-search-blog-optimiser/zurich` (so the
plugin's `.mcp.json` and `.claude-plugin/plugin.json` are picked up).

Single bg job, single canonical pair, fresh run (NOT --resume). On
completion:
- Read `state.json` and `gates.json` of the new run dir.
- Verify all 5 GREEN criteria.
- Emit Y/N verdict per criterion.

If GREEN → ship feat/v0.6.0-integration to main, then rotate in 2 fresh
Granola articles for the Round 5 stress-test smoke per Marco's loop policy.

If YELLOW → diagnose, then spec iteration 7.

### Lane S — Static iter7 audit (Codex GPT-5.5 reasoning high, parallel)

Codex GPT-5.5 with `reasoning_effort=high` runs in parallel with Lane R. It
does NOT run the smoke (Codex has no Claude plugin runtime). Its job is to:

1. Read the full iteration 4-6 spec stack (`specs/2026-04-25-bugs.md`,
   `bugs-iteration[2-6].md`).
2. Read the current `dashboard/server.py`, `dashboard/quality_gate.py`,
   `dashboard/rubric_lint.py`, and the agent specs in `agents/`.
3. Statically audit all six known fix points (Bugs 11, 12, 13, 14, 15, 16,
   17) — confirm every fix is present in the v0.6.3 code AND that no
   regression was introduced.
4. Predict whether the smoke will be GREEN. Flag any latent risk that would
   surface as Bug 18+ in iter7.
5. If risks are found, draft a skeleton iteration 7 spec at
   `specs/2026-04-26-bugs-iteration7-predicted.md` with: bug name, file +
   line, root cause, proposed fix, acceptance test outline, and lane
   assignment.

Outputs: a written audit doc + (conditional) iter7 spec skeleton.

### Lane T — Decision and ship (Richard, when Lane R + Lane S both report)

Cross-reference Lane R's empirical verdict with Lane S's static prediction.

- **Both GREEN** → fast-forward `main` to `feat/v0.6.0-integration`. Tag
  `v0.6.3`. Rotate in 2 fresh Granola articles + launch Round 5 smoke.
- **Lane R GREEN, Lane S flags risk** → land main but immediately spec iter7
  preventatively (don't wait for Round 5 to surface it).
- **Lane R YELLOW** → use Lane S's audit as the seed for iter7 spec. Spawn
  Codex lanes per spec (1-2 lanes max, non-overlapping files, gpt-5.5 high).
  Re-run Round 4 smoke after iter7 ships as v0.6.4.

## Non-goals

- Do NOT touch `main` until Lane R reports GREEN.
- Do NOT modify `_apply_trust_author_fallback` further unless Lane R / Lane S
  surfaces a concrete bug.
- Do NOT regenerate the brand-voice baseline. Reuse the cached
  `granola.ai/brand-voice.md`.
- Do NOT chase the v0.7.0 parking-lot items (evidence-builder 404 fallback,
  reviewer-promotion banner, audit_before normalisation).

## Risk register (for Lane S to verify)

- **R1**: Does the early-return guard actually short-circuit before the
  `article_author_fallback` branch? In particular, does it skip the case
  where the validator passed via `article_author_fallback` (which sets
  `author_validation.source == "article_author_fallback"`)? If yes, that's a
  feature; if it loops or re-enters, that's Bug 18.
- **R2**: Does `_validate_trust_block` (Lane G fix) write `trust_block.source`
  consistently as `"author_validation"` when status==passed, or are there
  paths where it writes `"reviewers_json"` while status==passed? GREEN
  criterion 1 demands `source == "author_validation"`, so any mismatch is a
  smoke YELLOW.
- **R3**: `_persist_manifest_and_update_draft_state` runs after the fallback.
  Does it apply any further trust_block mutations? If yes, that's a third
  writer and Bug 17's fix doesn't fully close the loop.
- **R4**: Does the `record_recommendations` synthesis-claims contract check
  (Bug 11) handle the empty-recs case (zero `claim_synthesis` recs) without
  raising spuriously?
- **R5**: Does `audit_after` (Bug 12) really return integer 0 when an article
  has no rubric scores at all, vs raising a "missing-critical-input" error?
  We don't want it silently zero-coalescing in the Round 4 case if rubric is
  absent.
