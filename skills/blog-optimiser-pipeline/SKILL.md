---
name: blog-optimiser-pipeline
description: Canonical orchestration playbook for the AI Search Blog Optimiser pipeline. Runs in the main session, uses disk-first state, and only opens the dashboard after a fresh run has been registered.
version: 0.3.2
---

# Blog Optimiser Pipeline (v0.3.2)

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

## Pipeline stages

1. `prereqs`
2. `crawl`
3. `voice`
4. `analysis`
5. `recommendations`
6. `draft`

The run's `state.json` is the source of truth. Update it on disk after every stage transition.

## Fresh run flow

### Stage 0 — Prereqs

Run prerequisites before creating or opening anything:

1. Probe Peec with `mcp__peec__list_projects`.
2. Probe Crawl4AI with:

```json
{
  "url": "https://example.com/"
}
```

using `mcp__c4ai-sse__md`.

Treat success as a small, non-empty response. If Crawl4AI fails, stop immediately. Do not open the dashboard.

### Stage 1 — Register the run

Call `mcp__blog-optimiser-dashboard__register_run` with:

```json
{
  "blog_url": "<blog-url>",
  "peec_project_id": "<matched-project-or-null>",
  "refresh_voice": true|false
}
```

Use the returned fields as authoritative:

- `run_id`
- `dashboard_url`
- `run_dir`
- `state_path`
- `outputs_dir`
- `articles_dir`
- `recommendations_dir`
- `optimised_dir`
- `media_dir`
- `raw_dir`
- `gaps_dir`
- `competitors_dir`
- `peec_cache_dir`
- `decisions_path`
- `gates_path`
- `run_summary_path`
- `site_key`
- `voice_baseline`
- `voice_markdown_path`
- `voice_meta_path`

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
articles_dir: <articles_dir>
media_dir: <media_dir>
raw_dir: <raw_dir>
state_json: <state_path>

Use dashboard MCP artifact tools for all host-side reads and writes.
Never use Bash/Read/Write on /Users/... paths.
Discover article URLs only from actual hrefs or canonical URLs exposed by the index/article fetches.
Never infer slugs from titles.
Use this fetch order for article pages: md raw -> html.
```

After the crawler returns, immediately verify the real host-side outputs:

1. Call `mcp__blog-optimiser-dashboard__list_artifacts` with `namespace="articles"` and `suffix=".json"`.
2. If zero article JSON files exist:
   - call `show_banner` with severity `error`
   - set `pipeline.crawl.status = "failed"`
   - set `status = "failed"`
   - stop the pipeline
3. If one or more article JSON files exist:
   - set `pipeline.crawl.status = "completed"`
   - checkpoint `state.json`

Do not continue to voice, recommendations, or draft on an empty crawl.

Unless `--no-gates` is set, stop here for review before Stage 3:

1. Call `set_gate` with:

```json
{
  "run_id": "<run_id>",
  "gate": "crawl_gate",
  "status": "pending",
  "prompt": "Review the crawl output before voice extraction and Peec analysis.",
  "timeout_seconds": 300
}
```

2. Poll `get_gates` every 10 seconds.
3. Do not continue until `crawl_gate.status == "resolved"`.

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

Unless `--no-gates` is set, stop here for review before Stage 4:

1. Call `set_gate` with:

```json
{
  "run_id": "<run_id>",
  "gate": "voice_gate",
  "status": "pending",
  "prompt": "Review the extracted voice baseline before recommendations are generated.",
  "timeout_seconds": 300
}
```

2. Poll `get_gates` every 10 seconds.
3. Do not continue until `voice_gate.status == "resolved"`.

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

If `peec_project_id` is present, dispatch `peec-gap-reader` once per article before recommendations with:

```text
run_id: <run_id>
article_slug: <article_slug>
peec_project_id: <peec_project_id>
```

Do this in batches of 3 in a single assistant message.

If a gap read succeeds, it should write `gaps/{article_slug}.json`.

If a gap read fails or the project has no usable prompt/topic data:

- keep the run moving
- show a warning banner only if every article failed gap-read
- let the recommender fall back to `voice-rubric` mode

When the first successful recommendation artefact is written, mark `pipeline.analysis.status = "completed"`.

### Stage 5 — Recommendations

Dispatch recommenders in batches of 3 in a single assistant message.

Each recommender receives:

- `run_id`
- `article_slug`
- `peec_project_id`
- `site_key`
- `mode`
- `voice_markdown_path`
- `voice_meta_path`
- absolute output paths from `register_run`

Prompt contract additions:

```text
Use dashboard MCP artifact tools for all host-side reads and writes.
Read article JSON from articles/{article_slug}.json.
Read voice baseline from site/voice.json first. Only read site/brand-voice.md if site/voice.json is missing or malformed.
Write recommendation JSON to recommendations/{article_slug}.json.
Never use Bash/Read/Write on /Users/... paths.
```

Set `mode = "peec-enriched"` only when `gaps/{article_slug}.json` exists. Otherwise set `mode = "voice-rubric"`.

Recommender sub-agents update per-article `stages.recommendations` only. The main session owns top-level `pipeline.analysis` and `pipeline.recommendations` aggregate state.

After all recommender sub-agents return:

1. Call `list_artifacts` with `namespace="recommendations"` and `suffix=".json"`.
2. If zero recommendation artefacts exist:
   - call `show_banner` with severity `error`
   - set `pipeline.recommendations.status = "failed"`
   - set `status = "failed"`
   - stop the pipeline

Unless `--no-gates` is set, stop here for review before Stage 6:

1. Call `set_gate` with:

```json
{
  "run_id": "<run_id>",
  "gate": "recommend_gate",
  "status": "pending",
  "prompt": "Review the recommendation set before draft generation.",
  "timeout_seconds": 300
}
```

2. Poll `get_gates` every 10 seconds.
3. Do not continue until `recommend_gate.status == "resolved"`.

### Stage 6 — Draft

Dispatch generators in batches of 3 in a single assistant message.

Each generator receives:

- `run_id`
- `article_slug`
- `peec_project_id`
- `site_key`
- `voice_markdown_path`
- `voice_meta_path`
- absolute output paths from `register_run`

Prompt contract additions:

```text
Use dashboard MCP artifact tools for all host-side reads and writes.
Read article JSON from articles/{article_slug}.json.
Read recommendation JSON from recommendations/{article_slug}.json.
Read decisions from run/decisions.json.
Read voice baseline from site/voice.json first. Only read site/brand-voice.md if site/voice.json is missing or malformed.
Write draft artefacts under optimised/{article_slug}.*.
Never use Bash/Read/Write on /Users/... paths.
```

Generator sub-agents update per-article `stages.draft` only. The main session owns top-level `pipeline.draft` aggregate state.

## Gates

Unless `--no-gates` is set, use gates after:

- crawl
- voice
- recommendations

The dashboard reads `gates.json` from disk. When opening a gate, write it with a 5-minute timeout. Poll `get_gates` every 10 seconds and trust the returned status as authoritative. Never infer timeout from wall-clock time in the conversation. The server resolves expired gates and records `timeout-auto-proceed` itself.

## Resume mode

For `--resume {run_id}`:

1. Read `{run_dir}/state.json`.
2. Set `session.mode = "resumed"`.
3. Open the dashboard for that exact `run_id`.
4. Resume only incomplete stages:
   - if `pipeline.crawl.status == "completed"`, do not re-crawl
   - if `voice.mode == "reused"` or `pipeline.voice.status == "completed"`, do not regenerate voice unless `--refresh-voice`
   - skip any article whose `stages.recommendations.status == "completed"`
   - skip any article whose `stages.draft.status == "completed"`

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
