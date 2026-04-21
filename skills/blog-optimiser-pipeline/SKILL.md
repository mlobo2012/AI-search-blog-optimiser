---
name: blog-optimiser-pipeline
description: Orchestration playbook for the AI Search Blog Optimiser pipeline. Use when running or resuming the /blog-optimiser command. Defines the 4-stage flow, context management rules, model allocation, parallelism caps, error handling, and the embedded 15-point GEO + 40-point audit rubric so the plugin works even when the user's environment lacks external skill banks.
version: 0.1.0
---

# Blog Optimiser Pipeline

The canonical playbook consumed by the `blog-optimiser-orchestrator` agent. Encodes everything Claude needs to run the pipeline robustly without requiring external skill banks to be installed.

## Stages

1. **Prereq validation** — verify Peec MCP, Crawl4AI MCP, dashboard server. Fall back to generic mode if Peec is unavailable; hard-fail if Crawl4AI is unavailable.
2. **Peec project resolution** — `list_projects` → auto-match domain → set `role` → `register_run`.
3. **Crawl** — sequential per-article extraction via the `blog-crawler` sub-agent.
4. **Voice extraction** — single call to `voice-extractor` sub-agent.
5. **Recommend** — fan out `recommender` sub-agents (cap=3 concurrent); each spawns its own `peec-gap-reader` + `competitor-crawler`.
6. **Generate** — fan out `generator` sub-agents (cap=3 concurrent).
7. **Finalise** — write `run-summary.md`, push final state.

## Context management rules

- **The orchestrator never reads article bodies.** It passes file paths to sub-agents and receives ≤ 500-token summaries.
- **Disk is shared memory.** All cross-agent state lives in `runs/{run_id}/`.
- **Each sub-agent loads what it needs, nothing more.** `recommender` loads the audit rubric + GEO rules; `blog-crawler` loads none.
- **1M context windows on Cowork (Opus 4.6/4.7)** remove token-budget pressure on single-agent steps — but the sub-agent pattern stays for parallelism, context cleanliness, and failure isolation.

## Model allocation

| Agent | Model | Reason |
|---|---|---|
| orchestrator | opus | Multi-step planning, error recovery |
| blog-crawler | haiku | Mechanical extraction × N articles — cost-sensitive |
| voice-extractor | sonnet | Stylistic synthesis, one-shot |
| peec-gap-reader | sonnet | Data routing + light reasoning |
| competitor-crawler | haiku | Structured extraction × 5 URLs |
| recommender | opus | The demo money shot — judgment quality matters |
| generator | opus | Brand-voice rewriting quality |

## Parallelism

Stages 5 and 6 fan out articles with concurrency cap = 3. Balances throughput vs. Anthropic rate limits and Peec MCP limits.

## Checkpointing

Every sub-agent write is atomic (tmp + rename). `state.json` updates after every sub-agent returns. `--resume {run_id}` picks up from last completed stage per article.

## Error handling

- MCP timeout → retry once with exponential backoff (2s, 4s). Second failure → log to state, continue.
- Sub-agent fails → retry once. Second failure → mark `failed` on the article, continue the run.
- Rate limit → exponential backoff up to 60s; state shows `waiting on rate limit`.
- Never halt the whole run on a single article failure.

## Embedded GEO rules (the 15-point checklist)

When external skill banks (Marco's gstack `geo-content-engineering` etc.) aren't available, agents use these embedded rules. Evidence citations are Peec/Profound 2025-2026 research.

1. **Trust block at top** — 30–60 word direct answer, followed by 1–2 atomic paragraphs with cited sources + visible last-updated date + named author. Highest-leverage single change.
2. **Atomic paragraphs** — no paragraph > ~150 words or ~3 sentences for primary claims. Dense blocks aren't chunk-extractable.
3. **Question-based H2/H3** — every heading mirrors an actual user prompt. Engines match chunks to prompts.
4. **Tables for structured data** — pricing, feature matrices, specs in `<table>`, not prose. Top-5 citation driver.
5. **Concrete numbers in titles/H2s** — "7 X for Y", not "Several X to consider".
6. **Current-year modifier** — 2026 in title, slug, at least one H2. Engines inject year modifiers during fanout.
7. **Target 1,500–2,500 words** — Profound benchmark; not 500, not 5,000.
8. **Specialized schema** — FAQPage, HowTo, Product, Person, Organization, DefinedTerm, Review over generic Article. FAQ schema = biggest single citation lift.
9. **Cite primary sources inline** — `.gov`, `.edu`, analyst firms, named studies as "According to [NIH, 2025], …".
10. **Named, credentialed author + Person schema** — full name, role, credentials, LinkedIn, photo. ~41% higher citation likelihood. Avoid "Staff".
11. **Original data or framework** — at least one proprietary stat, named framework, first-hand case with numbers. Recycled content doesn't earn citations.
12. **Listicle / comparison / how-to format bias** — 52% of listicles achieve ≥2.0 citation rate on ChatGPT. BUT do not rank your own product #1 in your own listicle (self-promo filtered 3× harder).
13. **Shippable-noun presence** — embed concrete buyable nouns ("meeting notes app" not "productivity tool"). Apparel 62% / Physical 56% / Consumables 30% ChatGPT Shopping trigger rates.
14. **Multimodal enrichment** — products cited most show 848% more FAQs, 103% more videos, 36% higher ratings, 23% more spec entries vs uncited.
15. **Chunk-extractability self-test** — every H2 section must answer its implied question standalone.

## Embedded 40-point audit rubric

Scored binary pass/fail, total 40 (minimum passing 32).

### Retrieval foundation (6 pts)
- [ ] Robots.txt allows major AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
- [ ] Canonical URL set correctly
- [ ] Meta description present, 120–155 chars
- [ ] Alt text on ≥80% of images
- [ ] Updated-at date within last 12 months (or clearly marked evergreen)
- [ ] Semantic HTML (proper H1→H6 hierarchy, `<article>`/`<section>`)

### Chunk extractability (8 pts)
- [ ] Trust block in first 60 words
- [ ] Atomic paragraph ratio ≥ 0.6
- [ ] H2s phrased as user prompts (question or imperative)
- [ ] ≥1 table for structured data where relevant
- [ ] ≥1 concrete number/stat in the title or an H2
- [ ] Every H2 section extractable standalone
- [ ] Current-year modifier present (title OR H2 OR slug)
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

### Article-type-specific (8 pts, varies by type)
See embedded presets below.

## Article-type presets (8 pts each)

### Listicle
- [ ] Ranked items with named criteria
- [ ] Intro comparison table above fold
- [ ] Each item has 40–200w standalone answer
- [ ] Named author with credentials
- [ ] NOT self-promotional
- [ ] Current-year modifier in title
- [ ] Internal cross-links to each item's detail page
- [ ] ItemList schema

### How-to
- [ ] Numbered steps, each standalone
- [ ] HowTo schema with step properties
- [ ] Total time estimate visible
- [ ] Tools / prerequisites listed upfront
- [ ] Images or video per step where applicable
- [ ] FAQ section for common failure modes
- [ ] Troubleshooting block
- [ ] Year modifier if time-sensitive

### Comparison
- [ ] Comparison table above fold
- [ ] Balanced coverage (not biased)
- [ ] Named criteria with rationale
- [ ] Pricing included and dated
- [ ] Verdict / "when to choose" section
- [ ] Both products' named author commentary
- [ ] Article + FAQPage schema
- [ ] Link to each product's standalone page

### Glossary
- [ ] 30–60w definition in trust block
- [ ] DefinedTerm schema
- [ ] Synonyms / aliases listed
- [ ] 2–3 examples in context
- [ ] Related-terms cross-links
- [ ] "Not to be confused with" block
- [ ] Elaboration after definition
- [ ] FAQPage if ≥3 questions

### Case study
- [ ] Named client with permission
- [ ] Problem → Action → Result structure
- [ ] ≥3 quantified outcomes
- [ ] Timeframe stated
- [ ] Method / approach detail
- [ ] Client quote with role + full name
- [ ] Article schema with author
- [ ] Linked to the product/service page

### Pillar
- [ ] Table of contents jump-linked
- [ ] Every H2 extractable
- [ ] Cross-links to related detail pages
- [ ] Summary of key points at top
- [ ] Glossary/definitions section
- [ ] FAQ section (5+ questions)
- [ ] Multi-schema (Article + FAQPage + HowTo if applicable)
- [ ] Last-updated date prominent

### Opinion
- [ ] Clear thesis in trust block
- [ ] Named, credentialed author (higher bar)
- [ ] Supporting evidence with inline citations
- [ ] Counter-argument section
- [ ] Original framework or data
- [ ] Author's credential relevant to topic
- [ ] Publish AND last-updated dates
- [ ] Person schema linked to author

### Product
- [ ] Product schema with all required fields
- [ ] FAQPage for ≥3 Q&A
- [ ] Review / AggregateRating schema
- [ ] Rich enrichment: FAQs, video, rating, specs
- [ ] Shippable-noun in description
- [ ] Natural-language description
- [ ] Variants/sizes/compatibility
- [ ] Natural-language URL slug

## Strategic non-goals

Agents must not:
- Generate mass AI content (Schmidt: 100% of pages removed under 2024 Google spam policy had AI content).
- Optimise for a single engine (89% of cited domains diverge between ChatGPT and Perplexity).
- Publish self-promo listicles ranking own brand #1.
- Use universal citation-rate thresholds (ChatGPT target ≥2.0, Perplexity 1.5–2.0, Google AI Mode 1.1–1.5).
- Auto-push to a CMS.

## Per-engine benchmarks

| Engine | Citation rate target | Avg |
|---|---|---|
| ChatGPT | ≥ 2.0 | > 2.5 |
| Google AI Mode | 1.1–1.5 | > 1.2 |
| Perplexity | 1.5–2.0 | 0.5 |

Display metrics as per the Peec MCP rules: visibility/SoV/retrieved_percentage are 0-1 ratios (×100 for display); sentiment is 0-100; citation_rate is an average (never × 100); position is rank (lower = better).
