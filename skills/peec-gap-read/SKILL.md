---
name: peec-gap-read
description: Canonical recipe for reading a brand's gap data from the Peec AI MCP for a specific article. Use when you need to produce the evidence trail that grounds a GEO recommendation in live AI citation behaviour. Consumed by the peec-gap-reader sub-agent and directly by the recommender when running single-article analysis.
version: 0.1.0
---

# Peec Gap Read Recipe

How to pull a complete, evidence-ready gap picture for a single article from the Peec AI MCP.

## Prerequisites

- User has the Peec AI MCP connected to Claude Desktop.
- User has at least one Peec project with tracked topics + prompts + competitors.
- Data is ≥ 24 hours old (Peec prompts run daily).

If any of these fail, return a `notes` field with the specific gap. Do not fabricate.

## Core Peec MCP rules

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
mcp__peec__list_projects → confirm peec_project_id is live.
```

### 2. Classify the article's target prompt-space

Given the article record (H1, top H2s, entities, body theme):

```
mcp__peec__list_topics(peec_project_id)
```

Pick the 1–2 best-matching topics. If no topic matches, check if the project has topics at all. If none, return `notes: "project has no tracked topics — user should configure topics in app.peec.ai"`.

### 3. Match prompts (3–8)

```
mcp__peec__list_prompts(topic_id=<matched>)
```

Among returned prompts, select those that are most likely the ones this article is trying to win. Matching criteria:

- Article H2 phrasing ≈ prompt phrasing (question-match)
- Entities in the article also in the prompt
- Topic alignment

Cap at 8. If fewer than 3 match, widen to the next-best topic or accept the sparse match and note it.

### 4. Per-prompt reports

For each matched prompt, run:

```
mcp__peec__get_brand_report(
    prompt_id=<id>,
    brand=<brand from project own brand>
)
→ { visibility, share_of_voice, position, citation_score, sentiment } per engine.

mcp__peec__get_domain_report(
    prompt_id=<id>,
    gap_filter=true
)
→ competitor URLs cited for this prompt where the own brand isn't, per engine.
```

If `citation_score=null` or `visibility=null`, the prompt has no data yet. Record as cold-start. Do not infer rates.

### 5. Pull the actual AI responses (the "oh wow" moment)

```
mcp__peec__list_chats(prompt_id=<id>) → recent responses across engines.
```

Filter for the top 3 chats where:
- Competitor domains appeared
- The own brand's domain did NOT appear

```
mcp__peec__get_chat(chat_id=<id>) → full response text.
```

Extract a 100–200 character excerpt showing the cited competitor text. This is the raw evidence that makes recommendations credible.

### 6. Peec Actions (native remediation)

```
mcp__peec__get_actions(scope=overview)
→ drill into relevant taxonomy branch (owned/editorial/reference/ugc).
```

Surface Peec's own recommendations for this brand on this prompt-space alongside our structural ones.

### 7. Output shape

```json
{
  "matched_prompts": [
    {
      "prompt_id": "",
      "prompt_text": "",
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
  "peec_actions": {"owned": [], "editorial": [], "reference": [], "ugc": []},
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

Within one pipeline run, topics and prompts rarely change. If the orchestrator invokes multiple `peec-gap-reader` calls for different articles on the same topic, it should cache `list_prompts(topic_id)` results to `{peec_cache_dir}/prompts-{topic_id}.json` and pass that path to subsequent readers to avoid redundant MCP calls.
