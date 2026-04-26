# AI Search Blog Optimiser

Give the workflow a company blog URL. It indexes the blog, learns the brand voice, finds GEO optimisation opportunities from Peec-backed AI visibility data, writes recommendations, then turns those recommendations into optimised article drafts.

The point is simple: reuse the owned content you already have, and make it much easier to improve it at scale for AI search.

## Quick Start

Run this in Claude Cowork:

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 2
```

For your own blog:

```text
/blog-optimiser https://your-company.com/blog --max-articles 20
```

What happens:

- the dashboard opens for the run
- the blog index is crawled
- the plugin pulls article content from the URLs it finds
- brand voice is generated and saved for reuse in later runs
- Peec data is used to find where the brand is missing in AI answers
- competitor and top-cited source patterns are used to shape the recommendations
- recommendations are passed to the next agent to create an optimised article
- you get markdown, HTML, schema, diff, handoff notes, and a validation manifest

## What Problem Does This Solve?

Owned content matters for AI search, but most company blogs were not written for answer engines.

Product marketers, content teams, SEO teams, PR teams, and agencies now have to answer questions like:

- Are we mentioned when buyers ask ChatGPT or Perplexity about our category?
- Which competitors are being cited instead?
- Which third-party pages are AI engines trusting?
- What structure or semantics do those cited pages have that our article is missing?
- Can we improve our existing blog post instead of commissioning a new one?
- Did the writer actually implement the recommendations?

Doing this manually is slow.

The work usually looks like this:

1. Run buyer prompts across ChatGPT, Perplexity, Google AI Overview, Gemini, Claude, and Copilot.
2. Capture which brands appear and which sources get cited.
3. Open competitor pages and top-cited editorial pages.
4. Compare their structure, schema, FAQ coverage, trust signals, evidence, and phrasing.
5. Decide what your article is missing.
6. Turn that into a digestible recommendation list.
7. Hand it to a writer or product marketer.
8. Rewrite the article.
9. Check that the rewrite added the TL;DR, evidence, links, schema, FAQ, trust block, and prompt-shaped sections.
10. Repeat next week because AI answers and citation surfaces change.

That may be manageable for one or two posts. It breaks down across 20 or 30 articles.

AI Search Blog Optimiser automates the upstream work: crawling your pages, reading Peec research, comparing against competitor and top-cited pages, generating recommendations, and then passing those recommendations into a drafting agent.

It is a workflow for repurposing what you already own.

## How It Works

You give it the blog URL.

The crawler indexes the blog and pulls article content. For a demo you can cap it at 2 or 3 articles. For real use, you can run it across the whole blog.

Then the workflow runs in stages:

1. **Crawl the blog** - discovers article URLs from the blog index and saves the source content.
2. **Extract brand voice** - builds a reusable voice baseline for that site.
3. **Read Peec gaps** - finds prompts, engines, competitors, cited domains, and source gaps.
4. **Build evidence** - gathers the claims, sources, reviewer signals, and internal links the rewrite is allowed to use.
5. **Generate recommendations** - identifies semantic and structural changes likely to improve AI citation.
6. **Create the optimised article** - turns the recommendation list and original article into a draft.
7. **Validate the output** - checks schema, FAQ, evidence, trust, internal links, recommendation implementation, and quality gate status.

The important part is the waterfall:

```text
blog URL
  -> crawl articles
  -> generate/reuse brand voice
  -> read AI visibility gaps
  -> compare against cited competitors and sources
  -> generate recommendations
  -> generate optimised article
  -> hand off to content team
```

Instead of stopping at "here are recommendations", the workflow carries the work into an article draft.

## Granola Example

The example run used:

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 2
```

It processed:

- `Granola Chat just got smarter`
- `Granola raises $125M to put your company's context to work`

### 1. Source Blog Post

The crawler pulled the original Granola Chat article:

```text
Title: Granola Chat just got smarter
Author: Jack
Opening: Today, we're releasing a much smarter and faster Granola Chat...
```

The article had useful product information, but it was written like a launch post. It did not directly answer the buyer prompts the brand needed to win.

### 2. Peec-Backed Gap Analysis

The workflow matched the post to 3 tracked prompts and found:

```json
{
  "chatgpt_visibility": "about 4.5%",
  "perplexity_visibility": "0%",
  "google_ai_overview_visibility": "about 38%",
  "chatgpt_sentiment_floor": 59,
  "dominant_content_shape": "LISTICLE",
  "owned_coverage_percent": 0
}
```

The insight: Granola's own blog post was not competing with the listicles and competitor pages that answer engines already trusted.

### 3. Recommendations

The recommendation agent did not produce vague advice like "improve SEO".

It produced concrete changes:

```json
{
  "category": "content_gap",
  "priority": "critical",
  "title": "Add TL;DR block and retrieval-oriented H1 framing",
  "fix": "Add a 30-60 word TL;DR that states what changed, what it does, and why inline citations make it auditable."
}
```

```json
{
  "category": "engine_specific",
  "priority": "high",
  "title": "Address ChatGPT and Perplexity engine asymmetry",
  "fix": "Add a 'Who it is for' or 'Works with' section stating Google Meet, Zoom, and Microsoft Teams."
}
```

```json
{
  "category": "sentiment",
  "priority": "high",
  "title": "Fix ChatGPT sentiment floor (59)",
  "fix": "Replace vague capability language with a specific, differentiated claim about cross-meeting search, Team Space, and inline citations."
}
```

This is the difference: recommendations are based on Peec visibility data, top-cited source patterns, competitor presence, and the article's own structure.

### 4. Optimised Article

The drafting agent then used the recommendations and source article to create a new markdown draft.

It added a clear TL;DR:

```markdown
**TL;DR**
We've rebuilt Granola Chat from the ground up as an agentic assistant. It searches across all your meeting notes - personal notes, Team Space, and privately shared notes - and returns answers with inline citations that link to the source meeting. Works with Google Meet, Zoom, and Microsoft Teams.
```

It also reshaped the article around answer-style sections:

```markdown
## How does Granola Chat search across all your past meetings?
## Who is Granola Chat for - and which meeting platforms does it support?
## How does Granola turn meeting notes into team knowledge?
```

The output is not just a report. It is an article your content team can review, edit, and publish.

### 5. Validation

The final manifest showed:

```json
{
  "quality_gate": "passed",
  "recommendations_implemented": 17,
  "inline_evidence_count": 3,
  "schema": ["BlogPosting", "BreadcrumbList", "FAQPage", "Organization", "Person"]
}
```

The Series C article went through the same flow and reached:

```json
{
  "quality_gate": "passed",
  "audit_after": 34,
  "recommendations_implemented": 17,
  "inline_evidence_count": 5,
  "faq_questions": 5
}
```

## What You Get Back

For each article:

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

The useful files:

- `recommendations/{slug}.json` - what to change and why
- `optimised/{slug}.md` - markdown article draft
- `optimised/{slug}.html` - rendered article with embedded schema
- `optimised/{slug}.diff.md` - what changed from the source
- `optimised/{slug}.handoff.md` - editor handoff
- `optimised/{slug}.manifest.json` - validation and recommendation implementation proof

## Why Run This Weekly?

AI search changes quickly.

Competitors get added to roundups. New Reddit threads appear. Product pages get cited. Sentiment shifts. Your own blog might already have the right raw material, but not the right structure.

This workflow lets a product marketer or content lead run the same process every week:

1. Crawl the blog.
2. Reuse the saved brand voice.
3. Pull fresh Peec visibility data.
4. Find which owned posts can be improved.
5. Generate recommendations at scale.
6. Turn those recommendations into draft articles.
7. Send markdown and handoff notes to the content team.

That is the core value: not a one-off audit, but a repeatable owned-content optimisation loop.

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

Use the source checkout for the latest code. The ZIP files in `dist/` are older builds.

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

### 5. Run your own blog

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
