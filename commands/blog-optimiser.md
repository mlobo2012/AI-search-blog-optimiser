---
description: GEO-optimise a blog. Runs in the main session — never via an orchestrator sub-agent.
argument-hint: "[blog-url] [--resume {run-id}] [--refresh-voice] [--max-articles N] [--article-url URL ...]"
allowed-tools: "*"
---

# AI Search Blog Optimiser — Slash Command

You are the orchestrator for the AI Heroes Blog Optimiser pipeline. The orchestration runs directly in the main session. Do not hand off to an orchestrator sub-agent.

## Load the canonical playbook

Read `skills/blog-optimiser-pipeline/SKILL.md` and follow it exactly. That skill is the source of truth for ordering, state writes, browser opening, and resume behavior.

## Argument parsing

`$ARGUMENTS` contains the user-supplied arguments. Parse:

- Positional URL → the blog index URL for a fresh run
- `--resume {run-id}` → resume an existing run
- `--refresh-voice` → force a new voice baseline even if the same site already has one
- `--max-articles N` → override the default article cap of 20
- `--article-url <url>` → exact article input; may be repeated. When present, crawl only these URLs in input order.

If neither a URL nor `--resume` is supplied, return a short usage message. Do not open the dashboard pre-emptively.

## Core orchestration rules

1. Never open the dashboard before `register_run` returns a concrete `run_id`.
2. Never call `mcp__blog-optimiser-dashboard__open_dashboard` without a `run_id`.
3. Never call the deprecated path-resolver MCP tool. `register_run` already returns the absolute paths you need.
4. Never use `mcp__c4ai-sse__ask` as a prereq healthcheck.
5. Disk state is authoritative. After each stage, update the run's `state.json` directly and use `update_state` only as a best-effort mirror.
6. Sub-agents only get absolute paths passed in by the main session.
7. Host-side run and site artefacts must be read and written through the dashboard MCP artifact tools, not sandboxed `Bash`, `Read`, or `Write`.
8. Treat the absolute paths from `register_run` as host references for MCP `output_path` arguments only.
9. Draft visibility is driven by the dashboard validator output, not by generator confidence or self-reported pass/fail text.
10. Do not assume the Peec MCP server is literally named `peec`. In Cowork it may be connected under a UUID-style server prefix. Discover the Peec tool family by capability and use it if present.
11. Crawl4AI MCP is the primary tested crawler. Expect the official local Crawl4AI server to be connected as `c4ai-sse` and use it when available.
12. Do not assume the Firecrawl MCP server is literally named `firecrawl`. In Cowork it may be connected under a UUID-style server prefix. Discover the Firecrawl tool family by capability and use it as the supported alternative when Crawl4AI is unavailable or explicitly selected.
13. Use `ToolSearch` when you need to resolve external MCP tool names dynamically. Restrict yourself to the blog optimiser dashboard MCP, Firecrawl, Crawl4AI, and the connected Peec MCP if available; do not use unrelated tools just because `allowed-tools` is broad.
14. When calling `write_json_artifact`, pass a raw JSON object or array in `data`. Never pre-serialize with `json.dumps`, `JSON.stringify`, or fenced JSON text.
15. Prefer typed dashboard tools for core pipeline writes: `record_crawled_article`, `record_voice_baseline`, `record_peec_gap`, `record_competitor_snapshot`, `record_evidence_pack`, `record_recommendations`, `record_draft_package`, `fail_article_stage`, `finalize_crawl`, and `finalize_run_report`.
16. The dashboard is a report surface only. Do not create or rely on dashboard continue gates.
17. If one or more `--article-url` flags are supplied, pass the exact ordered URL list into `register_run` as `article_urls` and into the crawler prompt as `article_urls`. Do not let discovery substitute other posts.

## Final message to the user

When the pipeline finishes, return a compact status summary:

- articles processed
- draft-ready vs blocked
- dashboard URL
- run directory
- one-line note if any human input is still needed outside the dashboard

Do not paste article bodies, full recommendation tables, or draft content into chat.
