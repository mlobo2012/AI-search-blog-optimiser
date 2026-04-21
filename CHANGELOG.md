# Changelog

All notable changes to the AI Search Blog Optimiser plugin.

## [0.1.0] — Unreleased

First public release. Peec AI MCP Challenge submission.

### Added
- 4-stage pipeline: crawl → voice → recommend → generate.
- 7 specialised agents with tiered model allocation (Opus for orchestrator/recommender/generator; Sonnet for voice/peec-gap-reader; Haiku for crawlers).
- Live local dashboard (python3 stdlib HTTP server + Tailwind/Alpine CDN + AI Heroes brand theme).
- Deep structural capture via Crawl4AI: heading tree, tables, images (downloaded locally), videos, schema gaps, trust signals, link graph, CTAs.
- Peec gap evidence trail per recommendation: matched prompts, brand visibility per engine, cited competitor URLs, verbatim AI response excerpts.
- Brand voice extraction: persistent, namespaced by Peec project ID + role, structural fingerprint + lexicon + tone rules + exemplar pairs.
- 40-point article audit rubric with type-adaptive presets (listicle / how-to / comparison / glossary / case-study / pillar / opinion / product).
- Recommender produces 5–7 recommendations per article, each with complete evidence trail (Peec gap + GEO rule + competitor example + Step 1 field) and structured `auto_fix` payload.
- Generator preserves all original claims, quotes, images, links; augments, never rewrites. Self-checks ≥ 32/40 before shipping.
- Outputs per article: optimised markdown + styled HTML + JSON-LD schema + handoff doc + diff vs original + self-contained media folder.
- Resumable via `/blog-optimiser --resume {run_id}`. Atomic disk writes.
- Dashboard accept/reject toggles per recommendation; re-run per article without re-running the whole pipeline.
- Generic mode fallback when Peec MCP isn't connected.
