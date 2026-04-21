# AI Search Blog Optimiser

A Claude Desktop plugin that rewrites your blog's long tail for **AI search citation** — grounded in your own Peec AI gap data, the competitors AI engines are actually citing for your prompts this week, and the latest evidence-backed GEO best practices.

Point it at any blog URL. Get back optimised article drafts with a full evidence trail, ready for your content team.

**Built by [AI Heroes](https://aiheroes.site). Powered by the [Peec AI MCP](https://peec.ai) Challenge stack.**

---

## What it does

```
/blog-optimiser https://www.your-blog.com/blog
```

The plugin opens a live local dashboard in your browser and runs a 4-agent pipeline across every article on the blog:

1. **Crawls** every article via Crawl4AI — full HTML, images (downloaded locally), tables, schema, author block, link graph, CTAs.
2. **Extracts your brand voice** into a persistent, editable artefact (namespaced per Peec project so competitor runs never contaminate your own profile).
3. **Reads your Peec gap** — matched prompts, brand visibility per engine, competitor URLs currently being cited where you aren't, and the actual AI response excerpts. Crawls those competitor articles to see what structural pattern is winning.
4. **Rewrites each article** — augmenting, never replacing. Original claims, quotes, images, internal links are preserved. Schema gaps filled. Trust blocks added. Tables drafted. FAQ blocks generated from your matched Peec prompts. Brand voice applied throughout.

Every recommendation ships with a complete evidence trail: Peec gap signal + the relevant GEO rule + the competitor example + the exact article field the gap was detected in.

Outputs land on disk in `runs/{timestamp}/optimised/` — markdown, styled HTML, JSON-LD schema, handoff doc, diff vs original, and every image preserved in a self-contained folder ready for your CMS.

---

## Install

### Prerequisites

1. **Claude Desktop** with the Cowork plugin system (April 2026+).
2. **Peec AI MCP** connected to Claude Desktop. Follow the [Peec MCP Quick Start](https://peec-ai.notion.site/Peec-MCP-Challenge-Quick-Start-Kit-33ccac05310f805fb0a8dbcabe1a66d9) and ensure you have at least one project configured with tracked topics, prompts, and competitors.
3. **Crawl4AI MCP** connected to Claude Desktop. See [Crawl4AI](https://github.com/unclecode/crawl4ai) for setup.
4. **Python 3.8+** on PATH. macOS bundles this by default; Windows/Linux users install from [python.org](https://python.org).

### Install the plugin

1. Download `ai-search-blog-optimiser.zip` from the [latest release](https://github.com/mlobo2012/AI-search-blog-optimiser/releases).
2. Unzip into `~/.claude/plugins/marketplaces/local-desktop-app-uploads/AI-search-blog-optimiser/`.
3. In Claude Desktop, run `/plugin reload`.
4. Confirm the command is available: type `/blog-optimiser` — you should see it in the slash-command menu.

### First run

```
/blog-optimiser https://www.your-blog.com/blog
```

- Your browser opens to `http://127.0.0.1:{port}/` with the AI Heroes dashboard.
- The plugin auto-matches your blog's domain to one of your Peec projects.
- If multiple matches or no matches, a banner in the dashboard asks you to pick.
- If you have no Peec projects, the plugin runs in "generic mode" (GEO best practices without live gap data) and surfaces a link to Peec setup.
- Progress updates live in the dashboard as each stage completes.

Typical run: ~10–15 minutes for a blog of 15–20 articles.

---

## How it works

Seven specialised agents, dispatched by an orchestrator, running with isolated context windows and disk-backed shared state:

| Agent | Model | Role |
|---|---|---|
| `blog-optimiser-orchestrator` | Opus | Top-level planning, dispatch, checkpointing |
| `blog-crawler` | Haiku | Crawl4AI extraction per article |
| `voice-extractor` | Sonnet | Synthesise persistent brand-voice artefact |
| `peec-gap-reader` | Sonnet | Pull matched prompts + gap data + AI response excerpts |
| `competitor-crawler` | Haiku | Crawl competitor URLs from the gap report |
| `recommender` | Opus | Synthesise 5–7 grounded recommendations per article |
| `generator` | Opus | Rewrite each article augmenting with accepted recs, preserving originals |

**Context management:** The orchestrator never reads article bodies; it passes file paths. Sub-agents each get a fresh context window (up to Cowork's 1M on Max plans) and return compact summaries. All shared state lives on disk under `runs/{run_id}/`.

**Parallelism:** Steps 5 (recommend) and 6 (generate) fan out with concurrency cap = 3. Balances throughput against Anthropic + Peec rate limits.

**Resumability:** Every write is atomic. Crash Claude Desktop mid-run? Relaunch and `/blog-optimiser --resume {run_id}` picks up from the last completed checkpoint.

---

## Output anatomy

For each article, the plugin produces in `runs/{run_id}/optimised/{slug}/`:

- `{slug}.md` — CMS-ready markdown with full frontmatter
- `{slug}.html` — styled preview in AI Heroes theme, schema JSON-LD embedded
- `{slug}.schema.json` — standalone JSON-LD payload for direct engineer injection
- `{slug}.diff.md` — section-level diff vs original: what changed, what was preserved, what's flagged for human input
- `{slug}.handoff.md` — review brief for the content team: before/after audit scores, recommendations applied with full evidence trail, per-engine lift table
- `media/{slug}/` — every image used, preserved from the original

A `run-summary.md` at the root of the run summarises all articles with scores and dispositions.

---

## Recommendation evidence trail

Every recommendation includes:

1. **Fix** — concrete, specific action (not "consider adding a trust block" — "add a 30-60 word trust block answering 'how do I take good meeting notes with AI' — competitor otter.ai/blog/take-better-notes (cited 2.1× on ChatGPT for this prompt) opens with this exact pattern").
2. **Severity** — critical / high / medium / low.
3. **Effort** — <1h / 1–4h / 1 day / multi-day.
4. **Expected lift per engine** — grounded in Peec benchmarks (ChatGPT ≥2.0, Perplexity 1.5–2.0, Google AI Mode 1.1–1.5).
5. **Evidence trail** — four slots, all filled:
   - **Peec gap** — the matched prompt, engines you're losing on, cited competitor URLs and rates
   - **GEO rule** — specific rule reference (e.g. `geo-content-engineering#1 trust block at top`)
   - **Competitor example** — URL + verbatim excerpt of what won the citation
   - **Detected in** — the exact article field that failed (e.g. `schema.types_missing` or `trust.author.linkedin`)

No generic advice. No fabricated numbers. No universal benchmarks across engines. Every claim traces back to either your article, your Peec data, or a cited research source.

---

## Troubleshooting

### "Peec AI MCP is not connected"

Follow the [Peec MCP Quick Start](https://peec.ai). The plugin still runs without Peec (generic mode) but you lose the live gap data — recommendations become best-practice-only.

### "Crawl4AI MCP is not connected"

Crawl4AI is required — no fallback. Install from [github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) and re-run `/plugin reload`.

### Dashboard doesn't open / browser shows "connection refused"

Check that `python3` is on your PATH:

```
which python3 && python3 --version
```

If missing, install from [python.org](https://python.org). Then `/plugin reload`.

### Dashboard shows "no active run" indefinitely

The orchestrator agent hasn't registered a run yet. Check Claude Desktop's chat for error messages. If stuck, run `/blog-optimiser` again — resumable state means no work is lost.

### Run crashed mid-way

```
/blog-optimiser --resume {run_id}
```

The `{run_id}` is a timestamp like `2026-04-21T18-52-33`. You'll find it under `runs/` in the plugin directory.

### Some articles are marked "partial" or "failed"

Open the dashboard, expand the article, look at the stage that failed. Common causes:

- Crawl4AI timed out on a JS-heavy page → retry via the dashboard's "Re-run" button.
- Peec had no data for the matched prompts (cold start) → article still gets processed, just without Peec evidence.
- Generator produced < 32/40 audit → review the flagged dimensions, reject some recommendations, re-run the generator stage.

### Brand voice contamination across runs

Brand voice is namespaced by `peec_project_id` + role (`own` / `competitor`). Running on a competitor writes to `.context/brands/{peec_project_id}-competitor-view/{domain}/`, never the own-brand artefact. If you suspect contamination, check the file path in `.context/brands/` — the directory name tells you which profile was used.

### Port clashes

The dashboard auto-picks a free port. If you have multiple runs or other services, expect ports like `:62543` rather than a fixed `:8080`.

---

## Privacy

Everything runs on your machine except what goes to:
- **Claude** (via the Claude Desktop API) — agent reasoning, article text, recommendation synthesis.
- **Peec AI MCP** — your existing connection, per your Peec account settings.
- **Crawl4AI MCP** — your existing connection.
- **CDNs** — the dashboard HTML loads Tailwind and Alpine from jsdelivr; no data goes back.

No telemetry. No lead tracking. No data leaves unless you explicitly hand off artefacts from `runs/` elsewhere.

---

## Roadmap

- Slack integration — push handoff docs to a content-team channel.
- Continuous drift loop — daily Peec sampling triggers automatic re-optimisation when a cited competitor changes.
- CMS push — Webflow, Contentful, Ghost, WordPress integrations behind confirmation gates.
- Net-new article generation — identify demand pockets your brand hasn't covered via `list_prompts` with no-coverage filter.
- Off-site distribution plan generator — per-article outbound plan for Reddit, LinkedIn, YouTube, editorial pitches.

---

## License

Apache 2.0 with Commons Clause. See `LICENSE`.

## Built by

[AI Heroes](https://aiheroes.site) · Built for the [Peec AI MCP Challenge](https://peec-ai.notion.site/Peec-MCP-Challenge-Quick-Start-Kit-33ccac05310f805fb0a8dbcabe1a66d9)
