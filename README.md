# AI Search Blog Optimiser

## What problem does this solve?

AI Search Blog Optimiser turns an existing blog into AI-search-ready content. It is a Claude Cowork desktop plugin for content teams that want their articles to show up when people ask ChatGPT, Perplexity, Google AI Overview, and similar answer engines about their category.

Most blog posts were written for readers and Google. AI answer engines need something stricter:

- clear answers to real user prompts
- named evidence and sources
- author and reviewer trust signals
- structured sections, FAQ, schema, and internal links
- language that matches the prompts where the brand is currently missing
- proof that every recommendation made it into the final draft

This workflow gives content teams a repeatable way to move from "we are invisible in ChatGPT or Perplexity for these prompts" to "this article now contains the evidence, structure, and language needed to compete."

## How does it work?

Run one command with a blog URL. The plugin crawls your blog, reads your live Peec AI visibility gaps, finds the sources and competitors that answer engines already trust, then rewrites each article with evidence-backed recommendations. If the article cannot be improved honestly, it blocks the draft and tells you why.

```text
/blog-optimiser https://your-blog.com/blog [--refresh-voice] [--resume {run_id}] [--max-articles N]
```

The plugin then runs a seven-stage workflow:

1. **Prereqs** - confirms Peec MCP and Crawl4AI are available before opening anything.
2. **Crawl** - discovers real article URLs from the blog index and saves article captures.
3. **Voice** - builds or reuses a site-level brand voice baseline.
4. **Analysis** - matches each article to Peec prompts, topics, source gaps, and engine performance.
5. **Evidence** - gathers the claims, citations, reviewers, and competitor examples the rewrite is allowed to use.
6. **Recommendations** - creates a compact rewrite blueprint from Peec data, deterministic lint results, and competitor evidence.
7. **Draft** - writes markdown, HTML, schema, diff, handoff notes, and a validator manifest.

The dashboard opens after a run is registered and stays a report surface. Claude Cowork remains the control surface.

## What you get

For every article, the run writes:

- the original article capture
- a Peec gap artifact with matched prompts, engine visibility, source gaps, sentiment, and citation patterns
- an evidence pack with allowed claims, source URLs, reviewer candidates, and internal link candidates
- a recommendation artifact with category, brand, and competition lenses
- an optimized markdown article
- rendered HTML with embedded JSON-LD
- standalone schema JSON
- a diff against the source article
- a handoff document for editors
- a manifest showing which recommendations were implemented and whether the quality gate passed

At the end, `run-summary.md` reports how many articles were draft-ready and how many were blocked.

## Example runs

Recent verification runs used `https://www.granola.ai/blog`, whose blog index is simple, current, and product-led. That made it a useful test case for the optimiser: the source articles were real launch and funding posts, not synthetic fixtures.

### Granola Chat article

The run matched `Granola Chat just got smarter` to 3 Peec prompts. The recommender found that Granola had roughly 4.5% ChatGPT visibility, 0% Perplexity visibility, and stronger Google AI Overview presence for the matched prompt set.

The workflow turned that into engine-specific recommendations: question-style H2s, FAQ coverage, named product proof, reviewer trust, and off-page actions for the editorial listicles answer engines were already citing. The final manifest implemented 17 recommendations, added FAQ schema, embedded JSON-LD, used 3 inline evidence references, and passed the quality gate.

### Series C article

The run matched `Granola raises $125M to put your company's context to work` to 7 Peec prompts. It found a sharper gap: ChatGPT sentiment floor at 46, Perplexity dark on most matched prompts, and editorial roundups such as TechTarget and TrendHarvest acting as citation gatekeepers.

The optimiser rebuilt the article around the prompts Granola needed to win: team knowledge, CRM workflows, no-bot privacy, meeting use cases, and enterprise trust. The final manifest reached an `audit_after` score of 34/40, implemented 17 recommendations, added 5 inline evidence references, generated FAQ schema that matched visible FAQ questions, and passed the quality gate.

## Current capabilities

### Peec-first gap analysis

The workflow requires Peec for fresh runs. It discovers the connected Peec MCP by capability, not by server name, so Cowork installations with UUID-style MCP prefixes still work.

For each article it prefers prompt-level evidence:

- matched prompts and topics
- brand visibility per engine
- share of voice, position, sentiment, and citation score per engine
- domains and URLs answer engines cite when competitors appear and your brand does not
- recent AI responses used as gap excerpts
- Peec action opportunities for owned, editorial, reference, and UGC surfaces

If no direct prompt match exists, the gap reader falls back to topic-level signals instead of producing a generic rewrite.

### Recommendation engine

The v0.6 recommendation engine produces more than a checklist. It builds:

- `category_lens` - where this article sits in the topic cluster and which source formats dominate
- `brand_lens` - which engines are strong, weak, dark, or low-sentiment
- `competition_lens` - which competitors, publishers, corporate sites, UGC sources, or reference domains shape the answer
- `engine_gap_strategy` - per-engine levers for ChatGPT, Perplexity, and Google AI Overview
- `primary_gaps` - the missing prompt language and evidence
- `off_page_actions` - actions outside the article when Peec shows a citation-surface gap
- `synthesis_claims` - grouped claims that address multiple prompts at once

It emits 3-8 LLM-source recommendations in Peec modes, plus deterministic rubric items and off-page actions where relevant.

### Deterministic lint and quality gate

The dashboard runtime owns the hard checks. It can block an article even if the generator sounds confident.

The validator checks:

- visible TL;DR
- full-name trust block with role and date signals
- question-format headings when the recommendation set requires them
- atomic paragraphs and chunk-complete sections
- inline evidence
- semantic HTML
- differentiation
- JSON-LD embedded in the HTML
- FAQ visibility and FAQ schema alignment
- internal links, including subdomains of the canonical site
- recommendation implementation coverage
- scope drift
- minimum `audit_after` score of 32/40 when scoring is available

The manifest cross-checks every critical recommendation against `rec_implementation_map`. A brilliant recommendation that never appears in the draft is a failed article, not a success.

### Evidence and trust handling

The workflow keeps trust explicit:

- source authors pass when they have a credible full name and role
- first-name authors can pass only when a substantive role is present
- site-level reviewers can be promoted when the source byline is weak
- reviewer provenance is preserved in `author_validation`
- the visible trust block and validator state must agree
- articles can block when there are not enough external sources

This is why the system sometimes returns a blocked article. A blocked article is useful. It tells the editor what proof is missing instead of shipping made-up confidence.

### Dashboard and storage

The dashboard is a local report view with run history and per-article status. It does not own the orchestration.

Writable root selection:

- `CLAUDE_PLUGIN_DATA` when Cowork provides it
- platform fallback roots otherwise
- `BLOG_OPTIMISER_DATA_ROOT` for tests and local debugging

Default fallback roots:

- macOS: `~/Library/Application Support/ai-search-blog-optimiser/v3`
- Linux: `~/.local/share/ai-search-blog-optimiser/v3`
- Windows: `%APPDATA%\ai-search-blog-optimiser\v3`

When `CLAUDE_PLUGIN_DATA` is used, the runtime imports legacy default-root data once if the new plugin data directory is empty. Set `BLOG_OPTIMISER_SKIP_LEGACY_IMPORT=1` to disable that import during tests or debugging.

Layout:

```text
v3/
  runs/{run_id}/
    state.json
    gates.json
    run-summary.md
    outputs/
      articles/
      evidence/
      recommendations/
      optimised/
      media/
      raw/
      gaps/
      competitors/
      peec-cache/
      rubric/
  sites/{site_key}/
    brand-voice.md
    voice.json
    reviewers.json
  dashboard.lock
```

## Runtime rules

- The main Claude session is the orchestrator.
- Sub-agents are leaf workers for crawl, voice, evidence, recommendations, and draft generation.
- `register_run` must happen before `open_dashboard`.
- `register_run` requires `peec_project_id`.
- `open_dashboard` requires a concrete `run_id`.
- `get_paths` is deprecated for normal orchestration.
- `state.json` is the source of truth.
- Same-site voice reuse is automatic unless `--refresh-voice` is set.
- Core writes use typed dashboard MCP tools so artifact persistence and state updates happen together.
- `write_json_artifact` accepts raw JSON objects or arrays; the runtime normalizes accidentally stringified JSON for backward compatibility.
- Peec failures block the relevant run or article instead of silently downgrading to a generic GEO rewrite.

## Embedded dashboard MCP tools

Core orchestration:

- `register_run`
- `open_dashboard`
- `get_dashboard_url`
- `update_state`
- `list_runs`
- `show_banner`

Run artifacts:

- `record_crawl_discovery`
- `record_crawled_article`
- `finalize_crawl`
- `record_voice_baseline`
- `record_peec_gap`
- `record_competitor_snapshot`
- `record_evidence_pack`
- `rubric_lint`
- `record_recommendations`
- `record_draft_package`
- `fail_article_stage`
- `finalize_run_report`

Validation and review:

- `validate_article`
- `validate_run`
- `set_gate`
- `get_gates`

Artifact helpers:

- `get_artifact_path`
- `list_artifacts`
- `read_text_artifact`
- `read_json_artifact`
- `read_bundle_text`
- `write_text_artifact`
- `write_json_artifact`
- `download_media_asset`

## Development

Run the regression suite:

```bash
python3 tests/dashboard_e2e_test.py
```

Validate the server module:

```bash
python3 -m py_compile dashboard/server.py
```

Useful files:

- `commands/blog-optimiser.md` - slash-command entrypoint
- `skills/blog-optimiser-pipeline/SKILL.md` - canonical orchestration playbook
- `skills/peec-gap-read/SKILL.md` - Peec gap-read recipe
- `references/geo-article-contract.md` - article quality contract
- `dashboard/server.py` - local dashboard MCP runtime
- `dashboard/quality_gate.py` - draft validator
- `dashboard/rubric_lint.py` - deterministic GEO lint
- `agents/*.md` - worker contracts
