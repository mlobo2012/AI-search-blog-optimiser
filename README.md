# AI Search Blog Optimiser

Turn a blog URL into AI-search-ready article rewrites.

This is a Claude Cowork plugin for teams that want to run a weekly AI visibility workflow without manually copying prompts, citations, competitor mentions, recommendations, drafts, schemas, and QA notes between tools.

## What Problem Does This Solve?

Teams are starting to check whether ChatGPT, Perplexity, Google AI Overview, Gemini, Claude, and Copilot mention their brand when buyers ask category questions.

The manual workflow is painful:

1. Pick 10-20 high-intent prompts buyers might ask.
2. Run those prompts across multiple AI engines.
3. Log whether your brand appears.
4. Log which competitors appear instead.
5. Open the sources each engine cites.
6. Work out why those sources are being trusted.
7. Turn the gap into an article brief.
8. Rewrite the article without making unsupported claims.
9. Add schema, FAQ, evidence, links, trust blocks, and source citations.
10. Check whether the rewrite actually implemented the recommendations.
11. Repeat next week, because AI answers move.

That work usually lands across SEO teams, content teams, product marketing, PR, and agencies. Monitoring tools can show the gap. The hard part is turning the gap into a usable content update every week.

AI Search Blog Optimiser closes that loop.

Give it a blog URL. It crawls the blog, reads live Peec AI data, finds the prompts and sources where the brand is losing, creates recommendations, writes optimized article drafts, and blocks anything that cannot be supported honestly.

The value is speed and repeatability: instead of spending a day collecting screenshots, copying citations, briefing a writer, and QA-ing the result, you can run the workflow weekly and get draft-ready article packages plus a clear report of what still needs human input.

## Quick Start

Run the workflow from Claude Cowork:

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 2
```

Expected result:

- a local dashboard opens for the run
- the plugin crawls the Granola blog
- each article gets Peec-backed gap analysis
- each article gets recommendations
- each article gets an optimized markdown draft, HTML draft, schema, diff, handoff doc, and validation manifest
- `run-summary.md` tells you which articles are draft-ready and which are blocked

Use this for your own site:

```text
/blog-optimiser https://your-company.com/blog --max-articles 10
```

Run it every week:

```text
/blog-optimiser https://your-company.com/blog --max-articles 20
```

Resume a previous run:

```text
/blog-optimiser --resume 2026-04-25T19-21-10
```

Refresh the brand voice baseline:

```text
/blog-optimiser https://your-company.com/blog --refresh-voice
```

## How Does It Work?

The workflow has seven stages.

1. **Prereqs** - checks that Peec MCP and Crawl4AI are available.
2. **Crawl** - discovers real article URLs from the blog index.
3. **Voice** - builds or reuses a site-level brand voice baseline.
4. **Analysis** - matches articles to Peec prompts, AI engines, source gaps, and competitor citations.
5. **Evidence** - gathers claims, source URLs, reviewer candidates, and internal link options.
6. **Recommendations** - turns the gap data into a rewrite blueprint.
7. **Draft** - writes the optimized article package and validates it.

The dashboard is for review. Claude Cowork stays in control of the workflow.

## Granola Example

The repo includes recent test runs against:

```text
https://www.granola.ai/blog
```

One run processed two Granola posts:

- `Granola Chat just got smarter`
- `Granola raises $125M to put your company's context to work`

Both ended draft-ready in the run summary.

### Example 1: Granola Chat Just Got Smarter

Source article:

```text
Title: Granola Chat just got smarter
Author: Jack
Opening: Today, we're releasing a much smarter and faster Granola Chat...
```

The workflow found that the post was not shaped around the prompts it needed to win:

```json
{
  "matched_prompts": 3,
  "chatgpt_visibility": "about 4.5%",
  "perplexity_visibility": "0%",
  "google_ai_overview_visibility": "about 38%",
  "sentiment_floor": {"engine": "chatgpt-scraper", "value": 59},
  "dominant_content_shape": "LISTICLE",
  "owned_coverage_percent": 0
}
```

It then produced specific recommendations, not generic SEO advice:

```json
{
  "id": "rec-012",
  "category": "content_gap",
  "priority": "critical",
  "title": "Add TL;DR block and retrieval-oriented H1 framing",
  "fix": "Add a 30-60 word TL;DR that states what changed, what it does, and why inline citations make it auditable.",
  "target_engines": ["chatgpt-scraper", "perplexity-scraper", "google-ai-overview-scraper"]
}
```

```json
{
  "id": "rec-014",
  "category": "engine_specific",
  "priority": "high",
  "title": "Address ChatGPT and Perplexity engine asymmetry",
  "fix": "Add a 'Who it is for' or 'Works with' section stating Google Meet, Zoom, and Microsoft Teams."
}
```

The optimized draft started like this:

```markdown
# Granola Chat just got smarter

By Chris Pedregal, CEO & Co-founder - Granola
Published 2026-04-21 - Updated 2026-04-25

**TL;DR**
We've rebuilt Granola Chat from the ground up as an agentic assistant...
```

It also added prompt-shaped sections:

```markdown
## How does Granola Chat search across all your past meetings?
## Who is Granola Chat for - and which meeting platforms does it support?
## How does Granola turn meeting notes into team knowledge?
```

Validation result:

```json
{
  "quality_gate": "passed",
  "recommendations_implemented": 17,
  "inline_evidence_count": 3,
  "schema": ["BlogPosting", "BreadcrumbList", "FAQPage", "Organization", "Person"]
}
```

### Example 2: Granola Series C

Source article:

```text
Title: Granola raises $125M to put your company's context to work
Opening: Today we're announcing our $125M Series C...
```

The workflow matched this article to seven tracked Peec prompts and found a stronger AI-search gap:

```json
{
  "matched_prompts": 7,
  "chatgpt_visibility": "about 12%",
  "perplexity_visibility": "about 7%",
  "google_ai_overview_visibility": "about 51%",
  "chatgpt_sentiment_floor": 46,
  "editorial_gatekeepers": ["techtarget.com", "trendharvest.blog", "meetingnotes.com"]
}
```

One recommendation:

```json
{
  "id": "rec-010",
  "category": "content_gap",
  "priority": "critical",
  "title": "Add TL;DR block and reframe H2 headings as user-prompt mirrors",
  "fix": "Rename H2s around Spaces, CRM/API workflows, and enterprise compliance controls."
}
```

Another recommendation:

```json
{
  "id": "rec-016",
  "category": "claim_synthesis",
  "priority": "high",
  "fix": "Open the APIs section with a citable claim about piping meeting context into Salesforce, HubSpot, or any tool."
}
```

The optimized article added direct answer sections:

```markdown
## How Granola Spaces helps teams search across all past meetings
## How Granola APIs connect meeting context to your CRM and other tools
## What enterprise compliance controls does Granola include?
```

Validation result:

```json
{
  "quality_gate": "passed",
  "audit_after": 34,
  "recommendations_implemented": 17,
  "inline_evidence_count": 5,
  "faq_questions": 5
}
```

## What Gets Generated?

Each article gets a folder of usable outputs:

```text
outputs/
  articles/{slug}.json
  gaps/{slug}.json
  evidence/{slug}.json
  recommendations/{slug}.json
  optimised/{slug}.md
  optimised/{slug}.html
  optimised/{slug}.schema.json
  optimised/{slug}.diff.md
  optimised/{slug}.handoff.md
  optimised/{slug}.manifest.json
  rubric/{slug}.json
```

Use the files this way:

- `recommendations/{slug}.json` - see what to change and why
- `optimised/{slug}.md` - edit or publish the draft
- `optimised/{slug}.html` - inspect rendered structure and embedded schema
- `optimised/{slug}.diff.md` - review what changed
- `optimised/{slug}.handoff.md` - give an editor the action list
- `optimised/{slug}.manifest.json` - confirm the quality gate passed

## What Makes It Useful Weekly?

The workflow is designed for recurring content ops.

Every week you can:

1. Run the blog again.
2. See which articles still map to live prompt gaps.
3. See whether ChatGPT, Perplexity, and Google AI Overview changed behavior.
4. See which competitor domains and editorial surfaces are still shaping answers.
5. Refresh drafts with new evidence.
6. Hand the editorial team a short list of publishable updates.

This matters because AI visibility is not just a rank. It is whether an answer engine selects your brand, explains it correctly, and cites sources that support the story you want buyers to hear.

## Install And Run

### 1. Install the plugin from this repo

In Claude Cowork, install this folder as a local plugin. Choose the repo root, the folder that contains:

```text
.claude-plugin/plugin.json
commands/blog-optimiser.md
dashboard/server.py
agents/
skills/
references/
```

For the latest code, use the source checkout rather than the older ZIP files in `dist/`.

### 2. Connect Peec MCP

Add the Peec MCP server to Claude/Cowork:

```text
https://api.peec.ai/mcp
```

Use Streamable HTTP transport and sign in through Peec OAuth when prompted.

The plugin expects a Peec project with:

- own brand configured
- competitors configured
- tracked prompts
- at least one day of Peec data

### 3. Make Crawl4AI available

The workflow uses Crawl4AI to fetch blog pages. If Crawl4AI is not connected, the command stops during prereqs before creating a run.

### 4. Run the Granola example

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 2
```

Watch for:

- local dashboard URL
- `run_id`
- article crawl count
- recommendation count
- draft-ready vs blocked status

### 5. Run your own weekly workflow

```text
/blog-optimiser https://your-company.com/blog --max-articles 20
```

Then review:

```text
run-summary.md
outputs/recommendations/
outputs/optimised/
```

If an article is blocked, read the reason first. A blocked article usually means the system could not find enough evidence, trust, or source support to ship a defensible rewrite.

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
- `skills/blog-optimiser-pipeline/SKILL.md` - orchestration playbook
- `skills/peec-gap-read/SKILL.md` - Peec gap-read recipe
- `references/geo-article-contract.md` - article quality contract
- `dashboard/server.py` - local dashboard MCP runtime
- `dashboard/quality_gate.py` - draft validator
- `dashboard/rubric_lint.py` - deterministic GEO lint
- `agents/*.md` - worker contracts
