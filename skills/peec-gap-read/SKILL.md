---
name: peec-gap-read
description: Canonical recipe for reading a brand's gap data from the Peec AI MCP for a specific article. Use when you need to produce the evidence trail that grounds a GEO recommendation in live AI citation behaviour. Consumed by the peec-gap-reader sub-agent and directly by the recommender when running single-article analysis.
version: 0.1.3
---

# Peec Gap Read Recipe

How to pull a complete, evidence-ready gap picture for a single article from the Peec AI MCP.

## Prerequisites

- User has the Peec AI MCP connected to Claude Desktop.
- User has at least one Peec project with tracked topics + prompts + competitors.
- Data is ≥ 24 hours old (Peec prompts run daily).

If any of these fail, return a `notes` field with the specific gap. Do not fabricate.

## Core Peec MCP rules

Before running this recipe in Cowork, use `ToolSearch` to load the connected Peec tool family by
capability. Do not assume the server prefix is literally `peec`; Cowork can expose external MCP
servers under UUID-based prefixes.

Examples:
- `mcp__peec__list_projects`
- `mcp__57fe1a18-bd7d-47fc-846e-bb20a3bdb291__list_projects`

The exact prefix can change across users and installs. The tool suffixes are what matter.

From the Peec MCP server instructions:
- **Metrics**: `visibility`, `share_of_voice`, `retrieved_percentage` are 0-1 ratios (×100 for display). `sentiment` is 0-100. `position` is rank (lower = better). `retrieval_rate` and `citation_rate` are averages, NEVER percentages — display as-is, never × 100.
- **Break down by engine** (model_id), not just aggregate.
- **Default range 30 days.** Weekly analyses use 7 days.
- **Resolve IDs to names** via `list_*` tools. Never show raw IDs in user-facing output.
- **Cite date range** (`date_range` field in responses).
- **Gap filter** on `get_domain_report` finds sources where competitors are cited but the user isn't. This is the remediation roadmap.
- **Never use a universal citation-rate threshold** — per-engine benchmarks diverge 4×.
- **Locked gap schema**: every emitted gap artefact must conform to the v0.6.0 schema. Do not
  rename fields to match ad hoc Peec response names.

## Per-article recipe

### 1. Validate project

```
<connected-peec>__list_projects → confirm peec_project_id is live.
```

### 2. Read the article and classify its target prompt-space

Given the article record (H1, top H2s, intro paragraph, entities, body theme):

```
<connected-peec>__list_topics(peec_project_id)
```

If topics exist, pick the 1-2 best topic candidates. Treat them as hints only.

### 3. Match prompts first (3–8 target, 1–2 acceptable if sparse)

```
<connected-peec>__list_prompts(project_id=<peec_project_id>)
```

Among returned prompts, select those that are most likely the ones this article is trying to win.
Use prompt-first matching even if the project has zero topics.

Matching criteria:

- Title/H1 phrasing ≈ prompt phrasing
- Article H2 phrasing ≈ prompt phrasing (question-match)
- Intro paragraph or article summary ≈ prompt intent
- Entities in the article also in the prompt
- Topic alignment, if the project has topics

Cap at 8.

If fewer than 3 match:

- widen to adjacent prompts with the same semantic intent
- accept the sparse match if it is still the best evidence available
- note it explicitly via `notes: "sparse prompt match: only {N} prompts matched"`

If zero prompts match, continue to section 6 before writing. A zero-prompt article can still produce
`match_mode: "topic-level"` when topic-level signals are available.

### 4. Per-prompt reports

For each matched prompt, run:

```
<connected-peec>__get_brand_report(
    prompt_id=<id>
)
→ { visibility, share_of_voice, position, citation_score, sentiment } per engine.

<connected-peec>__get_domain_report(
    prompt_id=<id>,
    gap filter
)
→ competitor URLs cited for this prompt where the own brand isn't, per engine.
```

Normalize the brand block before writing:

- Always include `visibility_per_engine`, `sov_per_engine`, `position_per_engine`,
  `sentiment_per_engine`, and `citation_score_per_engine` under `brand`.
- For every engine returned by Peec for the prompt, include all five per-engine metric keys. Use
  `null` for unavailable values; never omit `position_per_engine`, `sentiment_per_engine`, or
  `citation_score_per_engine`.
- If Peec returns no engine rows for a prompt, emit the five empty metric objects and add a
  cold-start note.
- Use `citation_score_per_engine` for brand citation score. Use `citation_rate_per_engine` only for
  cited competitor domain rates.

Classify cited competitors before writing:

```
<connected-peec>__list_brands(project_id=<peec_project_id>, is_own=false)
```

Every `cited_competitors[]` entry requires `classification` in this enum:
`COMPETITOR | EDITORIAL | CORPORATE | UGC | REFERENCE`.

Classification precedence:

- Use Peec's returned classification when it is present and in the enum.
- Domains returned by `list_brands(is_own=false)` are `COMPETITOR`.
- Domains whose registrable root or TLD does not match a tracked competitor brand default to
  `EDITORIAL`.
- Preserve Peec-returned `CORPORATE`, `UGC`, or `REFERENCE` values.

If `citation_score=null` or `visibility=null`, the prompt has no data yet. Record as cold-start. Do not infer rates.

### 5. Pull the actual AI responses (the "oh wow" moment)

```
<connected-peec>__list_chats(prompt_id=<id>) → recent responses across engines.
```

Sort matched prompts by severity: `engines_lost.length >= 2`, then lowest visibility, then strongest
competitor citation signal. For the top 2 prompts where `engines_lost.length >= 2`, chat evidence is
mandatory.

Filter for chats where:
- Competitor domains appeared
- The own brand's domain did NOT appear
- The chat is from a lost engine when possible

```
<connected-peec>__get_chat(chat_id=<id>) → full response text.
```

Extract verbatim excerpts showing the cited competitor text. Each excerpt must be 200 characters or
shorter. This is the raw evidence that makes recommendations credible.

For each of the top 2 high-loss prompts, `top_gap_chats[]` must contain at least one entry with
`chat_id`, `engine`, `excerpt`, and `cited_urls`. If Peec returns no usable chats after checking
available recent chats, do not fabricate. Mark the gap read inadmissible and name the missing prompt
in `blocker_reason` instead of silently writing an empty `top_gap_chats[]`.

### 6. Peec Actions (native remediation)

```
<connected-peec>__get_actions(scope=overview)
→ capture the top overview opportunities only.
```

For this plugin stage, do **not** drill into `scope=owned`, `scope=editorial`, `scope=reference`,
or `scope=ugc`.

Reason:
- the recommender only needs the overview slice as a prioritization signal
- the live Peec endpoint can reject follow-up action requests for some branches, which turns a
  useful gap read into an avoidable runtime failure

Record the strongest overview opportunities and let the recommender combine them with the rest of
the article, evidence, and Schmidt-rule analysis. When the project has any actions data,
`peec_actions.overview_top_opportunities` is required and must contain at least 3 entries if Peec
returns 3 or more. Prefer the top 6 entries.

### 6a. Topic-level fallback for zero prompt matches

When `matched_prompts.length == 0`, pull the broader signal stack before writing:

```
<connected-peec>__get_actions(scope=overview)
<connected-peec>__get_domain_report(project_id=<peec_project_id>, gap filter)
<connected-peec>__get_brand_report(project_id=<peec_project_id> or topic_id=<matched_topic_id>)
```

Use the connected tool's supported arguments; some Peec installs expose project-level and topic-level
reports through the same suffix with different parameters.

Write:

- `match_mode: "topic-level"`
- `topic_level_signals.category_gap`: strongest overview action, preferring `OWNED`.
- `topic_level_signals.surface_gap`: strongest non-owned overview action, preferring `EDITORIAL`.
- `topic_level_signals.dominant_competitor_domains[]`: highest source-domain gap domains with
  `domain` and `classification`.
- `topic_level_signals.engine_sentiment`: engine-level sentiment from topic-level brand report when
  available, otherwise project-level brand report.

If neither prompt-level nor topic-level evidence is available, write `match_mode: "none"` and mark
the gap read inadmissible with a specific blocker.

### 7. Output shape

```json
{
  "article_slug": "<slug>",
  "match_mode": "prompt-first",
  "matched_topics": [
    {"topic_id": "", "topic_name": ""}
  ],
  "matched_prompts": [
    {
      "prompt_id": "",
      "prompt_text": "",
      "match_reasons": [],
      "brand": {
        "visibility_per_engine": {"chatgpt-scraper": 0.12, "perplexity-scraper": 0.0},
        "sov_per_engine": {},
        "position_per_engine": {"chatgpt-scraper": null, "perplexity-scraper": null},
        "sentiment_per_engine": {"chatgpt-scraper": null, "perplexity-scraper": null},
        "citation_score_per_engine": {"chatgpt-scraper": null, "perplexity-scraper": null}
      },
      "engines_lost": ["perplexity-scraper", "chatgpt-scraper"],
      "cited_competitors": [
        {
          "domain": "otter.ai",
          "classification": "COMPETITOR",
          "citation_rate_per_engine": {"chatgpt-scraper": 2.1}
        }
      ],
      "top_gap_chats": [
        {"chat_id": "", "engine": "chatgpt-scraper", "excerpt": "<verbatim text ≤200 chars>", "cited_urls": []}
      ],
      "notes": ""
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
    "dominant_competitor_domains": [{"domain": "techsifted.com", "classification": "EDITORIAL"}],
    "engine_sentiment": {"chatgpt-scraper": 64, "perplexity-scraper": 71, "google-ai-overview-scraper": 79}
  },
  "peec_actions": {
    "overview_top_opportunities": [
      {"action_group_type": "OWNED", "url_classification": "LISTICLE", "opportunity_score": 0.27, "gap_percentage": 100, "coverage_percentage": 0, "note": ""}
    ]
  },
  "data_freshness": "YYYY-MM-DD",
  "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "notes": ""
}
```

Schema hardening checklist before `record_peec_gap`:

- `matched_prompts[].brand.position_per_engine` is present.
- `matched_prompts[].brand.sentiment_per_engine` is present.
- `matched_prompts[].brand.citation_score_per_engine` is present.
- `matched_prompts[].cited_competitors[].classification` is present and in the fixed enum.
- At least 2 prompts with `engines_lost.length >= 2` have non-empty `top_gap_chats[]` when at
  least 2 such prompts exist.
- `topic_level_signals` is present and non-empty when `matched_prompts.length == 0`.
- `peec_actions.overview_top_opportunities` has at least 3 entries when Peec returned any actions
  data.

## Cold-start handling

If Peec data is < 30 days or the project was just created:
- Record `notes: "cold-start: data < 30 days, confidence low"`.
- Report metrics as captured (may be sparse).
- The recommender still runs but leans on Schmidt rules.

## Cache hints for the orchestrator

Within one pipeline run, prompts rarely change. Cache `list_prompts(project_id)` results to
`{peec_cache_dir}/prompts-{peec_project_id}.json` and reuse them across articles.
