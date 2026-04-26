# v0.6.4 Iteration 8 Bug Fixes (target: v0.6.5)

Origin: v0.6.4 verification smoke `2026-04-26T10-13-57` after Marco's
diagnostic review surfaced 3 system-level bugs. The Bug 17/18 trust-author
work shipped clean in v0.6.4, but the canonical-pair smoke YELLOW'd because
the plugin's recommender produces correct recs that the validator and
generator do not honour. Symptoms previously mis-framed as "input quality
issues" — corrected: these are validator + generator bugs, not source-article
faults.

Test target: continues to be the canonical pair (`granola-chat-just-got-smarter`
+ `series-c`) so iter8 outcomes can be regression-compared run-over-run.
Smoke will be driven by `claude --print --model sonnet --max-articles 2` per
Marco's brief.

---

## Lane assignment

- **Lane K** (Codex Agent K): Bugs 19 + 20 — both touch `dashboard/quality_gate.py`. Single lane.
- **Lane L** (Codex Agent L): Bug 21 — `agents/generator.md`. Independent lane.

Single-file lanes. No two lanes touch the same file.

---

## Bug 19 — `trust_block` validator ignores reviewer block when present

**Owner: Lane K.**

### Symptom

In v0.6.4 smoke `2026-04-26T10-13-57`, granola-chat-just-got-smarter optimised draft
contains BOTH a source author byline AND a reviewer block:

```
By **Jack Whitton**, Marketing, Granola · Published 21 April 2026
Reviewed by **Chris Pedregal**, CEO & Co-founder, Granola ([LinkedIn](...)) — Chris Pedregal is CEO and Co-founder of Granola. He previously worked at Google and DeepMind.
```

The recommender correctly flagged "first-name-only byline blocks Perplexity author trust" and the generator correctly added the reviewer block with full role + LinkedIn + bio. Despite this, `quality_gate.passed = false` because `_apply_trust_author_fallback` in `dashboard/server.py` (and `_validate_trust_block` in `dashboard/quality_gate.py`) checks the *source author* byline ("Jack Whitton, Marketing") for trust strength and rejects "Marketing" as too weak — even though the reviewer ("Chris Pedregal, CEO & Co-founder") is the actual trust signal. `trust_block.passed=false`, `author_validation.status=failed`.

### Root cause

`_validate_trust_block` and `_apply_trust_author_fallback` only inspect `author_validation` derived from the source `article.trust.author` field. They do not consult the `reviewers_json` site config for a strong-role reviewer when the source author is weak. The current author-validation logic is asymmetric: it can promote a reviewer when there's NO source author (Bug 14 fix) but cannot promote a reviewer when the source author EXISTS but is weak.

### Fix

In `dashboard/quality_gate.py::_validate_trust_block`:

When `author_passed` is false (i.e., the source author byline doesn't satisfy author-validation rules), check whether `reviewers_json` contains a reviewer with a strong role (active=true AND role exists AND role is NOT in the weak-role rejection list). If yes:

- Return `{"passed": true, "source": "reviewers_json", "author_name": <reviewer.display_name>}` — the reviewer is the trust signal.
- Set `author_validation.display_name`, `display_role`, `reviewer_id` to that reviewer's values; flip `author_validation.status` to `"passed"` with a `detail` field that explains the reviewer-promotion path.

Important: the existing Bug 18 contract still applies — `trust_block.source` MUST be either `"author_validation"` or `"reviewers_json"` deterministically; never both, never null. The reviewer-promotion case explicitly sets `"reviewers_json"` because the trust signal genuinely came from the reviewer table, not the source author.

The Bug 17 `_apply_trust_author_fallback` guard (in server.py) already short-circuits when `author_validation.status == "passed"` AND `display_name` is non-empty, so the new reviewer-promotion path will be respected by the fallback function automatically.

### Acceptance test

Add `tests/bug_19_trust_block_reviewer_promotion_test.md` matching the style of `bug_14_trust_block_promoted_reviewer_test.md`:

1. Source author "Jack Whitton, Marketing" + reviewers_json contains "Chris Pedregal, CEO & Co-founder" with LinkedIn → `trust_block.passed=true`, `source=reviewers_json`, `author_name="Chris Pedregal"`. Validator flips author_validation.status to passed with reviewer-promotion detail.
2. Source author "Jane Doe, VP Engineering" (already strong role) + reviewers_json non-empty → existing Bug 14 path wins (do not promote a different reviewer).
3. Source author "Jack, Marketing" + reviewers_json EMPTY → `trust_block.passed=false`, `source=author_validation`, `author_name=""`. Genuine failure case.
4. Source author missing entirely + reviewers_json contains strong reviewer → existing Bug 14 path. Reviewer is promoted as before.

### Non-goals

- Do NOT change the weak-role definition itself (kept as a separate decision; iter8 is about applying it correctly when a strong reviewer exists).
- Do NOT modify `dashboard/server.py::_apply_trust_author_fallback` (Bug 17 guard already correct).

---

## Bug 20 — internal source check rejects valid same-domain subdomains

**Owner: Lane K.**

### Symptom

In v0.6.4 smoke `2026-04-26T10-13-57`, series-c manifest:

- `internal_source_count = 1` despite the optimised draft containing 7 internal links and 6 evidence sources.
- `quality_gate.blocking_issues = ["Evidence pack has 1 internal sources; requires 2."]`

The 6 evidence sources include `https://docs.granola.ai/help-center/sharing/integrations/{personal-api,enterprise-api,mcp}` — clearly granola-owned content — but the validator only counts URLs whose host EXACTLY matches the canonical blog apex (`www.granola.ai`). `docs.granola.ai` is silently excluded.

For a public company blog, all subdomains of the canonical blog's apex domain are "internal" content and should count toward the internal-source minimum.

### Root cause

In `dashboard/quality_gate.py`, the internal-source classifier compares a URL's host against `state["canonical_blog_url"]` host (`www.granola.ai`) using exact string equality. It does not strip subdomains to compare apex domains.

### Fix

Compute the apex domain from `state["canonical_blog_url"]` (e.g., `www.granola.ai` → apex `granola.ai`) and treat any URL whose host EQUALS the apex OR ENDS WITH `."<apex>"` as internal. Public-suffix awareness is not required for v0.6.5 — a simple right-to-left dot-split on the apex (last 2 labels) is acceptable for the .com/.ai/.io single-suffix cases that the plugin targets. If `state["canonical_blog_url"]` host has only 2 labels (e.g., `granola.ai`), the apex IS the host.

Use this rule everywhere internal/external classification is currently done in `quality_gate.py` (search for the existing classifier and point all callers at one helper).

### Acceptance test

Add `tests/bug_20_internal_source_subdomain_test.md`:

1. canonical_blog_url=`https://www.granola.ai/blog`, evidence sources = `[https://www.granola.ai/blog/foo, https://docs.granola.ai/help, https://app.granola.ai/x]` → all 3 count as internal. `internal_source_count = 3`.
2. canonical_blog_url=`https://granola.ai/blog`, evidence sources = `[https://granola.ai/blog/foo, https://www.granola.ai/x]` → both count as internal.
3. canonical_blog_url=`https://www.granola.ai/blog`, evidence sources = `[https://techtarget.com/x, https://atlassian.com/y]` → 0 internal.
4. canonical_blog_url=`https://www.granola.ai/blog`, evidence sources = `[https://granolafake.com/x]` (substring trick) → 0 internal. The check must NOT match `granolafake.com` against `granola.ai`.

### Non-goals

- Do NOT introduce a public-suffix list dependency. Single-label suffix split (`a.b.c → b.c`) is sufficient for the .com/.ai/.io cases.
- Do NOT change the minimum internal-source count threshold. The threshold (currently 2) is correct; the bug is the classifier missing valid same-apex sources.

---

## Bug 21 — generator does not enforce ≥50% question H2s when rec list demands

**Owner: Lane L.**

### Symptom

In v0.6.4 smoke `2026-04-26T10-13-57`, granola-chat optimised draft has 5 H2s of which only 1 is a question:

- "Which AI meeting assistant is best for searching across all past meetings?" ← question
- "Auditable by design" ← declarative
- "New Recipes" ← declarative
- "Putting your company's context to work" ← declarative
- "FAQ" ← literal label, doesn't count

`module_checks` includes `question_headings = failed` because <50% are questions. The recommender DID produce a rec ("Add FAQ block targeting ChatGPT and Perplexity dark-engine gap") but the generator only added the FAQ label without rewriting other H2s as questions per GEO best practice.

### Root cause

`agents/generator.md` does not explicitly require the generator to enforce question-H2 ratio when the rec list contains ANY rec with `category == "engine_specific"` or `category == "geo_hygiene"` and the rec mentions FAQ / question-format / question-target language. Generator currently treats FAQ recs as additive (add a section) rather than transformational (rewrite H2s).

### Fix

Edit `agents/generator.md`. In the H2 / structure section, add an explicit rule:

> **Question-H2 enforcement.** When the rec list contains any recommendation whose `category` is in `{"engine_specific", "geo_hygiene"}` AND whose `title` or `description` mentions FAQ, question H2, or question-format headings, the optimised draft MUST satisfy the question_headings GEO contract: at least 50% of body H2s (excluding the literal "FAQ" label) MUST be in question form (start with Which/How/What/Why/When/Where/Who/Can/Does/Is/Are/Should — case-insensitive — OR end with `?`). If the source draft has fewer than this threshold, you MUST rewrite existing H2s in question form rather than just adding a separate FAQ section. Preserve the article's information architecture — do not invent topics; rephrase the headings that already exist around the article's actual sections so that they ASK the question the section answers. Example: "Auditable by design" → "How is Granola Chat auditable by design?".

Add this rule to the existing "Headings" or "Structure" section of generator.md. Do not duplicate language from the question_headings module; reference the GEO contract explicitly.

### Acceptance test

Add `tests/bug_21_question_h2_enforcement_test.md`:

1. Recs include a `geo_hygiene` rec mentioning "FAQ block" + source draft has 4 declarative H2s + 0 questions → optimised draft must have ≥2 question H2s (50%) or ≥2 of 3 if H2 count drops to 3.
2. Recs include an `engine_specific` rec mentioning "question H2 targeting" + source has 6 H2s → optimised must have ≥3 question H2s.
3. Recs DO NOT mention FAQ/question/question-format → no transformation enforced; existing H2s preserved.
4. Source already satisfies the threshold → generator MUST NOT remove/rewrite existing question H2s into declarative.

### Non-goals

- Do NOT change the question_headings detector logic in `quality_gate.py`. The detector is correct; only generator behavior needs the enforcement rule.
- Do NOT add a post-generator H2-rewrite step in code. The fix is at the generator-prompt level; LLM follow-through is the loop.

---

## Definition of done

- All 3 acceptance tests added under `tests/`.
- `dashboard/quality_gate.py` modified for Bugs 19 + 20.
- `agents/generator.md` modified for Bug 21.
- `feat/v0.6.0-integration` head is a release commit "release: v0.6.5 (iteration 8 bug-fix integration)".
- `plugin.json` and `marketplace.json` bumped to 0.6.5.
- `CHANGELOG.md` documents Bugs 19, 20, 21.
- Marketplace cache rsync'd to 0.6.5 with explicit `__pycache__` exclusion.
- Smoke on Sonnet against the canonical pair (`--model sonnet --max-articles 2`) verifies:
  - **C1** trust_block contract still GREEN on series-c (Bug 18 regression check).
  - **C1+** trust_block.passed=true on granola-chat with `source=reviewers_json` and `author_name="Chris Pedregal"` (Bug 19 acceptance).
  - **C3+** internal_source_count ≥ 2 on series-c with at least 1 docs.granola.ai counted (Bug 20 acceptance).
  - **C3+** question_headings module status = passed on granola-chat with ≥3 of 5+ H2s in question form (Bug 21 acceptance).
  - **C4** quality_gate.passed=true on BOTH articles.
- If smoke surfaces NEW YELLOW signals, spec iter9 with whatever Codex sees in the residual issues, spawn the next lane(s), repeat. Loop until canonical pair is fully GREEN on Sonnet, then ship.

## Loop policy (per Marco's iter8 brief)

- Test runner: `claude --print --model sonnet` from zurich cwd.
- Article cap: `--max-articles 2`. Same canonical pair (granola-chat + series-c) across iterations to track regression risk.
- Codex lane size: 1 file per lane, 2 lanes max in parallel. Same Codex GPT-5.5 reasoning_effort=high invocation as iter6/iter7.
- Marco notification: ping at each integration boundary (lanes done) AND at each smoke verdict. Don't ping mid-flight.
- Ship gate: ALL of (C1, C1+, C3+, C4) must hold across canonical pair on Sonnet smoke before pushing to main.
