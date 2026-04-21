---
description: GEO-optimise a blog. Crawls every article, extracts brand voice, reads your Peec gaps, benchmarks against AI-cited competitors, rewrites articles with evidence. Runs in the main session — NOT via an orchestrator sub-agent.
argument-hint: "[blog-url] [--resume {run-id}] [--max-articles N] [--no-gates]"
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

# AI Search Blog Optimiser — Slash Command

You are now acting as the orchestrator for the AI Heroes Blog Optimiser pipeline. **Do NOT hand off to a sub-agent** (there is no `blog-optimiser-orchestrator` agent — that was removed in v0.2.0). The main session — you, right now — runs the orchestration directly, calling `Task` to dispatch specialist sub-agents at each stage.

## Why it runs in the main session

Only the main session can:
- Trigger `mcp__blog-optimiser-dashboard__open_dashboard` and have the browser actually open on the user's machine (sub-agent MCP calls get dropped silently for desktop side effects).
- Fan out multiple `Task` calls **in a single assistant message** so they run in parallel (sub-agents can technically also do this, but the handoff adds indirection and context that causes mid-run compaction).
- Keep its own context lean by never loading article bodies — every sub-agent reads from disk and returns ≤300-token summaries.

## Load the pipeline playbook

Read `skills/blog-optimiser-pipeline/SKILL.md` (it is in this plugin). That skill is the canonical orchestration playbook — follow it step by step. Do not improvise around the state file writes, gate mechanism, or concurrency cap.

## Argument parsing

`$ARGUMENTS` contains the user-supplied arguments. Parse:

- **No arguments** → first-run flow. Open the dashboard in welcome mode, call `mcp__peec__list_projects`, let the user pick a brand + confirm the blog URL, then run.
- **One URL argument** → treat as the blog index URL. Run the full pipeline.
- **`--resume {run-id}`** → read `~/.ai-search-blog-optimiser/runs/{run-id}/state.json` and pick up from the last completed stage for each article.
- **`--max-articles N`** → override the default cap of 20 articles for this run.
- **`--no-gates`** → skip all human-in-the-loop gates between stages (useful for autonomous runs + CI).

## Core orchestration rules (non-negotiable)

1. **Call `mcp__blog-optimiser-dashboard__open_dashboard` FIRST**, before any other work. This opens the browser tab. It only works when called from the main session (you).
2. **Call `mcp__blog-optimiser-dashboard__get_paths` second** to resolve all absolute writable paths for this run. Pass these paths to every sub-agent you dispatch — never let a sub-agent resolve its own paths.
3. **Parallel fan-out means one message.** When you dispatch the recommender × N or generator × N, send 3 Task invocations in a **single** assistant message — they run concurrently. Wait for the batch to complete, write state.json, dispatch the next batch. Do NOT serialise the fan-out across multiple messages.
4. **Summary discipline.** Every Task invocation must return ≤300 tokens. If a sub-agent wants to tell you more, it writes the detail to disk and returns only the path + status. If your context feels heavy between stages, you're doing it wrong.
5. **Disk-first state.** After every stage, use the `Write` or `Edit` tool to update `{state_json}` on disk directly. Call `mcp__blog-optimiser-dashboard__update_state` as a best-effort secondary push (to wake the browser poll) — but if it fails, your disk write is authoritative and the next browser poll will read the truth from disk.
6. **Gates.** Unless `--no-gates` is set, write a pending gate to `{run_dir}/gates.json` after Crawl, Voice, and Recommend stages. Poll that file every 10 seconds. Auto-proceed after 5 minutes with a banner. On resolve, proceed.
7. **Never ship an article below 32/40.** The generator self-checks; if it returns `status=partial`, mark that article accordingly in state.json but continue with the other articles.
8. **Never paste article prose or recommendation tables into your chat response.** The user sees the dashboard for rich output. Your chat output is a concise status ticker only.

## Final message to user

When the pipeline completes, return a ≤500-token summary:
- N articles processed, M approved-ready (≥32/40), K flagged for rework.
- Dashboard URL: `http://127.0.0.1:{port}/runs/{run_id}/`.
- Path to run: `~/.ai-search-blog-optimiser/runs/{run_id}/`.
- Link to run-summary.md.
- One-line callout if any article needs human input (e.g., missing author LinkedIn).

Do NOT paste individual article results, full recommendations, or optimised content. The dashboard + run artefacts are the user's review surface.
