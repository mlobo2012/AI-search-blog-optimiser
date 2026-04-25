# Peec-MCP Recommendation Engine — Improvement Spec (target: v0.6.0)

This spec hardens the Peec-driven half of the recommender. It does **not** remove or weaken the GEO-rubric checks that catch deterministic hygiene gaps (meta tags, schema, CTAs, internal links, author bios). It demotes those rubric checks to a fast deterministic pre-pass so the LLM's tokens go to synthesis, not to "your meta description is empty".

Origin: dry-run on 2026-04-25 against `granola.ai/blog`, 3 articles. Across 21 generated recommendations, 13 came from the GEO rubric (deterministic, mostly checklist), 6 came from Peec data, 2 were hybrid. The Peec half is the differentiator and is the under-developed half.

This spec is split into two parallel work lanes:

- **Lane C**: Coverage & multi-signal use (improvements 1 + 2)
- **Lane D**: Synthesis layer + sentiment recs + rubric demotion (improvements 3 + 4 + 5)

---

## Architectural goal

Move the recommender from "translate one Peec prompt → one mechanical rec" to "ingest the full Peec signal stack, aggregate to claim-level synthesis, output recs that only an LLM with this evidence could produce."

Rule of thumb for the new contract:

- Anything a deterministic linter could find should be found by the linter (Stage 4a) and surfaced as a checklist, not as an LLM-generated rec.
- Anything that requires synthesis across multiple Peec signals should be the LLM recommender's job (Stage 4b).
- Both lists are merged into the final recommendations JSON, with a `source` field so callers can tell which is which.

---

## Improvement 1 — Coverage fallback for articles with zero Peec prompt matches

### Problem

In the 2026-04-25 run, the engineering post (`so-you-think-its-easy-to-change-an-app-icon`) matched **zero** of the 49 tracked Peec prompts. The recommender silently fell back to a 100% GEO-rubric output with no Peec edge whatsoever — but the result was indistinguishable from a peec-enriched run because `mode: peec-enriched` was still set.

### Root cause

The recommender's mode is set by the orchestrator based on `gaps/{slug}.json` existence, not on whether the gap file actually contains useful prompt matches. A gap file with `matched_prompts: []` still gets treated as peec-enriched.

### Fix

Two changes in `agents/peec-gap-reader.md` and `agents/recommender.md`:

1. **Gap-reader expands its signal set when prompt matches are zero.** When `matched_prompts.length == 0`:
   - Pull `peec_actions(scope=overview)` and identify the article's category (owned, editorial, reference, ugc) and surface (article, listicle, comparison, etc).
   - Pull source-domain analytics for the article's site_key — which domains cite competitors but not us.
   - Pull engine-level brand sentiment by topic if topics are tagged.
   - Write these as `gaps/{slug}.json` under a new key `topic_level_signals` with sub-keys `category_gap`, `surface_gap`, `dominant_competitor_domains`, `engine_sentiment`.
2. **Recommender mode resolution becomes**:
   - `peec-prompt-matched` if `matched_prompts.length >= 1`
   - `peec-topic-level` if `matched_prompts.length == 0` AND `topic_level_signals` is non-empty
   - `voice-rubric` if neither (true fallback)

The recommender prompt branches on `mode`. For `peec-topic-level`, the recommender targets gap categories (e.g. "engineering article in OWNED bucket with 89% gap, dominated by towardsai.net and assemblyai.com") instead of specific prompts.

### Acceptance test

Add `tests/improvement_01_coverage_fallback_test.md`:

1. Run pipeline with one article that does NOT match any tracked prompt.
2. `gaps/{slug}.json` contains `topic_level_signals` with non-empty `category_gap` and `dominant_competitor_domains`.
3. Recommendation file's top-level `mode` field equals `peec-topic-level`.
4. At least 2 of the 7 recommendations cite `topic_level_signals` evidence (not just rubric).

---

## Improvement 2 — Use the full Peec signal stack in recommendations, not just prompt visibility

### Problem

Peec returns rich data: prompt visibility, share of voice, average position, citation_rate, retrieval_rate, gap chats, sentiment by engine, source-domain rankings, Action opportunities. The 2026-04-25 recommender keyed off prompt visibility almost exclusively. Citation rates, retrieval rates, sentiment-by-engine, and gap-chat excerpts were collected but not converted into recs.

### Fix

Rewrite the recommender contract in `agents/recommender.md` and the rec JSON shape:

- Each recommendation MUST cite at least one signal from a defined list:
  - `prompt_visibility` (existing)
  - `citation_rate`
  - `retrieval_rate`
  - `gap_chat_excerpt` (with the verbatim excerpt as evidence)
  - `engine_sentiment`
  - `source_domain_competitor_concentration`
  - `peec_actions_opportunity`
- The recommender is graded against signal diversity: of N recommendations in `peec-prompt-matched` or `peec-topic-level` mode, ≥3 distinct signal types should appear across the rec set.
- The rec JSON adds a per-rec field: `signal_types: ["prompt_visibility", "citation_rate"]` so downstream tooling can audit signal diversity.

### Acceptance test

Add `tests/improvement_02_signal_diversity_test.md`:

1. Run pipeline against an article with rich Peec coverage (matched_prompts ≥ 5).
2. Resulting `recommendations/{slug}.json`:
   - At least 3 distinct values across all `signal_types` arrays.
   - At least one rec cites a `gap_chat_excerpt` with the verbatim excerpt embedded in its evidence.
   - At least one rec cites either `citation_rate` or `retrieval_rate`.

---

## Improvement 3 — Sentiment-driven recommendations

### Problem

In the 2026-04-25 run, the gap-reader for two of three articles flagged "ChatGPT sentiment is the real problem: 58, dead last." The recommender produced **zero** recs targeting sentiment language. This is the loudest, most actionable Peec finding and it is invisible in the output.

### Fix

Extend the recommender contract:

- Treat sentiment-by-engine as a first-class input. If any tracked engine sentiment is below 65 (the documented healthy floor), the recommender MUST emit at least one rec targeting that engine's sentiment.
- The sentiment rec shape:
  - `category: "engine_sentiment"`
  - `target_engine: "chatgpt"`
  - `current_sentiment: 58`
  - `gap_to_floor: 7`
  - `fix`: a concrete language change in the article — typically rephrasing claims using terms the engine already associates with the brand more warmly (sourced from the gap_chat_excerpt evidence), or adding privacy/no-bot/accuracy framing if those terms cluster in the engine's positive-sentiment context.
  - `evidence`: the engine sentiment number plus 1–2 verbatim gap chat excerpts showing the engine's current language about the brand.
- The recommender draws the "warmer language" from the actual gap chat excerpts. It does not invent new positioning; it surfaces what the engine is already saying about competitors and reframes that on a first-party URL.

### Acceptance test

Add `tests/improvement_03_sentiment_recs_test.md`:

1. Run pipeline with a fixture where one engine sentiment is < 65.
2. Recommendations contain at least one item with `category == "engine_sentiment"`.
3. That rec's `evidence` array includes at least one verbatim excerpt from the gap chats.
4. The rec `fix` text contains a concrete proposed sentence or phrase — not generic advice.

---

## Improvement 4 — Claim-level synthesis instead of one-rec-per-prompt

### Problem

The 2026-04-25 recommender treated each Peec prompt as an isolated lever. Five 15–20% prompts that share an underlying missing claim (e.g. "Granola is a notepad/notetaker hybrid for teams with no bot") generate five separate atomic recs instead of one synthesised "missing claim" rec.

### Fix

Insert a synthesis pass between gap-read and recommendation:

- New stage in `agents/recommender.md`: before generating recs, group prompts by extracted claim. A "claim" is a positioning sentence the article would need to make to address the prompt cluster.
- For a prompt cluster like:
  - "best AI note taker for teams" — 20%
  - "best AI note taker for remote teams" — 20%
  - "best AI meeting assistant for distributed teams" — 18%
  - "what's the best AI note taker for collaboration" — 22%
  - The claim is: *"Granola is the AI note taker built for distributed and async teams."*
  - The single synthesised rec: "Add this claim, supported by [evidence], in this section, with [internal link] / [terms]." — replacing four atomic recs.
- The recommender output retains `claim_grouped: true` flag and an `addresses_prompts: [list]` array so the manifest still credits the underlying prompts.

### Acceptance test

Add `tests/improvement_04_claim_synthesis_test.md`:

1. Run pipeline with a fixture where ≥4 prompts share a clear underlying claim (e.g. team-related cluster).
2. Resulting recommendations contain at least one rec with `claim_grouped: true` and `addresses_prompts.length >= 3`.
3. The synthesised rec contains a one-sentence "missing claim" string in a field `claim` (not just a list of fixes).

---

## Improvement 5 — Demote GEO rubric checks to a deterministic linter pre-pass

### Problem

13 of 21 recs in the 2026-04-25 run were items a static linter could surface in milliseconds:

- empty meta description
- empty OG/Twitter tags
- no schema.org JSON-LD
- no inbound internal links
- missing primary CTA
- missing author bio / linkedin / updated_at
- < 2 internal links
- no FAQ blocks

These are real misses. They should still surface. But the recommender (running Sonnet) is wasting tokens producing them as natural-language recs when a deterministic linter could output them as a fixed-shape checklist.

### Fix

Add a new pipeline stage **4a — Rubric Lint** ahead of the LLM recommender:

- New module `dashboard/rubric_lint.py` (or equivalent) that consumes `articles/{slug}.json` and the GEO contract reference, and emits `rubric/{slug}.json` with a fixed list of pass/fail rubric checks.
- Each rubric check has `id`, `dimension`, `severity`, `auto_fix` (machine-applicable patch when possible), and `evidence` (the empty field, the missing schema type, etc).
- The recommender (Stage 4b) now receives `rubric/{slug}.json` as input and is explicitly told: *"These rubric items are already detected. Do NOT regenerate recommendations for them. Your job is synthesis on top of the rubric — claim-level recs, sentiment recs, and recs that depend on multiple Peec signals."*
- The final `recommendations/{slug}.json` aggregates both:
  - rubric-source items with `source: "rubric"` and `category: "geo_hygiene"`
  - LLM-source items with `source: "llm"` and `category: "synthesis" | "engine_sentiment" | "claim_grouped" | etc`
- The dashboard renders both sets in a single ordered list with a small badge indicating the source.

This preserves GEO hygiene (every rubric item still surfaces) while moving the LLM's tokens to where only an LLM can help.

### Acceptance test

Add `tests/improvement_05_rubric_lint_test.md`:

1. Run pipeline against an article known to have empty meta + no schema.
2. `rubric/{slug}.json` exists and contains rubric items for both gaps with `source: "rubric"`.
3. `recommendations/{slug}.json` contains those same rubric items merged into the final list, NOT regenerated by the LLM.
4. The LLM-source recs in the same file all have `source: "llm"` and at least one of `category in ["synthesis", "engine_sentiment", "claim_grouped", "topic_level"]`.
5. Total run time is measurably faster than baseline (rubric lint should be < 2 seconds; the recommender prompt is shorter because it's not re-finding rubric items).

---

## Lane assignment & branch hygiene

- **Lane C** (Codex Agent C): improvements 1 + 2. Branch `feat/v0.6.0-peec-coverage-and-multisignal` off the `fix/v0.5.4-bugs-integration` head (so it inherits all bug fixes). Worktree `~/conductor/workspaces/ai-search-blog-optimiser/lane-c`.
- **Lane D** (Codex Agent D): improvements 3 + 4 + 5. Branch `feat/v0.6.0-synthesis-and-rubric-demotion` off the same head. Worktree `~/conductor/workspaces/ai-search-blog-optimiser/lane-d`.

Files touched by Lane C and Lane D overlap on `agents/recommender.md` — Lane D owns the rec output schema and source-tagging changes; Lane C owns the input-side mode resolution. Coordinate via:

- Lane C goes first on `agents/recommender.md` (mode resolution change).
- Lane D pulls Lane C's `agents/recommender.md` change before applying its own changes.
- Final merge into `feat/v0.6.0-integration` performed by the orchestrator after both lanes land.

## Definition of done (whole improvements spec)

- All 5 acceptance tests pass.
- Re-run the Granola 3-article pipeline. Expected outcomes:
  - Engineering article (`so-you-think-its-easy-to-change-an-app-icon`) now has `mode: peec-topic-level` instead of empty Peec coverage. Recs cite topic-level signals.
  - At least one rec across the 3 articles addresses ChatGPT sentiment by name, with a verbatim gap-chat excerpt as evidence.
  - At least one rec across the 3 articles is `claim_grouped: true` with `addresses_prompts.length >= 3`.
  - Each `recommendations/{slug}.json` has both `source: "rubric"` and `source: "llm"` items, and `rubric/{slug}.json` exists.
  - Rec set signal-type diversity is ≥3 distinct values per article (where Peec coverage allows).
- `plugin.json` version bumped to `0.6.0`.
- `CHANGELOG.md` documents the four improvements with a note that GEO rubric hygiene is preserved via the new linter stage, not removed.
