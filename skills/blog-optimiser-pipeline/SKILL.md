---
name: blog-optimiser-pipeline
description: Canonical orchestration playbook for the AI Search Blog Optimiser pipeline. Runs in the main session, uses disk-first state, and only opens the dashboard after a fresh run has been registered.
version: 0.6.0
---

# Blog Optimiser Pipeline (v0.6.0)

This playbook is executed by the main session when `/blog-optimiser` runs. The main session is the orchestrator. Sub-agents are leaf workers only.

## Non-negotiables

- Never open the dashboard before `register_run`.
- Never call `open_dashboard` without a `run_id`.
- Never call `get_paths`.
- Never read historical runs during a new run.
- Never use the Crawl4AI docs/context endpoint as a prereq probe.
- Keep prereq outputs small and structured.
- Leaf workers must use the dashboard MCP artifact tools for host-side reads and writes.
- The absolute paths returned by `register_run` are for host-side MCP `output_path` arguments only. Do not use them with sandboxed `Bash`, `Read`, or `Write`.
- Never assume the Peec MCP server prefix is literally `peec`. In Cowork, external MCP servers can appear under UUID-based prefixes.
- Never assume the Firecrawl MCP server prefix is literally `firecrawl`. Discover Firecrawl by capability (`firecrawl_scrape`, `firecrawl_map`) and prefer it when it is connected.

## Pipeline stages

1. `prereqs`
2. `crawl`
3. `voice`
4. `analysis`
5. `evidence`
6. `recommendations`
7. `draft`

The run's `state.json` is the source of truth. Update it on disk after every stage transition.

## Fresh run flow

### Stage 0 — Prereqs

Run prerequisites before creating or opening anything:

1. Use `ToolSearch` to discover whether a connected Peec MCP is available.
   - Look for tools that expose the Peec capability set: `list_projects`, `list_prompts`,
     `list_chats`, `get_chat`, `get_actions`, `get_brand_report`, and `get_domain_report`.
   - Do not assume the tool prefix is `mcp__peec__`. A valid connected Peec MCP may look like
     `mcp__57fe1a18-bd7d-47fc-846e-bb20a3bdb291__list_projects`.
   - If such a tool family exists, load it and use its `list_projects` tool to match the project.
   - If no Peec tool family exists, stop immediately. Peec is required for this product.
2. Use `ToolSearch` to discover whether a connected Firecrawl MCP is available.
   - Look for tools that expose the Firecrawl capability set: `firecrawl_scrape` and `firecrawl_map`.
   - Do not assume the tool prefix is `mcp__firecrawl__`. A valid connected Firecrawl MCP may look like
     `mcp__57fe1a18-bd7d-47fc-846e-bb20a3bdb291__firecrawl_scrape`.
   - If such a tool family exists, probe it with:

```json
{
  "url": "https://example.com/",
  "formats": ["markdown"],
  "onlyMainContent": true
}
```

using the discovered `firecrawl_scrape` tool.
   - Treat success as a small, non-empty response and set `crawl_backend = "firecrawl"`.
3. If Firecrawl is not connected or its tiny probe fails, probe Crawl4AI with:

```json
{
  "url": "https://example.com/"
}
```

using `mcp__c4ai-sse__md`.

Treat success as a small, non-empty response and set `crawl_backend = "crawl4ai"`. If Firecrawl was connected but failed and Crawl4AI succeeds, show a warning banner after registration explaining that the run fell back to Crawl4AI. If neither Firecrawl nor Crawl4AI is available, stop immediately. Do not open the dashboard.
Do not emit "No Peec connection" unless you first attempted capability-based discovery via `ToolSearch`.
If no Peec project matches the blog or brand, stop immediately instead of running a GEO-only fallback.

### Stage 1 — Register the run

Call `mcp__blog-optimiser-dashboard__register_run` with:

```json
{
  "blog_url": "<blog-url>",
  "peec_project_id": "<matched-project-id>",
  "refresh_voice": true|false,
  "crawl_backend": "firecrawl"|"crawl4ai",
  "crawl_mcp_server": "<discovered Firecrawl server name or c4ai-sse>",
  "article_urls": ["<exact-article-url>", "..."] // omit when no --article-url flags were supplied
}
```

Use the returned fields as authoritative:

- `run_id`
- `dashboard_url`
- `run_dir`
- `state_path`
- `outputs_dir`
- `articles_dir`
- `evidence_dir`
- `recommendations_dir`
- `optimised_dir`
- `media_dir`
- `raw_dir`
- `gaps_dir`
- `competitors_dir`
- `peec_cache_dir`
- `run_summary_path`
- `site_key`
- `voice_baseline`
- `voice_markdown_path`
- `voice_meta_path`
- `reviewers_path`

Immediately after registration, call:

```json
{
  "run_id": "<run_id>",
  "open_browser": true
}
```

with `mcp__blog-optimiser-dashboard__open_dashboard`.

### Stage 2 — Crawl

Dispatch exactly one `Task(subagent_type="blog-crawler", ...)` and pass this exact input block in the prompt:

```text
run_id: <run_id>
blog_url: <blog_url>
max_articles: <max_articles>
article_urls: <ordered JSON array of --article-url values, or [] when not supplied>
crawl_backend: <crawl_backend from prereqs/register_run>
articles_dir: <articles_dir>
media_dir: <media_dir>
raw_dir: <raw_dir>
state_json: <state_path>

Use dashboard MCP artifact tools for all host-side reads and writes.
Never use Bash/Read/Write on /Users/... paths.
If crawl_backend is firecrawl, resolve and use the connected Firecrawl MCP tools by capability via ToolSearch.
If crawl_backend is crawl4ai, use Crawl4AI with the existing md raw -> html fallback.
Discover article URLs only from actual hrefs or canonical URLs exposed by the index/article fetches.
If article_urls is non-empty, use only those exact URLs in the supplied order. Do not discover, backfill, or substitute other posts.
Never infer slugs from titles.
Use this fetch order for article pages: Firecrawl scrape(markdown, html) when `crawl_backend=firecrawl`; otherwise Crawl4AI md raw -> html.
Call `record_crawl_discovery` after URL discovery.
Call `record_crawled_article` for every persisted article.
Call `finalize_crawl` before returning.
```

After the crawler returns, immediately verify the real host-side outputs:

1. Call `mcp__blog-optimiser-dashboard__finalize_crawl` with `run_id`.
2. If `persisted_count == 0`:
   - call `show_banner` with severity `error`
   - set `pipeline.crawl.status = "failed"`
   - set `status = "failed"`
   - stop the pipeline
3. If exact `article_urls` were supplied and `finalize_crawl.status == "failed"` because one or more requested URLs were not persisted:
   - call `show_banner` with severity `error`
   - set `pipeline.crawl.status = "failed"`
   - set `status = "failed"`
   - stop the pipeline before voice, analysis, evidence, recommendations, or draft
4. If `status == "partial"`:
   - call `show_banner` with severity `warn`
   - message: `Crawler discovered {discovered_count} articles but only {persisted_count} JSON files were written to disk. Continuing with the persisted set only.`
5. If `persisted_count > 0`:
   - trust the returned `article_slugs` as the canonical crawl set for downstream stages
   - checkpoint `state.json`

Do not continue to voice, recommendations, or draft on an empty crawl.

### Stage 3 — Voice

Check `voice_baseline.will_reuse` from `register_run`.

If `true`:

- skip the voice extractor
- keep `voice.mode = "reused"`
- keep `pipeline.voice.status = "completed"`

If `false`:

- run `voice-extractor` with this exact input block:

```text
run_id: <run_id>
site_key: <site_key>
canonical_blog_url: <canonical_blog_url>
articles_dir: <articles_dir>
site_dir: <site_dir>
voice_markdown_path: <voice_markdown_path>
voice_meta_path: <voice_meta_path>

Use dashboard MCP artifact tools for all host-side reads and writes.
Never use Bash/Read/Write on /Users/... paths.
```

- on success set `voice.mode = "generated"`
- update `voice.summary`, `voice.updated_at`, and `voice.source_run_id`

### Stage 4 — Analysis

Before recommendation batches begin, mark:

```json
{
  "pipeline": {
    "analysis": {
      "status": "running"
    }
  }
}
```

This stage represents gap analysis and competitor evidence collection performed by the recommender flow.

Dispatch `peec-gap-reader` once per article before recommendations with:

```text
run_id: <run_id>
article_slug: <article_slug>
peec_project_id: <peec_project_id>
```

Do this in batches of 3 in a single assistant message.

If a gap read succeeds, it should write its artifact through `record_peec_gap`.

If a gap read fails or the project has no usable prompt data:

- call `fail_article_stage(stage="analysis", ...)` for that article
- keep the rest of the run moving only for articles that still have admissible Peec evidence
- do not let the recommender silently fall back to `voice-rubric` mode

When the first successful recommendation artefact is written, mark `pipeline.analysis.status = "completed"`.

### Stage 5 — Evidence

Before evidence-builder batches begin, mark:

```json
{
  "pipeline": {
    "evidence": {
      "status": "running"
    }
  }
}
```

Dispatch `evidence-builder` workers in batches of 3 in a single assistant message.

Each evidence-builder receives:

- `run_id`
- `article_slug`
- `site_key`
- `peec_project_id`
- `reviewers_path`
- absolute output paths from `register_run`
- `crawl_backend`

Prompt contract additions:

```text
Use dashboard MCP artifact tools for all host-side reads and writes.
Read article JSON from articles/{article_slug}.json.
Read gap JSON from gaps/{article_slug}.json if it exists.
Read site reviewers from site/reviewers.json. It is always present as a JSON array and may be empty.
Fetch public source pages with Firecrawl when `crawl_backend=firecrawl`; otherwise use Crawl4AI.
Write evidence via `record_evidence_pack`, not `write_json_artifact`.
Never use Bash/Read/Write on /Users/... paths.
Do not invent reviewers, claims, or sources.
```

Evidence-builder sub-agents update per-article `stages.evidence` only. The main session owns top-level `pipeline.evidence` aggregate state.

After all evidence-builder sub-agents return:

1. Call `list_artifacts` with `namespace="evidence"` and `suffix=".json"`.
2. If zero evidence artefacts exist:
   - call `show_banner` with severity `error`
   - set `pipeline.evidence.status = "failed"`
   - set `status = "failed"`
   - stop the pipeline

### Stage 6 — Recommendations

Dispatch recommenders in batches of 3 in a single assistant message.

Each recommender receives:

- `run_id`
- `article_slug`
- `peec_project_id`
- `site_key`
- `mode`
- `reviewers_path`
- `voice_markdown_path`
- `voice_meta_path`
- absolute output paths from `register_run`

Prompt contract additions:

```text
Use dashboard MCP artifact tools for all host-side reads and writes.
Read article JSON from articles/{article_slug}.json.
Read evidence JSON from evidence/{article_slug}.json.
Read site reviewers from site/reviewers.json. It is always present as a JSON array and may be empty.
Read voice baseline from site/voice.json first. Only read site/brand-voice.md if site/voice.json is missing or malformed.
Read the GEO contract from references/geo-article-contract.md via read_bundle_text.
Write recommendations via `record_recommendations`, not `write_json_artifact`.
Never use Bash/Read/Write on /Users/... paths.
Treat prompt matching as the primary Peec evidence path. Topics are optional grouping signals.
```

Set `mode = "peec-enriched"` only when `gaps/{article_slug}.json` exists and its admissibility is positive. Otherwise block the article instead of drafting a weak fallback.

Recommender sub-agents update per-article `stages.recommendations` only. The main session owns top-level `pipeline.analysis` and `pipeline.recommendations` aggregate state.

After all recommender sub-agents return:

1. Call `list_artifacts` with `namespace="recommendations"` and `suffix=".json"`.
2. If zero recommendation artefacts exist:
   - call `show_banner` with severity `error`
   - set `pipeline.recommendations.status = "failed"`
   - set `status = "failed"`
   - stop the pipeline

### Stage 7 — Draft

Dispatch generators in batches of 3 in a single assistant message.

Each generator receives:

- `run_id`
- `article_slug`
- `peec_project_id`
- `site_key`
- `reviewers_path`
- `voice_markdown_path`
- `voice_meta_path`
- absolute output paths from `register_run`

Prompt contract additions:

```text
Use dashboard MCP artifact tools for all host-side reads and writes.
Read article JSON from articles/{article_slug}.json.
Use articles/{article_slug}.json.body_md as the rewrite spine. Keep the original article topic, product context, core claims, and search intent intact.
Read evidence JSON from evidence/{article_slug}.json.
Read recommendation JSON from recommendations/{article_slug}.json.
Read site reviewers from site/reviewers.json. It is always present as a JSON array and may be empty.
Read voice baseline from site/voice.json first. Only read site/brand-voice.md if site/voice.json is missing or malformed.
Read the GEO contract from references/geo-article-contract.md via read_bundle_text.
Write draft artefacts through `record_draft_package`.
Apply recommendations as edits to the article, never as visible recommendations, rationale, implementation notes, or process commentary.
Put SEO rationale, off-page actions, and implementation notes only in `diff_markdown` or `handoff_markdown`.
Keep off-page-only recommendations out of visible HTML and mark their `rec_implementation_map` entries as `{ "implemented": false, "reason": "non-applicable" }`.
If the article cannot honestly support a compliant rewrite, call `fail_article_stage(stage="draft", ...)`.
Never use Bash/Read/Write on /Users/... paths.
The draft is complete only when the manifest quality gate passes.
```

Generator sub-agents update per-article `stages.draft` only. The main session owns top-level `pipeline.draft` aggregate state.

## Finalization

After draft work finishes, call `finalize_run_report`.

- The dashboard is a report surface, not an orchestration surface.
- `run-summary.md` must be generated from disk truth after validation completes.
- Use `draft-ready` vs `blocked` language in user-facing summaries.
- Deprecated `set_gate` / `get_gates` tools should not be part of the main flow.

## Resume mode

For `--resume {run_id}`:

1. Read `{run_dir}/state.json`.
2. Set `session.mode = "resumed"`.
3. Open the dashboard for that exact `run_id`.
4. Resume only incomplete stages:
   - if `pipeline.crawl.status == "completed"`, do not re-crawl
   - if `voice.mode == "reused"` or `pipeline.voice.status == "completed"`, do not regenerate voice unless `--refresh-voice`
   - skip any article whose `stages.evidence.status == "completed"`
   - skip any article whose `stages.recommendations.status == "completed"`
   - skip any article whose `stages.draft.quality_gate == "passed"`

## Final state expectations

By the end of a successful run, `state.json` should contain:

- `run_id`
- `created_at`
- `status`
- `blog_url`
- `canonical_blog_url`
- `site_key`
- `dashboard_url`
- `peec_project`
- `voice`
- `voice_baseline`
- `pipeline`
- `articles`
- `outputs`

Do not invent additional orchestration state outside this file unless it is written to the run directory.
