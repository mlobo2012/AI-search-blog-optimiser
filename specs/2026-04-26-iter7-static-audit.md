# Iteration 7 readiness — static audit (v0.6.3)

Date: 2026-04-26
Author: Codex GPT-5.5 (reasoning=high)
Audited from: feat/v0.6.0-integration HEAD = fe864c6

## Bug fix verification matrix

| Bug | Spec | File | Line | Fix present? | Fix matches intent? | Adjacent regression risk? | Edge cases handled? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | `specs/2026-04-25-bugs-iteration4.md:41-56` require paired `claim_synthesis` recs + top-level `synthesis_claims[]` at threshold 3. | `server.py` / `recommender.md` | `server.py:2453`, `2547-2587`, `2669-2670`; `recommender.md:153-165` | Yes. Threshold is `3`; recommender instructs the paired write; server rejects unpaired recs or orphan claims. | Yes. A claim rec with no claims errors at `2550-2552`; every rec prompt set must be covered by claim prompt union at `2574-2585`. | Low. Validation happens before write at `server.py:2703-2705`; failure raises banner + `ValueError` at `2675-2685`. | Mostly. Missing/non-list claims coerce to `[]`; zero `claim_synthesis` recs + zero claims returns cleanly at `2553-2556`. Null items inside `addresses_prompts` are stringified by `_prompt_id_set` at `2543-2544`, but threshold/pairing still rejects most malformed prompt lists. |
| 12 | `specs/2026-04-25-bugs-iteration4.md:103-107` require deterministic integer `[0,40]`, zero sub-scores for missing inputs, and specific errors for critical missing inputs. | `quality_gate.py` | `120-135`, `809-859`, `862-878`, `1065-1071` | Yes. Numeric score is always clamped integer from deterministic sub-scores. | Yes. Each sub-score defaults to 0 on false/missing signals (`829-851`); aggregate clamps to `[0,40]` at `856`. Critical state/article/recommendation/html/schema inputs use required readers and raise at `862-878`. | Low. `audit_after` prefers explicit caller/existing/stage values before computed score at `1066-1071`, but all values are coerced/clamped and computed score is last-resort non-null. | Yes for absent rubric/audit scores: if no prior score exists, `score_breakdown["score"]` is used. Missing critical artifacts raise before scoring. |
| 13 | `specs/2026-04-25-bugs-iteration4.md:150-154` require null `reviewer_id` + passed author validation to populate `trust_block.author_name` from `author_validation.display_name`. | `quality_gate.py` | `792-806`, `900-902`, `1091-1092` | Yes. `build_article_manifest` computes `author_validation`, then passes it into `_validate_trust_block`. | Yes for the named null-reviewer case: passed + display name returns `passed: True` and `author_name: display_name`. | Medium. The explicit `reviewer_id` path still sets `source: "reviewers_json"` at `799`, which conflicts with the newer Round 4 source criterion, though not with Bug 13's original author-name fix. | Yes for null/missing author validation fields: status/display_name are checked before passing; failure returns empty `author_name`. |
| 14 | `specs/2026-04-25-bugs-iteration5.md:44-48` require `author_validation.display_name` as source of truth whenever author validation passed. | `quality_gate.py` | `792-801` | Yes. `_validate_trust_block` ignores source `trust.author.name` and uses `author_validation.display_name`. | Mostly. Name/pass consistency matches intent, but `source` is still conditional on `reviewer_id` at `799`; Round 4 R2 now wants `"author_validation"` for all passed paths. | Medium. This exact adjacent branch is the latent R2 issue and can cause a smoke YELLOW if a canonical article has non-null `reviewer_id`. | Yes for weak/missing names: failed author validation returns `passed: False`, `source: "author_validation"`, `author_name: ""`. |
| 15 | `specs/2026-04-25-bugs-iteration5.md:152-157` require exact `rec_implementation_map` shape and explicit ban on `status` / `note`. | `generator.md` / `quality_gate.py` | `generator.md:93-125`; `quality_gate.py:600-644` | Yes. Generator prompt pins the exact JSON shape and validator enforces it for critical LLM recs. | Yes. Implemented entries require boolean `implemented`, `section`, `anchor`, and schema/evidence arrays; false entries require allowed reasons. | Low. Controller copies existing manifest map at `quality_gate.py:1088`; validator rejects legacy shape because `implemented` is neither `True` nor `False` at `626-643`. | Yes for missing map, missing rec IDs, legacy strings, and invalid false reasons. |
| 16 | `specs/2026-04-25-bugs-iteration5.md:89-92` require H2 pass at >=50% questions or >=2 of >=3, with word-prefix detection. | `quality_gate.py` | `74-77`, `151-155`, `943-949`, `972` | Yes. Regex covers the specified question words and suffix `?`; module pass uses the 50% / 2-of-3 rule. | Yes. It no longer requires every H2 to be a question. | Low. Empty H2 list still fails by design (`bool(h2_headings)`). | Yes for empty strings and case-insensitive prefixes; no H2s fail rather than passing spuriously. |
| 17 | `specs/2026-04-25-bugs-iteration6.md:66-81` require `_apply_trust_author_fallback` to early-return when `author_validation.status == "passed"` and `display_name` is non-empty. | `server.py` | `2940-2947`, `2979-3011`, `3299-3302` | Yes. Guard is exactly present before any article/read/rewrite logic. | Yes for the current Round 4 risk register: it respects the Lane G trust block when author validation already passed. Older iter6 fixture B expected `article_author_fallback` source, but Round 4 R1 explicitly says skipping that re-entry is a feature. | Low for canonical pair. The fallback still mutates only when author validation has not already passed; persistence after it does not mutate `trust_block`. | Yes for non-dict article/author/reviewers, missing names, reviewer match, failed author validation, and empty-reviewer full-name fallback when author validation has not already passed. |

## Risk register findings

### R1 — Trust author fallback re-entry guard

Verdict: PASS.

The Round 4 risk register asks whether the guard short-circuits before the `article_author_fallback` branch, including the case where validation already passed via article-author fallback, and says that skip is a feature (`specs/2026-04-26-round4-relaunch-and-iter7-readiness.md:122-126`). The code does exactly that: `_apply_trust_author_fallback` reads `manifest["author_validation"]` and returns immediately when `status == "passed"` and `display_name` is non-empty (`server.py:2943-2947`). The later fallback writer that sets `author_validation.source = "article_author_fallback"` and `trust_block.source = "article_author_fallback"` is unreachable in that passed case (`server.py:2995-3011`). No loop or re-entry path is present in `_tool_validate_article`; the sequence is build manifest, internal-link fix, trust fallback, persist (`server.py:3299-3302`).

Note: this supersedes the older iter6 acceptance fixture B that expected `trust_block.source == "article_author_fallback"` for empty reviewers + full-name source author (`specs/2026-04-25-bugs-iteration6.md:87-90`). Under the latest R1 wording, the skip is intentional.

### R2 — _validate_trust_block source consistency

Verdict: FAIL / latent smoke risk.

Round 4 requires `trust_block.source == "author_validation"` and explicitly says any path writing `"reviewers_json"` while `status == "passed"` is a smoke YELLOW (`specs/2026-04-26-round4-relaunch-and-iter7-readiness.md:40-43`, `127-131`). `_validate_trust_block` still returns `"reviewers_json" if reviewer_id else "author_validation"` when `author_passed and display_name` (`quality_gate.py:793-800`). Therefore a passed author with a non-null `reviewer_id` produces `trust_block.passed == true` and `trust_block.source == "reviewers_json"`. That violates the latest contract even though the canonical v0.6.2 Bug 17 run described both articles with `reviewer_id: null` (`specs/2026-04-25-bugs-iteration6.md:23-27`).

### R3 — Third trust_block writer in _persist_manifest_and_update_draft_state

Verdict: PASS.

The risk asks whether `_persist_manifest_and_update_draft_state` mutates `trust_block` after fallback (`specs/2026-04-26-round4-relaunch-and-iter7-readiness.md:132-134`). It does not. It writes the manifest as received at `server.py:2751-2752`, then mutates only `state.json` draft fields: status, audit scores, quality gate, blocker summary, aggregates, and timestamp (`server.py:2753-2769`). `rg` found no `trust_block` references inside this function; the only server-side trust-block writes are in `_apply_trust_author_fallback` (`server.py:2974-3011`) and the quality-gate builder (`quality_gate.py:900-902`, `1091-1092`).

### R4 — Empty claim_synthesis recs handling

Verdict: PASS.

The risk asks whether zero `claim_synthesis` recs avoid a spurious error (`specs/2026-04-26-round4-relaunch-and-iter7-readiness.md:135-137`). Exact branch trace:

1. `_validate_recommendation_payload` coerces top-level `synthesis_claims` to a list (`server.py:2669`).
2. `_claim_synthesis_pair_issues` builds `claim_recs` from LLM items where `category == "claim_synthesis"` (`server.py:2547-2549`).
3. If `claim_recs` is empty and `claims` is also empty, it falls through `if claims:` and returns `issues` unchanged (`server.py:2553-2556`).
4. If `claim_recs` is empty but top-level claims are present, it correctly reports orphan `synthesis_claims` (`server.py:2553-2556`).

So the empty-recs/empty-claims case is clean. The paired failure case still rejects and retries via `_raise_recommendation_validation` (`server.py:2675-2685`, `2703-2705`).

### R5 — audit_after numeric path with missing rubric

Verdict: PASS.

The risk asks whether no rubric scores produce integer 0 instead of a `missing-critical-input` error (`specs/2026-04-26-round4-relaunch-and-iter7-readiness.md:138-141`). The validator does not depend on rubric scores for the numeric aggregate. It computes sub-scores from module status, author validation, evidence, schema, scope, and rec implementation issues (`quality_gate.py:809-853`), then returns a clamped integer total (`quality_gate.py:854-859`). If an article has no passing signals at all, each sub-score is 0 and the aggregate is integer `0`. `audit_after` is resolved from caller value, existing manifest, stage draft, then computed score (`quality_gate.py:1066-1071`), so absent rubric/audit values do not raise.

Critical missing inputs still raise before scoring: missing state/article/recommendation use required JSON readers (`quality_gate.py:862-869`), and missing/empty rendered HTML plus missing schema package use required readers (`quality_gate.py:874-878`). That matches iter4's requirement to raise on critical missing artifacts, not silently null-coalesce (`specs/2026-04-25-bugs-iteration4.md:103-107`).

## Smoke verdict prediction

- Per article (granola-chat-just-got-smarter): GREEN, assuming the v0.6.3 marketplace cache produces the same null-`reviewer_id` canonical path documented in iter6. The trust guard preserves the passed manifest (`server.py:2943-2947`), `_validate_trust_block` returns `source: "author_validation"` when `reviewer_id` is null (`quality_gate.py:793-800`), audit_after is computed as an integer (`quality_gate.py:1066-1071`), and question headings use the >=50% / 2-of-3 detector (`quality_gate.py:943-949`).
- Per article (series-c): GREEN on the same assumption. The latest documented v0.6.2 failure had both articles with `author_validation.status == "passed"`, display name `Chris Pedregal`, and `reviewer_id: null` (`specs/2026-04-25-bugs-iteration6.md:23-27`), which exercises the safe source branch.
- Run-level: GREEN predicted for the canonical pair, but with a latent R2 branch that must be fixed before treating the contract as generally closed.
- Confidence: medium. Static code strongly supports GREEN for the documented canonical null-reviewer path, but if either smoke article now carries non-null `reviewer_id`, `trust_block.source` will be `"reviewers_json"` and criterion 1 will turn the smoke YELLOW.

## Latent bugs surfaced (candidates for Bug 18+)

1. `dashboard/quality_gate.py:793-800` — `_validate_trust_block` writes `trust_block.source = "reviewers_json"` when `author_validation.status == "passed"` and `reviewer_id` is non-null. Symptom: Round 4 criterion 1 fails despite a valid author and matching author name. Proposed fix sketch: for passed author validation, always return `source: "author_validation"`; if reviewer provenance is needed, add a separate non-gating field such as `author_source` or rely on `author_validation.reviewer_id`.
