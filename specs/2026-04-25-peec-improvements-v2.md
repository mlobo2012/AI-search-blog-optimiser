# Peec-MCP Recommendation Engine — Improvement Spec v2 (target: v0.6.0)

This is v2 of `specs/2026-04-25-peec-improvements.md`. v1 captured the right shape (5 improvement areas + rubric demotion) but, after reviewing the actual v0.5.9 outputs against real Peec data, four hard problems were not addressed:

1. The recommender contract is too loose — the same agent produces a 4-item generic list for one article and a deeply Peec-grounded `geo_gap_actions` + `engine_gap_strategy` artefact for another in the same run. `record_recommendations` only validates `len(items) == 4`. Nothing else.
2. The most actionable Peec finding — engine-pattern asymmetry (e.g. Granola at 57–100% on Google AI Overview, 0–50% on ChatGPT and Perplexity) — has no first-class signal slot, no required engine-specific tactic, no enforcement.
3. There is no category / brand / competition lens in the recommender output. The recommender lists prompts and modules; it does not synthesise where the article sits in the category, what the brand-level engine pattern is, or what the competition-class strategy implies.
4. There is no manifest cross-validation. Even brilliant recs are wasted if the generator silently ignores them, and the validator cannot check whether a `priority: critical` rec actually landed in the rendered article.

This v2 spec hardens v1 with six structural changes (A–F), three sharpenings on the existing five improvements, and a clean lane split that removes the merge-conflict risk on `agents/recommender.md`.

It does **not** remove or weaken the GEO-rubric checks that catch deterministic hygiene gaps (meta tags, schema, CTAs, internal links, author bios). It demotes those rubric checks to a fast deterministic pre-pass so the LLM's tokens go to synthesis, not to "your meta description is empty".

Origin evidence: v0.5.9 smoke run `2026-04-25T17-49-21` (granola-chat-just-got-smarter + series-c) and earlier 3-article run `2026-04-25T10-45-39` (which included the engineering post `so-you-think-its-easy-to-change-an-app-icon`).

---

## Lane assignment (clean — zero file overlap)

- **Lane C** owns the **input layer**:
  - `agents/peec-gap-reader.md`
  - `skills/peec-gap-read/SKILL.md`
  - new acceptance tests for Improvements 1, 2, and the gap-reader hardenings
  - **Does NOT touch `agents/recommender.md`, `dashboard/server.py`, `agents/generator.md`.**
- **Lane D** owns the **output layer**:
  - `agents/recommender.md` (full rewrite of output schema, framing, mode handling)
  - `dashboard/rubric_lint.py` (NEW — 13 enumerated deterministic checks)
  - `dashboard/server.py` (`record_recommendations` schema validation + new `rubric_lint` tool)
  - `agents/generator.md` (rec_implementation_map population + manifest contract)
  - `dashboard/quality_gate.py` (new manifest validator: `priority: critical` recs must have implementation entries)
  - new acceptance tests for Improvements 3, 4, 5, plus the new framing / engine-pattern / off-page / manifest tests
  - **Does NOT touch `agents/peec-gap-reader.md` or `skills/peec-gap-read/SKILL.md`.**

Branch off the head of `fix/v0.5.9-bugs-integration` (commit `5771114`). Worktrees `~/conductor/workspaces/ai-search-blog-optimiser/lane-c` and `~/conductor/workspaces/ai-search-blog-optimiser/lane-d`. After both lanes land, merge into `feat/v0.6.0-integration`.

Lane D depends on Lane C's gap-reader output schema. The schema is locked in this spec (see "Locked gap artefact schema" below), so Lane D can implement against it without waiting for Lane C to finish.

---

## Architectural goal

Move the recommender from "translate one Peec prompt → one mechanical rec" to "ingest the full Peec signal stack, synthesise into category / brand / competition lenses, output recs that only an LLM with this evidence could produce, and prove they landed in the rendered article."

Operating rules:

- Anything a deterministic linter could find is found by the linter (Stage 4a) and surfaced as a checklist, not as an LLM-generated rec.
- Anything that requires synthesis across multiple Peec signals is the LLM recommender's job (Stage 4b).
- Both lists merge into the final `recommendations/{slug}.json`, with a `source: "rubric" | "llm"` field so callers can tell which is which.
- Every `priority: critical` LLM-source rec MUST have an implementation entry in the optimised manifest. The validator FAILS the article if any critical rec is missing or unimplemented without a valid reason.

---

## Locked gap artefact schema (Lane C output, Lane D input)

`outputs/gaps/{article_slug}.json`:

```json
{
  "article_slug": "<slug>",
  "match_mode": "prompt-first | topic-level | none",
  "matched_topics": [
    {"topic_id": "...", "topic_name": "..."}
  ],
  "matched_prompts": [
    {
      "prompt_id": "...",
      "prompt_text": "...",
      "match_reasons": ["..."],
      "brand": {
        "visibility_per_engine": {"chatgpt-scraper": 0.0, "perplexity-scraper": 0.0, "google-ai-overview-scraper": 0.0},
        "sov_per_engine": {},
        "position_per_engine": {},
        "sentiment_per_engine": {},
        "citation_score_per_engine": {}
      },
      "engines_lost": ["chatgpt-scraper"],
      "cited_competitors": [
        {
          "domain": "fireflies.ai",
          "classification": "COMPETITOR | EDITORIAL | CORPORATE | UGC | REFERENCE",
          "citation_rate_per_engine": {"chatgpt-scraper": 0.4}
        }
      ],
      "top_gap_chats": [
        {"chat_id": "...", "engine": "chatgpt-scraper", "excerpt": "<verbatim ≤200 chars>", "cited_urls": []}
      ],
      "notes": "..."
    }
  ],
  "gap_domains": {
    "top_competitor_cited_domains": [
      {
        "domain": "techsifted.com",
        "classification": "EDITORIAL",
        "citation_rate": 2.75,
        "retrieval_count": 4,
        "citation_count": 11
      }
    ]
  },
  "topic_level_signals": {
    "category_gap": {"action_group_type": "OWNED", "url_classification": "LISTICLE", "gap_percentage": 100, "coverage_percentage": 0, "opportunity_score": 0.27},
    "surface_gap": {"action_group_type": "EDITORIAL", "url_classification": "LISTICLE", "gap_percentage": 62.7, "coverage_percentage": 37.3, "opportunity_score": 0.13},
    "dominant_competitor_domains": [{"domain": "...", "classification": "EDITORIAL"}],
    "engine_sentiment": {"chatgpt-scraper": 64, "perplexity-scraper": 71, "google-ai-overview-scraper": 79}
  },
  "peec_actions": {
    "overview_top_opportunities": [
      {"action_group_type": "OWNED", "url_classification": "LISTICLE", "opportunity_score": 0.27, "gap_percentage": 100, "coverage_percentage": 0, "note": "..."}
    ]
  },
  "data_freshness": "YYYY-MM-DD",
  "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "notes": "..."
}
```

**Hard requirements**:

- `matched_prompts[].cited_competitors[].classification` — REQUIRED on every cited competitor (was missing in granola-chat-just-got-smarter v0.5.9 output for prompt-level competitors; was present at `gap_domains` level only).
- `matched_prompts[].top_gap_chats` — REQUIRED non-empty (≥1 entry) for every prompt where `engines_lost.length >= 2`. Was empty for all 8 granola-chat prompts in v0.5.9; was populated for series-c. The gap-reader is currently inconsistent. This is fixed by a new clause in `skills/peec-gap-read/SKILL.md` and the `peec-gap-reader.md` agent procedure.
- `topic_level_signals` — REQUIRED when `matched_prompts.length == 0`. Optional otherwise (still useful as side data).
- `peec_actions.overview_top_opportunities` — REQUIRED, ≥3 entries when the project has any actions data.

---

## Locked recommendation artefact schema (Lane D output)

`outputs/recommendations/{article_slug}.json`:

```json
{
  "article_slug": "<slug>",
  "run_id": "<run_id>",
  "generated_at": "<iso8601>",
  "preset": "announcement_update | comparison | how_to | listicle | glossary | case_study | pillar | narrative_editorial",
  "mode": "peec-prompt-matched | peec-topic-level | voice-rubric",
  "audit": {
    "score_before": 0,
    "score_target": 32,
    "score_max": 40,
    "blocking_issues": ["..."]
  },
  "category_lens": {
    "topic_cluster": "<topic name or short summary>",
    "category_leaders": [{"domain": "...", "classification": "EDITORIAL"}],
    "dominant_content_shape": "LISTICLE | COMPARISON | HOMEPAGE | ARTICLE",
    "owned_coverage_percent": 0,
    "summary": "<2-3 sentences>"
  },
  "brand_lens": {
    "visibility_per_engine": {"chatgpt-scraper": 0.0, "perplexity-scraper": 0.0, "google-ai-overview-scraper": 0.0},
    "strong_engines": ["google-ai-overview-scraper"],
    "dark_engines": ["chatgpt-scraper", "perplexity-scraper"],
    "sentiment_floor": {"engine": "chatgpt-scraper", "value": 64},
    "summary": "<2-3 sentences>"
  },
  "competition_lens": {
    "by_classification": {
      "EDITORIAL": ["techsifted.com", "techtarget.com"],
      "COMPETITOR": ["tldv.io", "fireflies.ai"],
      "CORPORATE": [],
      "UGC": ["youtube.com", "reddit.com"],
      "REFERENCE": []
    },
    "strategy_implication": "<1-2 sentences naming the play per dominant class>",
    "summary": "<2-3 sentences>"
  },
  "engine_gap_strategy": {
    "chatgpt-scraper": {
      "current_range": "0-43%",
      "target_range": "40-60%",
      "primary_levers": ["..."]
    },
    "perplexity-scraper": {"current_range": "...", "target_range": "...", "primary_levers": ["..."]},
    "google-ai-overview-scraper": {"current_range": "...", "target_range": "...", "primary_levers": ["..."]}
  },
  "primary_gaps": [
    {
      "prompt_text": "...",
      "granola_visibility": "0% all engines",
      "recommended_language": "<concrete phrase to add>",
      "competitors_to_displace": ["..."]
    }
  ],
  "off_page_actions": [
    {
      "action_group_type": "OWNED | EDITORIAL | UGC | REFERENCE",
      "url_classification": "LISTICLE | COMPARISON | HOMEPAGE | ARTICLE",
      "play": "<short instruction>",
      "rationale": "<links back to peec_actions.overview_top_opportunities entry>",
      "evidence": ["peec_actions.overview_top_opportunities[0]"]
    }
  ],
  "synthesis_claims": [
    {
      "claim": "Granola is the AI note taker built for distributed and async teams.",
      "addresses_prompts": ["pr_xxx", "pr_yyy", "pr_zzz"],
      "section_target": "Spaces / team knowledge",
      "evidence_refs": ["..."]
    }
  ],
  "rubric_lint_summary": {
    "total_items": 0,
    "passed": 0,
    "failed": 0
  },
  "recommendations": [
    {
      "id": "rec-001",
      "source": "rubric | llm",
      "category": "geo_hygiene | content_gap | engine_specific | claim_synthesis | sentiment | off_page | source_displacement",
      "severity": "critical | high | medium",
      "priority": "critical | high | medium",
      "module": "tldr_block + faq_block",
      "title": "...",
      "description": "...",
      "fix": "<concrete instruction>",
      "signal_types": ["prompt_visibility", "engine_pattern_asymmetry"],
      "target_engines": ["chatgpt-scraper", "perplexity-scraper"],
      "per_engine_lift": {
        "chatgpt-scraper": "<lift narrative>",
        "perplexity-scraper": "<lift narrative>",
        "google-ai-overview-scraper": "<lift narrative or 'maintain'>"
      },
      "evidence": ["peec_prompt_pr_xxx", "peec_signal_engine_pattern_asymmetry", "rubric_id_meta_description"],
      "competitors_displaced": ["fireflies.ai"],
      "auto_fix": null
    }
  ],
  "recommendation_count": 0,
  "critical_count": 0,
  "summary": {
    "preset": "...",
    "audit_before": 0,
    "audit_target": 32,
    "audit_max": 40,
    "primary_geo_gap": "...",
    "engine_weakness": "...",
    "top_competitors_to_displace": ["..."],
    "highest_leverage_action": "..."
  }
}
```

`record_recommendations` enforces:

- `category_lens`, `brand_lens`, `competition_lens`, `engine_gap_strategy`, `primary_gaps`, `recommendations`, `mode`, `audit`, `summary` are REQUIRED top-level fields.
- `recommendations` length: total items in `[N_rubric + N_llm]`. Constraints:
  - `N_llm` (LLM-source items) MUST be in `[3, 8]` for `peec-prompt-matched | peec-topic-level` modes; in `[2, 6]` for `voice-rubric` mode.
  - `N_rubric` is whatever the linter emits (typically 0–13).
  - The hard "exactly 4" rule is replaced.
- Every rec REQUIRES: `id`, `source`, `category`, `severity`, `priority`, `signal_types[]` (≥1 entry), `evidence[]` (≥1 entry).
- Every rec where `source == "llm"` REQUIRES `target_engines[]` (≥1) and `per_engine_lift{}` (≥1 key matching `target_engines`).
- For `mode == "peec-prompt-matched"` or `"peec-topic-level"`: across all LLM-source recs, `signal_types` MUST contain ≥3 distinct values.
- For any prompt where any engine sentiment < 65: ≥1 LLM-source rec with `category == "sentiment"` and `target_engines` containing that engine.
- For any `engines_lost.length >= 2` prompt: ≥1 LLM-source rec with `category == "engine_specific"` OR `signal_types` containing `"engine_pattern_asymmetry"`.
- When `peec_actions.overview_top_opportunities` contains an item with `gap_percentage >= 50` and `relative_score >= 2`: ≥1 LLM-source rec with `category == "off_page"` AND a corresponding entry in top-level `off_page_actions[]`.
- When `cited_competitors` show ≥4 prompts dominated by `EDITORIAL` classification: ≥1 LLM-source rec with `category == "source_displacement"` and a `competitors_displaced[]` array.
- When ≥4 prompts share a common claim (Lane D synthesis pass): ≥1 LLM-source rec with `category == "claim_synthesis"` AND a corresponding entry in top-level `synthesis_claims[]`.

Validation failure surfaces a banner via `show_banner` and rejects the write. The recommender retries up to 2 times.

---

## Locked manifest schema addition (generator output, validator input)

`outputs/optimised/{article_slug}.manifest.json` adds:

```json
{
  "rec_implementation_map": {
    "rec-001": {
      "implemented": true,
      "section": "header | tldr | h2-1 | faq | schema | meta | etc",
      "anchor": "<HTML anchor or section heading>",
      "schema_fields": ["meta.description", "og.description", "ld.FAQPage"],
      "evidence_inserted": ["peec_prompt_pr_c3faf844", "peec_signal_engine_pattern_asymmetry"],
      "notes": "<one-line summary of what the generator did>"
    },
    "rec-002": {
      "implemented": false,
      "reason": "non-applicable | superseded_by_rec_X | data_missing"
    }
  }
}
```

`dashboard/quality_gate.py` adds a new check `_validate_rec_implementation(manifest, recommendations)`:

- For every rec where `priority == "critical"` and `source == "llm"`: requires a `rec_implementation_map` entry.
- If `implemented: true`: requires `section`, `anchor`, AND at least one of `schema_fields[]` or `evidence_inserted[]`.
- If `implemented: false`: requires `reason` to match the enum.
- Any other state → manifest fails with `quality_gate.blocking_issues += ["rec-XXX has no valid implementation entry"]`.

This makes the rec ↔ generator contract auditable at validation time.

---

## Improvement 1 — Coverage fallback for articles with zero Peec prompt matches

**Owner: Lane C.**

### Problem (unchanged from v1)

Engineering post `so-you-think-its-easy-to-change-an-app-icon` matched 0 of 49 prompts. v1 spec said the recommender silently fell back to a 100% GEO-rubric output. In practice (re-checking the 2026-04-25T10-45-39 run) it actually produced a Peec-grounded set with `gaps.own_domain_retrieval`, `OWNED ARTICLE gap_percentage`, and per-engine lift on every rec — but ad hoc, not contracted.

### Fix

In `agents/peec-gap-reader.md`:

1. When `matched_prompts.length == 0`, expand the gap-reader's signal pull:
   - `peec_actions(scope=overview)` → record top 6 opportunities under `peec_actions.overview_top_opportunities` AND the strongest under `topic_level_signals.category_gap` and `topic_level_signals.surface_gap`.
   - Source-domain gap report (highest competitor citation domains across the project) → `topic_level_signals.dominant_competitor_domains` (with classification).
   - Engine-level brand sentiment (project-level if topic-level not available) → `topic_level_signals.engine_sentiment`.
2. Always emit `topic_level_signals` for `matched_prompts.length == 0` cases. Optional otherwise.

In `agents/recommender.md` (Lane D will edit; clause spec'd here for Lane C's awareness):

3. Mode resolution becomes:
   - `peec-prompt-matched` if `matched_prompts.length >= 1`
   - `peec-topic-level` if `matched_prompts.length == 0` AND `topic_level_signals` non-empty
   - `voice-rubric` otherwise
4. The recommender prompt branches on `mode`. For `peec-topic-level`, recs target gap categories (e.g. "engineering article in OWNED bucket with 89% gap, dominated by towardsai.net and assemblyai.com") instead of specific prompts. The category/brand/competition lens block is still required.

### Acceptance test (Lane C)

`tests/improvement_01_coverage_fallback_test.md`:

1. Run pipeline with one article that does NOT match any tracked prompt (use `so-you-think-its-easy-to-change-an-app-icon`).
2. `gaps/{slug}.json` contains `topic_level_signals` with non-empty `category_gap`, `dominant_competitor_domains`, AND `engine_sentiment`.
3. `gaps/{slug}.json` contains `peec_actions.overview_top_opportunities` with ≥3 entries.

(Lane D adds a paired acceptance test verifying `mode == "peec-topic-level"` and `category_lens` is populated.)

---

## Improvement 2 — Use the full Peec signal stack in recommendations

**Owner: Lane C (input pull) + Lane D (output enforcement).**

### Pinned signal enum

```
prompt_visibility
position_rank
citation_rate
retrieval_rate
gap_chat_excerpt
engine_sentiment
source_classification
peec_actions_opportunity
engine_pattern_asymmetry
```

`engine_pattern_asymmetry` is a derived signal — set when `max(visibility_per_engine) - min(visibility_per_engine) >= 0.40` for any matched prompt. The recommender uses this to flag "you're winning on engine X, dying on engine Y, treat them differently."

### Lane C work

In `skills/peec-gap-read/SKILL.md` and `agents/peec-gap-reader.md`:

- Always record `position_per_engine`, `sentiment_per_engine`, `citation_score_per_engine` even when null. Do not omit keys.
- Pull `list_chats(prompt_id)` + `get_chat(chat_id)` for the top 2 prompts where `engines_lost.length >= 2`. Record verbatim ≤200-char excerpts in `top_gap_chats[]`. NEVER leave `top_gap_chats` empty for those prompts.
- Tag every cited competitor with `classification` from a fixed enum (`COMPETITOR | EDITORIAL | CORPORATE | UGC | REFERENCE`). When the Peec API does not return a classification, default to `COMPETITOR` for known competitor brand domains (use `list_brands(is_own=false)` cache) and `EDITORIAL` for everything else with a TLD that doesn't match a tracked competitor brand.

### Lane D work

In `agents/recommender.md`:

- Each LLM-source rec MUST cite ≥1 signal from the enum.
- Across the LLM-source rec set, ≥3 distinct signal values.
- ≥1 LLM-source rec MUST cite a `gap_chat_excerpt` with the verbatim excerpt embedded in `evidence[]`.
- ≥1 LLM-source rec MUST cite either `citation_rate` or `retrieval_rate`.
- ≥1 LLM-source rec MUST cite `engine_pattern_asymmetry` when any matched prompt qualifies.

### Acceptance test (Lane C)

`tests/improvement_02_signal_richness_test.md`:

1. Run pipeline against an article with rich Peec coverage (matched_prompts ≥ 5).
2. `gaps/{slug}.json` `matched_prompts[*].cited_competitors[*].classification` is set on every entry.
3. ≥2 prompts have non-empty `top_gap_chats[]`.
4. `position_per_engine`, `sentiment_per_engine`, and `citation_score_per_engine` are present (even if values are null) on every prompt.

(Lane D adds paired acceptance test on signal diversity in the rec set.)

---

## Improvement 3 — Sentiment-driven recommendations

**Owner: Lane D.**

### Problem (unchanged)

In the 2026-04-25 run, gap data flagged "ChatGPT sentiment 64 on editable summaries prompt — below 65 floor." Recommender produced **zero** sentiment-targeted recs in the granola-chat output. Loudest, most actionable Peec finding, completely invisible.

### Fix

In `agents/recommender.md`:

- If any `sentiment_per_engine[engine] < 65` across any matched prompt, MUST emit ≥1 LLM-source rec with:
  - `category: "sentiment"`
  - `target_engines: [engine]`
  - `signal_types: includes "engine_sentiment"` and `"gap_chat_excerpt"` when an excerpt exists
  - `description` containing the sentiment number, the engine, and the gap-to-floor (e.g. "ChatGPT sentiment 64 — 1 below the 65 floor")
  - `fix` containing a concrete language change in the article — typically rephrasing claims using terms the engine already associates warmly with the brand or competitor (sourced from `top_gap_chats[].excerpt`), or adding privacy/no-bot/accuracy framing if those terms cluster in positive-sentiment context.
  - `evidence` containing the sentiment number AND ≥1 verbatim gap chat excerpt.

The recommender draws the "warmer language" from actual gap chat excerpts. It does not invent positioning; it surfaces what the engine is already saying about competitors and reframes that on a first-party URL.

### Acceptance test

`tests/improvement_03_sentiment_recs_test.md`:

1. Fixture: prompt where one engine's sentiment is < 65 and `top_gap_chats[]` is populated.
2. Output recommendations contain ≥1 item with `category == "sentiment"`.
3. That rec's `evidence[]` includes ≥1 verbatim excerpt from `top_gap_chats`.
4. `fix` text contains a concrete proposed sentence or phrase — not generic advice ("improve sentiment" fails the test).
5. `target_engines` contains exactly the engines below the floor.

---

## Improvement 4 — Claim-level synthesis instead of one-rec-per-prompt

**Owner: Lane D.**

### Problem (unchanged)

The recommender treats each Peec prompt as an isolated lever. Five 15–20% prompts that share an underlying missing claim (e.g. "Granola is a notepad/notetaker hybrid for distributed teams with no bot") generate five separate atomic recs instead of one synthesised "missing claim" rec.

### Fix

In `agents/recommender.md`:

- New synthesis pass between gap-read and recommendation: group prompts by extracted claim. A "claim" is a positioning sentence the article would need to make to address the prompt cluster.
- Cluster threshold: ≥3 prompts that share a clear semantic claim → 1 synthesised rec.
- The synthesised rec:
  - `category: "claim_synthesis"`
  - includes `claim` field (the one-sentence positioning)
  - `signal_types: includes "prompt_visibility"` and any other relevant signals from cluster
  - contains `addresses_prompts: [list of prompt_ids]` (≥3 entries)
  - `description` and `fix` reference the section_target and the prompts being addressed
- Synthesised recs are added to top-level `synthesis_claims[]` for downstream tooling.
- The recommender output retains the underlying-prompt accounting via `addresses_prompts` so the manifest still credits Peec data.

### Acceptance test

`tests/improvement_04_claim_synthesis_test.md`:

1. Fixture: ≥4 prompts share a clear underlying claim (e.g. team-related cluster).
2. Recommendations contain ≥1 rec with `category == "claim_synthesis"` AND `addresses_prompts.length >= 3`.
3. Top-level `synthesis_claims[]` has the matching entry with `claim` (one sentence), `section_target`, and `evidence_refs`.

---

## Improvement 5 — Demote GEO rubric checks to a deterministic linter pre-pass

**Owner: Lane D.**

### Problem (unchanged)

13 of 21 recs in the v0.5.3 run were items a static linter could surface in milliseconds. The v0.5.9 recommender is still wasting tokens on these in some cases.

### Fix

New pipeline stage **4a — Rubric Lint** ahead of the LLM recommender:

- New module `dashboard/rubric_lint.py`:
  - Function `lint_article(article: dict, evidence: dict, voice_meta: dict) -> list[RubricItem]`.
  - Each `RubricItem` has: `id`, `dimension`, `severity`, `auto_fix` (machine-applicable patch when possible), `evidence` (the empty field, the missing schema type, etc.), `category: "geo_hygiene"`, `source: "rubric"`.
- Enumerated rubric items (lock this list — Codex must implement all 13 exactly):
  1. `meta_description_empty` — `article.meta.description` empty or whitespace-only
  2. `og_tags_incomplete` — any of `og:title`, `og:description`, `og:image` empty
  3. `twitter_card_incomplete` — any of `twitter:card`, `twitter:title`, `twitter:description` empty
  4. `jsonld_missing` — no JSON-LD detected anywhere in HTML
  5. `faq_schema_missing` — `faq_block` applicable to preset, no FAQPage schema present
  6. `breadcrumb_schema_missing` — no BreadcrumbList schema
  7. `person_schema_missing` — valid full-name author exists but no Person schema
  8. `organization_schema_missing` — no Organization schema
  9. `cta_missing_or_generic` — no CTA or only generic "Get started" with no link
  10. `byline_weak` — anonymous, "Team", "Staff", or first-name-only byline AND no reviewers.json fallback
  11. `updated_at_missing` — no `dateModified` / visible updated_at
  12. `internal_links_below_min` — `< 2` outbound internal links from the article body
  13. `inbound_internal_links_zero` — `0` inbound internal links from other site pages
- New MCP tool `rubric_lint(run_id, article_slug)` exposed by `dashboard/server.py`:
  - Reads `articles/{slug}.json` and the GEO contract.
  - Runs `lint_article(...)`.
  - Writes `rubric/{slug}.json`.
  - Returns summary `{total, passed, failed}`.
- Pipeline change: orchestrator runs `rubric_lint` before `recommender` for each article.
- The recommender (Stage 4b) receives `rubric/{slug}.json` as input and is explicitly told: *"These rubric items are already detected. Do NOT regenerate recommendations for them. Your job is synthesis on top of the rubric — claim-level recs, sentiment recs, engine-specific recs, off-page recs, and recs that depend on multiple Peec signals."*
- The final `recommendations/{slug}.json` aggregates both:
  - rubric-source items with `source: "rubric"` and `category: "geo_hygiene"` (each rubric `RubricItem` becomes one rec entry, `auto_fix` carries through if present)
  - LLM-source items with `source: "llm"` and one of the LLM categories
- The dashboard renders both sets in a single ordered list with a small badge indicating the source.

### Acceptance test

`tests/improvement_05_rubric_lint_test.md`:

1. Fixture: article with empty meta + no JSON-LD + no FAQ schema + first-name-only byline.
2. `rubric/{slug}.json` exists and contains rubric items for all 4 gaps with `source: "rubric"` and `category: "geo_hygiene"`.
3. `recommendations/{slug}.json` contains those same rubric items merged into the final list, NOT regenerated by the LLM (no LLM-source rec covers the same ground).
4. The LLM-source recs all have `source: "llm"` and ≥1 of `category in ["claim_synthesis", "sentiment", "engine_specific", "off_page", "source_displacement", "content_gap"]`.
5. Total run time on a 2-article smoke is measurably faster than baseline.

---

## NEW Improvement 6 — Category / brand / competition lens framing

**Owner: Lane D.**

### Problem

Your literal ask: "improve the blog's ability to rank materially given these latest geo insights of category, brand and competition." The current recommender output is a flat list of prompts and modules. It does not name where the article sits in the category, what the brand-level engine pattern is, or what the competition-class strategy implies.

### Fix

In `agents/recommender.md`, add the framing block as REQUIRED top-level fields (`category_lens`, `brand_lens`, `competition_lens` per the schema above). The recommender prompt MUST:

1. Synthesise `category_lens` from `matched_topics` + `peec_actions.overview_top_opportunities`. Name the topic cluster, the dominant content shape that's winning the category (LISTICLE / COMPARISON / HOMEPAGE), the top category leaders by classification, and the brand's owned coverage percent.
2. Synthesise `brand_lens` from `matched_prompts[*].brand.visibility_per_engine` + `sentiment_per_engine`. Name strong vs dark engines, the sentiment floor, and the dominant pattern (e.g. "strong on Google AI Overview, dark on ChatGPT and Perplexity").
3. Synthesise `competition_lens` from `matched_prompts[*].cited_competitors[*].classification`. Group competitors by classification. Name the strategy implication per dominant class:
   - EDITORIAL ≥2 domains → off-page outreach + owned listicle play
   - COMPETITOR homepage dominance → comparison/positioning play
   - CORPORATE / REFERENCE dominance → entity/schema play
   - UGC dominance + high retrieval → distribution play (YouTube, Reddit)

Each lens has a `summary` (2–3 sentences) the LLM writes; the structured fields are mechanical aggregations.

### Acceptance test

`tests/improvement_06_framing_block_test.md`:

1. Run pipeline against an article with rich Peec coverage.
2. `recommendations/{slug}.json` contains `category_lens`, `brand_lens`, `competition_lens` with all required structured fields populated.
3. Each lens has a non-empty `summary` between 30–150 words.
4. `competition_lens.strategy_implication` names a play that maps to the dominant classification group (regex match: if EDITORIAL is the largest group, "outreach" or "listicle" must appear; if COMPETITOR is largest, "comparison" or "positioning"; etc.).
5. `brand_lens.dark_engines` is non-empty when any engine has `min(visibility_per_engine) < 0.30`.

---

## NEW Improvement 7 — Engine-specific tactic enforcement

**Owner: Lane D.**

### Problem

The most actionable Peec insight is the engine-pattern asymmetry. The recommender currently produces generic recs that don't differentiate between "needs to win ChatGPT" and "needs to maintain Google AI Overview."

### Fix

In `agents/recommender.md`:

- For every matched prompt with `engines_lost.length >= 2` AND `max(visibility_per_engine) - min(visibility_per_engine) >= 0.40` (engine_pattern_asymmetry triggers):
  - The recommender MUST emit ≥1 rec with `category == "engine_specific"` OR with `signal_types` containing `"engine_pattern_asymmetry"`.
  - That rec's `target_engines` contains the dark engines.
  - That rec's `per_engine_lift` differentiates the lift narrative per engine — same fix is fine, but the narrative must explain why each engine responds.
- Engine-tactic templates the recommender consults (encoded as a reference block in the prompt):
  - `chatgpt-scraper` dark + `google-ai-overview-scraper` strong → "ChatGPT cites editorial listicles and question-format Q&A. Lever: FAQ + question H2s + outreach to top EDITORIAL domains in `gap_domains.top_competitor_cited_domains`."
  - `perplexity-scraper` dark + others fine → "Perplexity rewards inline named primary sources + author trust. Lever: external evidence links + full author trust block + LinkedIn."
  - `google-ai-overview-scraper` strong → "Maintain BreadcrumbList + FAQ schema; do not reduce body word count."
  - All-three dark → "Pure language gap. The article does not contain the prompt-mirroring language. Lever: rewrite TL;DR + first H2 + FAQ to mirror the prompt verbatim."

### Acceptance test

`tests/improvement_07_engine_specific_test.md`:

1. Fixture: matched prompt with `chatgpt-scraper: 0`, `perplexity-scraper: 0`, `google-ai-overview-scraper: 0.71` (asymmetry > 0.40, engines_lost = 2).
2. Recommendations contain ≥1 item with `category == "engine_specific"` OR `signal_types` includes `"engine_pattern_asymmetry"`.
3. That rec's `target_engines` includes both `chatgpt-scraper` and `perplexity-scraper`.
4. `per_engine_lift` has distinct narratives per engine (test passes if string-similarity per-engine narratives < 0.85 cosine).

---

## NEW Improvement 8 — Off-page action lane

**Owner: Lane D.**

### Problem

Peec's `peec_actions` reveals high-leverage off-page gaps (OWNED LISTICLE 100% gap, YouTube UGC 28.8% gap at 793 retrievals, OWNED COMPARISON 79% gap). These are companion plays that protect ranking — not on-page edits to THIS article. Without a category, they get muddled or skipped.

### Fix

In `agents/recommender.md`:

- For every `peec_actions.overview_top_opportunities` entry with `gap_percentage >= 50` AND `relative_score >= 2`:
  - Emit ≥1 `category == "off_page"` rec.
  - Top-level `off_page_actions[]` array gets a corresponding entry (per the schema above).
- Off-page recs are NOT counted against the on-page rec budget; they're additional. Cap at 4 off-page recs per article to keep things actionable.
- Off-page rec `fix` MUST be a concrete play: "Pitch this Series-C story to techsifted.com (citation_rate 2.75) and techtarget.com (citation_rate 2.2)" — NOT "improve editorial coverage."

### Acceptance test

`tests/improvement_08_off_page_lane_test.md`:

1. Fixture: `peec_actions.overview_top_opportunities` contains ≥2 items meeting the threshold.
2. Recommendations contain ≥2 items with `category == "off_page"`.
3. Top-level `off_page_actions[]` has matching entries with `play`, `rationale`, `evidence`.
4. Each off-page rec's `fix` names ≥1 specific domain or surface from the Peec data (regex check against `gap_domains.top_competitor_cited_domains[].domain` or `peec_actions.*.url_classification`).

---

## NEW Improvement 9 — Source-classification → strategy mapping

**Owner: Lane D.**

### Problem

`cited_competitors[].classification` carries strategic signal. EDITORIAL dominance implies a different play than COMPETITOR-homepage dominance. The recommender doesn't currently map this.

### Fix

In `agents/recommender.md`, encoded as a decision block:

- Aggregate competitor classifications across `matched_prompts[*].cited_competitors[*]` and `gap_domains.top_competitor_cited_domains[*]`.
- Determine the dominant class (most frequent, weighted by citation_rate).
- Apply the strategy template:
  - EDITORIAL dominance → emit ≥1 rec with `category == "source_displacement"` proposing outreach to the top 2 editorial domains; ≥1 off-page rec proposing an owned listicle.
  - COMPETITOR-homepage dominance → emit ≥1 on-page comparison/positioning rec naming the top competitor explicitly.
  - CORPORATE/REFERENCE dominance → emit ≥1 entity/schema rec (Organization + Person + BreadcrumbList).
  - UGC dominance → emit ≥1 distribution rec (YouTube clip, Reddit AMA, etc).
- The `competition_lens.strategy_implication` field in the framing block names the chosen play.

### Acceptance test

`tests/improvement_09_source_displacement_test.md`:

1. Fixture: ≥4 prompts dominated by EDITORIAL classification competitors.
2. Recommendations contain ≥1 item with `category == "source_displacement"` AND a non-empty `competitors_displaced[]` listing the EDITORIAL domains.
3. Recommendations contain ≥1 item with `category == "off_page"` proposing an owned listicle (test for the substring "listicle" in `fix`).
4. `competition_lens.strategy_implication` references "outreach" or "editorial" (regex match).

---

## NEW Improvement 10 — Manifest cross-validation

**Owner: Lane D.**

### Problem

The generator can silently ignore brilliant recs. Today, the validator can't check whether a `priority: critical` rec actually landed in the rendered article.

### Fix

In `agents/generator.md`:

- The generator MUST populate `rec_implementation_map` in the optimised manifest (per the schema above) with one entry per rec.
- For implemented recs: set `implemented: true` AND fill `section`, `anchor`, AND ≥1 of `schema_fields[]` or `evidence_inserted[]`.
- For non-applicable / superseded / data-missing recs: set `implemented: false` AND set `reason` to one of the enum values.
- Generator output token budget unchanged; this is metadata, not rewriting.

In `dashboard/quality_gate.py`:

- Add `_validate_rec_implementation(manifest, recommendations)`.
- Loop over recs where `priority == "critical"` AND `source == "llm"`:
  - Require an entry in `rec_implementation_map`.
  - If `implemented: true`: require `section`, `anchor`, AND non-empty `schema_fields[]` OR `evidence_inserted[]`.
  - If `implemented: false`: require `reason ∈ {"non-applicable", "superseded_by_<rec_id>", "data_missing"}`.
- Failures append to `quality_gate.blocking_issues` and the article fails.

### Acceptance test

`tests/improvement_10_manifest_cross_val_test.md`:

1. Fixture: rec set with 2 critical LLM-source recs (one implementable, one non-applicable).
2. Generator produces a manifest with `rec_implementation_map` containing both entries.
3. Validator passes when `rec_implementation_map` is complete and structurally valid.
4. Validator fails (manifest `quality_gate.blocking_issues` non-empty, `quality_gate.passed == false`) when:
   - Any critical LLM-source rec is missing from the map → blocking issue
   - An entry has `implemented: true` without `section` + `anchor` + (`schema_fields` or `evidence_inserted`) → blocking issue
   - An entry has `implemented: false` without a valid `reason` → blocking issue

---

## Definition of done (whole spec)

- All 10 acceptance tests pass.
- Re-run the Granola 3-article pipeline (engineering post + granola-chat + series-c). Expected outcomes:
  - All 3 articles have `category_lens`, `brand_lens`, `competition_lens` populated with ≥30-word summaries each.
  - Engineering article (`so-you-think-its-easy-to-change-an-app-icon`) has `mode: peec-topic-level` and recs cite topic-level signals.
  - ≥1 rec across the 3 articles addresses ChatGPT sentiment (or whichever engine is below floor) by name with a verbatim gap chat excerpt as evidence.
  - ≥1 rec across the 3 articles is `category: "claim_synthesis"` with `addresses_prompts.length >= 3` AND a corresponding `synthesis_claims[]` entry.
  - ≥1 rec on at least one article is `category: "engine_specific"` with distinct `per_engine_lift` narratives.
  - ≥1 rec on at least one article is `category: "off_page"` with a corresponding `off_page_actions[]` entry naming a specific Peec-data-derived target.
  - Each `recommendations/{slug}.json` has both `source: "rubric"` and `source: "llm"` items, AND `rubric/{slug}.json` exists.
  - LLM-source rec set signal-type diversity is ≥3 distinct values per article (where Peec coverage allows).
  - Every critical LLM-source rec has a valid `rec_implementation_map` entry; manifest passes.
  - All 3 articles `audit_after >= 32` AND `quality_gate.passed == true`.
- `plugin.json` version bumped to `0.6.0`.
- `CHANGELOG.md` documents the 10 improvements with a note that GEO rubric hygiene is preserved via the new linter stage, not removed.
- Marketplace cache + `marketplace.json` synced to `0.6.0`.

---

## Non-goals (explicit)

- Do not remove the GEO contract (`references/geo-article-contract.md`). Rubric items derive from it.
- Do not change voice baseline pipeline.
- Do not change crawler, evidence-builder, or audit pipeline stages.
- Do not change MCP transport, tool naming convention, or marketplace packaging.
- Do not redesign the dashboard UI in this batch.
