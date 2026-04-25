# Bug 02 acceptance test: evidence-builder agent registration

Manual reproduction sequence for a fresh Claude Code session with the
`ai-search-blog-optimiser` plugin enabled.

## Static preflight

1. Inspect `.claude-plugin/plugin.json`.
2. Assert there is no explicit top-level `agents` allow-list. If an `agents` list is later added, it MUST include `evidence-builder`.
3. Inspect `agents/evidence-builder.md` frontmatter and compare it with `agents/recommender.md`.
4. Assert the evidence-builder frontmatter uses only the supported keys in this order:

```yaml
---
name: evidence-builder
description: Builds a reviewer-aware evidence pack for one article using public first-party and external sources, then writes it as a real run artifact.
model: sonnet
maxTurns: 18
---
```

## Claude Code smoke

1. In a fresh Claude Code session, list available Task agent types.
2. Assert `ai-search-blog-optimiser:evidence-builder` is present.
3. Register a disposable run with the dashboard MCP and capture `run_id`.
4. Seed one article with `record_crawled_article` using slug `smoke`.
5. Call:

```text
Task(
  subagent_type="ai-search-blog-optimiser:evidence-builder",
  description="smoke",
  prompt="Build evidence for run_id=<run_id>, article_slug=smoke, site_key=<site_key>, peec_project_id=<project_id>. Use the dashboard MCP tools only. Fetch only real public source pages, then write evidence/smoke.json through record_evidence_pack."
)
```

6. Assert the Task call does not fail with `Agent type not found`.
7. Assert the sub-agent writes a valid `evidence/smoke.json` payload through `record_evidence_pack`.

Pass criterion: the resolver exposes `ai-search-blog-optimiser:evidence-builder`, dispatch does not raise `Agent type not found`, and the smoke prompt produces valid evidence JSON.
