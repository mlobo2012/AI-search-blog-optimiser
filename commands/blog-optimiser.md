---
description: GEO-optimise a blog. Runs in the main session — never via an orchestrator sub-agent.
argument-hint: "[blog-url] [--resume {run-id}] [--refresh-voice] [--max-articles N] [--no-gates]"
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

You are the orchestrator for the AI Heroes Blog Optimiser pipeline. The orchestration runs directly in the main session. Do not hand off to an orchestrator sub-agent.

## Load the canonical playbook

Read `skills/blog-optimiser-pipeline/SKILL.md` and follow it exactly. That skill is the source of truth for ordering, state writes, browser opening, and resume behavior.

## Argument parsing

`$ARGUMENTS` contains the user-supplied arguments. Parse:

- Positional URL → the blog index URL for a fresh run
- `--resume {run-id}` → resume an existing run
- `--refresh-voice` → force a new voice baseline even if the same site already has one
- `--max-articles N` → override the default article cap of 20
- `--no-gates` → skip human review gates

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

## Final message to the user

When the pipeline finishes, return a compact status summary:

- articles processed
- approved-ready vs flagged
- dashboard URL
- run directory
- one-line note if any human input is still needed

Do not paste article bodies, full recommendation tables, or draft content into chat.
