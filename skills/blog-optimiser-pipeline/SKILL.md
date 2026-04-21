---
name: blog-optimiser-pipeline
description: Canonical orchestration playbook for the AI Search Blog Optimiser pipeline. Runs IN THE MAIN SESSION (not via a sub-agent). Defines the 7-stage flow, disk-first state writes, gate mechanism for human-in-the-loop, parallelism pattern, and the embedded 15-point GEO + 40-point audit rubric for the recommender to use when the user's external skill banks aren't available.
version: 0.2.0
---

# Blog Optimiser Pipeline (v0.2)

The canonical playbook executed BY THE MAIN SESSION when `/blog-optimiser` runs. This replaces the v0.1 pattern where a `blog-optimiser-orchestrator` sub-agent drove the flow — that handoff is removed.

## Why main-session orchestration

- **Browser opens only fire from the main session.** `mcp__blog-optimiser-dashboard__open_dashboard` produces a desktop-level side effect (the browser tab). When called from a sub-agent, Cowork silently drops the side effect.
- **Parallelism is cleaner.** Multiple `Task` calls in a single main-session message run concurrently. A handoff to a sub-agent adds indirection and risks mid-run context compaction.
- **Context stays lean.** The main session never reads article bodies; it passes paths + receives ≤300-token summaries. Compaction triggers that broke v0.1.1 don't fire.

## The 7 stages

```
0. Prereq validation             → open dashboard, check Peec + Crawl4AI MCPs
1. Peec project resolution       → list_projects, auto-match domain, register_run
2. Blog crawl                    → Task(blog-crawler) — serial, writes articles/*.json
   GATE                          → user reviews crawled list in dashboard, clicks Continue
3. Voice extraction              → Task(voice-extractor) — one-shot
   GATE                          → user reviews voice summary, clicks Continue
4. Recommendations (parallel × 3) → Task(recommender) fan-out in batches of 3
   GATE                          → user reviews accept/reject toggles, clicks Continue
5. Article generation (parallel × 3) → Task(generator) fan-out in batches of 3
6. Finalise                      → write run-summary.md, final state update
```

`--no-gates` skips the gate polling. `--resume {run_id}` picks up from the last-completed stage per article.

## Stage 0 — Prereqs + dashboard

**As the main session**, execute in this exact order:

1. Call `mcp__blog-optimiser-dashboard__open_dashboard` with `{open_browser: true}`. Capture the returned URL. This launches the dashboard HTTP server (if not running) and opens the user's default browser.

2. Call `mcp__blog-optimiser-dashboard__get_paths`. Capture all absolute paths you'll pass to sub-agents (`data_dir`, `brands_dir`, `runs_dir`, and — once the run is registered — `run_dir`, `articles_dir`, `recommendations_dir`, `optimised_dir`, `media_dir`, `raw_dir`, `gaps_dir`, `competitors_dir`, `peec_cache_dir`, `state_json`, `decisions_json`).

3. Probe Peec: call `mcp__peec__list_projects` with empty args. If it fails, note Peec unavailable and set `mode=generic`.

4. Probe Crawl4AI: call `mcp__c4ai-sse__ask` with `{"query":"ping","url":"https://example.com"}`. If it fails, **hard-fail** with a `show_banner` error and stop. There's no fallback for crawling.

## Stage 1 — Peec project resolution

If Peec is available:

1. Parse domain from the blog URL (e.g., `granola.ai` from `https://www.granola.ai/blog`).
2. The `list_projects` response you captured in stage 0 is your project list. For each project, check if its tracked brand domain matches.
3. **One match** → auto-select, `role=own`, proceed silently.
4. **Multiple or none** → write a pending gate to `gates.json` asking the user to pick a project via the dashboard. Poll the gate.
5. Call `mcp__blog-optimiser-dashboard__register_run` with `{blog_url, brand_name, peec_project_id, role}`. It creates `runs/{run_id}/` with all subdirs and an initial `state.json`.
6. Use the returned paths for the rest of the pipeline.

If Peec is unavailable, register the run with `peec_project_id=generic-{domain-slug}` and `role=unknown`. Push an info banner explaining generic mode.

## Stage 2 — Blog crawl

Dispatch the crawler:

```
Task(
  subagent_type="blog-crawler",
  prompt="""
  run_id: {run_id}
  blog_url: {blog_url}
  max_articles: {max_articles}
  articles_dir: {articles_dir}
  media_dir: {media_dir}
  raw_dir: {raw_dir}
  state_json: {state_json}
  """
)
```

Wait for completion. The crawler writes `{articles_dir}/*.json` + downloaded images and returns a summary like `17 articles captured: [slugs...]; 1 partial (timeout on /blog/X)`.

**After completion, YOU (main session) update state.json directly** — don't rely on the crawler's state pushes alone:

1. Read current `state_json` via Read tool.
2. Merge: `pipeline.crawl.status="completed"`, `pipeline.crawl.count=N`, articles[] populated.
3. Write back atomically (Write tool, overwriting is fine since the file is yours).
4. Call `mcp__blog-optimiser-dashboard__update_state` with the same fragment as a best-effort browser wake-up. If it fails, the browser's next 1.5s poll reads disk and gets the truth.

**Crawl gate.** Unless `--no-gates`: write to `{run_dir}/gates.json`:

```json
{
  "crawl_gate": {
    "status": "pending",
    "pending_since": "ISO-8601",
    "prompt": "Review the crawled articles in the dashboard. Deselect any you want to skip, then click Continue.",
    "resolved_at": null,
    "user_action": null
  }
}
```

Poll `gates.json` every 10 seconds for up to 5 minutes. The dashboard's Continue button writes `resolved_at` and `user_action="proceed"`. On timeout, auto-proceed and log it in state.json.

## Stage 3 — Voice extraction

```
Task(
  subagent_type="voice-extractor",
  prompt="""
  run_id: {run_id}
  peec_project_id: {peec_project_id}
  role: {role}
  articles_dir: {articles_dir}
  brands_dir: {brands_dir}
  """
)
```

Returns a ≤150-token summary + writes `{brands_dir}/{peec_project_id}/brand-voice.md` (or the competitor-view path).

Update state.json with `pipeline.voice.status="completed"` + the one-sentence summary.

**Voice gate** unless `--no-gates`. Same pattern as crawl gate.

## Stage 4 — Recommendations (parallel × 3)

For each article, dispatch a recommender. **Dispatch in batches of 3 IN A SINGLE MESSAGE** for true parallelism:

```
(single assistant message, three Task calls)
Task(subagent_type="recommender", prompt="...article-1...")
Task(subagent_type="recommender", prompt="...article-2...")
Task(subagent_type="recommender", prompt="...article-3...")
```

Each recommender input includes: `run_id, article_slug, peec_project_id, role, mode, articles_dir, recommendations_dir, gaps_dir, competitors_dir, peec_cache_dir, brands_dir`.

When all 3 return, update state.json with `pipeline.recommend.completed_articles += 3`, merge per-article stage updates, write disk + push MCP. Then dispatch the next batch.

If any recommender fails: retry once. Second failure: mark that article's recommend stage `status=failed`, continue.

When all articles are recommended: state.json `pipeline.recommend.status="completed"`.

**Recommend gate** unless `--no-gates`. Prompt: "Review the recommendations for each article in the dashboard. Accept/reject individual recommendations — anything you don't explicitly reject will be applied. Click Continue when ready."

## Stage 5 — Article generation (parallel × 3)

Same batching pattern. Generator input: `run_id, article_slug, peec_project_id, articles_dir, recommendations_dir, optimised_dir, media_dir, brands_dir, decisions_json`.

The generator re-reads `decisions_json` inside its run to respect any user rejections.

After each batch, update state.json. When all articles generated: state.json `pipeline.generate.status="completed"`.

## Stage 6 — Finalise

1. Write `{run_dir}/run-summary.md` — aggregate table of before/after scores, approval status, path to each article's handoff doc.
2. Update state.json with `banners[]` entry: info severity, message "Run complete. Review approved articles in the dashboard or in {optimised_dir}."
3. Return concise summary to the user (≤500 tokens): counts, dashboard URL, run path.

## Gate mechanism details

### Writing a gate

```python
# Conceptual — do this via Write tool
{
  "crawl_gate": { "status": "pending", "pending_since": "...", "prompt": "..." },
  "voice_gate": { "status": "not-pending" },
  "recommend_gate": { "status": "not-pending" }
}
```

### Polling a gate

Use a Bash loop. Check once every 10s. Timeout at 5 minutes.

```bash
for i in $(seq 30); do
  status=$(python3 -c "import json; print(json.load(open('{gates_json}')).get('crawl_gate',{}).get('status','?'))")
  if [ "$status" = "resolved" ]; then break; fi
  sleep 10
done
```

If the loop exits without `resolved`, the gate timed out — auto-proceed and note in state.json.

### Dashboard Continue button

The dashboard's `POST /api/runs/{run_id}/gate` with `{"gate": "crawl_gate", "action": "proceed"}` writes `resolved_at` and `user_action="proceed"` to gates.json.

## Resume mode

`--resume {run_id}`:
1. Read `{run_dir}/state.json`. For each stage, check status.
2. If crawl is `completed`, skip stage 2. Otherwise resume with the list of articles that don't have `stages.crawl.status="completed"`.
3. Same logic for voice, recommend, generate.
4. Never redo completed work.

## Embedded 15-point GEO checklist

(Used by the recommender when the user's external skill banks aren't installed.)

1. **Trust block at top** — 30–60 word direct answer, followed by 1–2 atomic paragraphs with cited sources + visible last-updated date + named author.
2. **Atomic paragraphs** — no paragraph > ~150 words or ~3 sentences for primary claims.
3. **Question-based H2/H3** — every heading mirrors an actual user prompt.
4. **Tables for structured data** — pricing, feature matrices, specs in `<table>`, not prose.
5. **Concrete numbers in titles/H2s** — "7 X for Y", not "Several X to consider".
6. **Current-year modifier** — 2026 in title, slug, at least one H2.
7. **Target 1,500–2,500 words** — Profound benchmark.
8. **Specialized schema** — FAQPage, HowTo, Product, Person, Organization over generic Article.
9. **Cite primary sources inline** — `.gov`, `.edu`, analyst firms as "According to [NIH, 2025], …".
10. **Named, credentialed author + Person schema** — avoid "Staff" bylines.
11. **Original data or framework** — at least one proprietary stat, named framework, or first-hand case.
12. **Listicle / comparison / how-to format bias** — but NEVER rank your own product #1 in a self-promo listicle.
13. **Shippable-noun presence** — concrete buyable nouns for commerce pages.
14. **Multimodal enrichment** — FAQs, videos, images, specs lift citation rates.
15. **Chunk-extractability self-test** — every H2 section answers its implied question standalone.

## Embedded 40-point audit rubric

Scored binary pass/fail. Total 40. Minimum passing 32.

### Retrieval foundation (6 pts)
- [ ] Robots.txt allows major AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
- [ ] Canonical URL set correctly
- [ ] Meta description present, 120–155 chars
- [ ] Alt text on ≥80% of images
- [ ] Updated-at date within last 12 months
- [ ] Semantic HTML (proper H1→H6 hierarchy, `<article>`/`<section>`)

### Chunk extractability (8 pts)
- [ ] Trust block in first 60 words
- [ ] Atomic paragraph ratio ≥ 0.6
- [ ] H2s phrased as user prompts (question or imperative)
- [ ] ≥1 table for structured data where relevant
- [ ] ≥1 concrete number/stat in title or an H2
- [ ] Every H2 section extractable standalone
- [ ] Current-year modifier present
- [ ] Word count in 1,200–3,000 band

### Schema & entities (6 pts)
- [ ] Article or type-specific schema present
- [ ] FAQPage schema (if ≥3 Q&A)
- [ ] Person schema for author
- [ ] Organization schema
- [ ] BreadcrumbList schema
- [ ] HowTo schema (if how-to type)

### Authority & trust (6 pts)
- [ ] Named author (not "Staff")
- [ ] Author role / credential visible on page
- [ ] Author photo
- [ ] Author LinkedIn or profile link
- [ ] Publish date AND updated date visible
- [ ] Person schema linked to author byline

### Citation-worthiness (6 pts)
- [ ] ≥1 inline `.gov`/`.edu`/analyst/named-study citation
- [ ] Proprietary stat / framework / case with numbers
- [ ] ≥3 named entities (products, companies, people)
- [ ] ≥3 internal cross-links
- [ ] Not a self-promo listicle (own product not at #1/#2)
- [ ] External citation register ≥ median for category

### Article-type-specific (8 pts)
See per-type presets: listicle, how-to, comparison, glossary, case-study, pillar, opinion, product. Each swaps 8 points in.

## Per-engine citation benchmarks

- **ChatGPT**: target ≥ 2.0 citation rate (average > 2.5)
- **Google AI Mode**: target 1.1–1.5 (average > 1.2)
- **Perplexity**: target 1.5–2.0 (average 0.5 — don't over-index on Perplexity)

Metrics `visibility`, `share_of_voice`, `retrieved_percentage` are 0–1 ratios (×100 for display). `sentiment` is 0–100. `position` is rank (lower = better). `retrieval_rate` and `citation_rate` are averages — **never** ×100.

## Strategic non-goals

Agents must not:
- Generate mass AI content (100% of pages removed under Google's 2024 spam policy had AI content)
- Optimise for a single engine (89% of cited domains diverge between ChatGPT and Perplexity)
- Publish self-promo listicles ranking own brand #1
- Auto-push to a CMS
