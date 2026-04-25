---
name: peec-gap-read
description: Canonical recipe for reading a brand's gap data from the Peec AI MCP for a specific article. Use when you need to produce the evidence trail that grounds a GEO recommendation in live AI citation behaviour. Consumed by the peec-gap-reader sub-agent and directly by the recommender when running single-article analysis.
version: 0.1.2
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

If `citation_score=null` or `visibility=null`, the prompt has no data yet. Record as cold-start. Do not infer rates.

### 5. Pull the actual AI responses (the "oh wow" moment)

```
<connected-peec>__list_chats(prompt_id=<id>) → recent responses across engines.
```

Filter for the top 3 chats where:
- Competitor domains appeared
- The own brand's domain did NOT appear

```
<connected-peec>__get_chat(chat_id=<id>) → full response text.
```

Extract a 100–200 character excerpt showing the cited competitor text. This is the raw evidence that makes recommendations credible.

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
the article, evidence, and Schmidt-rule analysis.

### 7. Output shape

```json
{
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
        "visibility_per_engine": {"chatgpt": 0.12, "perplexity": 0.0},
        "sov_per_engine": {},
        "position_per_engine": {},
        "citation_score_per_engine": {},
        "sentiment_per_engine": {}
      },
      "engines_lost": ["perplexity", "chatgpt"],
      "cited_competitors": [
        {"domain": "otter.ai", "urls": [...], "cite_rate_per_engine": {"chatgpt": 2.1}}
      ],
      "top_gap_chats": [
        {"chat_id":"", "engine":"chatgpt", "excerpt":"<verbatim text ≤200 chars>", "cited_urls":[]}
      ]
    }
  ],
  "peec_actions": {
    "overview_top_opportunities": []
  },
  "data_freshness": "YYYY-MM-DD",
  "notes": ""
}
```

## Cold-start handling

If Peec data is < 30 days or the project was just created:
- Record `notes: "cold-start: data < 30 days, confidence low"`.
- Report metrics as captured (may be sparse).
- The recommender still runs but leans on Schmidt rules.

## Cache hints for the orchestrator

Within one pipeline run, prompts rarely change. Cache `list_prompts(project_id)` results to
`{peec_cache_dir}/prompts-{peec_project_id}.json` and reuse them across articles.
