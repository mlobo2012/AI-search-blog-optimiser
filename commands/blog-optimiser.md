---
description: GEO-optimise a blog. Crawls every article, extracts brand voice, reads your Peec gaps, benchmarks against AI-cited competitors, rewrites articles with evidence.
argument-hint: "[blog-url] [--resume {run-id}] [--max-articles N]"
allowed-tools:
  - Task
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - mcp__peec__*
  - mcp__c4ai-sse__*
  - mcp__blog-optimiser-dashboard__*
---

# AI Search Blog Optimiser

Run the full GEO optimisation pipeline on a blog. Works on any brand that the user has set up in Peec AI — auto-matches the blog URL to one of their Peec projects, falls back to generic mode if Peec isn't available.

## Arguments

`$ARGUMENTS` contains the user-supplied arguments. Parse them as follows:

- **No arguments** → first-run flow: open the dashboard in welcome mode, list Peec projects via `mcp__peec__list_projects`, let the user pick a brand + blog URL, then run.
- **One URL argument** → treat as the blog index URL. Run the full pipeline.
- **`--resume {run-id}`** → resume an incomplete run from `runs/{run-id}/state.json`.
- **`--max-articles N`** → override the default cap of 20 articles for this run.

## What to do

Invoke the **blog-optimiser-pipeline** skill which orchestrates the full flow. The skill is the playbook — follow it exactly.

Hand off to the `orchestrator` agent with the parsed arguments. The orchestrator will:
1. Validate prerequisites (Peec MCP, Crawl4AI MCP, python3 dashboard).
2. Start the dashboard server if not already running, open the user's browser.
3. Resolve the Peec project (auto-match domain → user-pick → generic-mode fallback).
4. Dispatch sub-agents in the order: blog-crawler → voice-extractor → recommender (parallel × N articles) → generator (parallel × N articles).
5. Write a run summary and surface completion in the dashboard.

## Guardrails

- Never ship an optimised article with audit score < 32/40. Halt that article, surface the failing dimensions, let the user iterate.
- Every recommendation MUST include the full evidence trail: Peec gap + Schmidt rule + competitor example + Step 1 field provenance. Drop or demote any rec without all four.
- Never auto-push to a CMS. All outputs go to `~/.ai-search-blog-optimiser/runs/{run_id}/optimised/` on disk for human review.
- Never silently fail. Every edge case surfaces a clear, actionable banner in the dashboard.

## Writable paths (CRITICAL)

The plugin install dir (`${CLAUDE_PLUGIN_ROOT}`) is READ-ONLY in sub-agent sandboxes. All writes go to the user's home directory at `~/.ai-search-blog-optimiser/`:
- `~/.ai-search-blog-optimiser/runs/{run_id}/` — per-run state, articles, recommendations, optimised outputs
- `~/.ai-search-blog-optimiser/brands/{peec_project_id}/` — persistent brand voice artefacts

Sub-agents must NEVER write under the plugin root. The orchestrator resolves paths via `mcp__blog-optimiser-dashboard__get_paths` at stage start and passes absolute paths to every sub-agent invocation.
