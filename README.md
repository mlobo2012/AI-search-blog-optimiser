# AI Search Blog Optimiser

## TL;DR

Give AI Search Blog Optimiser a company blog URL. It indexes the blog, learns and reuses the brand voice, reads Peec MCP data, creates GEO recommendations, and uses a writer agent to turn existing posts into optimised articles.

It is built for teams that want to refresh owned content every week or month as AI results change, without manually reviewing every prompt, competitor page, cited source, and article rewrite.

Impact: turn an existing blog into a repeatable AI-search optimisation loop, so product marketers and content teams can improve 40, 50, or 100 articles with the same process instead of doing one-off audits.

## Quick Start

Run this in Claude Cowork:

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 2
```

For your own blog:

```text
/blog-optimiser https://your-company.com/blog --max-articles 10
```

What happens:

- the dashboard opens for the run
- the blog index is crawled
- the plugin pulls article content from the URLs it finds
- brand voice is generated and saved for reuse in later runs
- Peec data is used to find where the brand is missing in AI answers
- competitor and top-cited source patterns are used to shape the recommendations
- recommendations are passed to a writer agent to create an optimised article
- you get markdown, HTML, schema, diff, handoff notes, and a quality manifest

## What Problem Does This Solve?

Owned content matters for AI search, but most company blogs were not written for answer engines.

Product marketers, content teams, SEO teams, PR teams, and agencies now have to answer questions like:

- Are we mentioned when buyers ask ChatGPT or Perplexity about our category?
- Which competitors are being cited instead?
- Which third-party pages are AI engines trusting?
- What structure or semantics do those cited pages have that our article is missing?
- Can we improve our existing blog post instead of commissioning a new one?

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

That may be manageable for one or two posts. It breaks down across 40, 50, or 100 articles. At that scale it is not possible to maintain manually as a dynamic system that keeps improving every week and month as the category and market move.

AI Search Blog Optimiser automates the upstream work: crawling your pages, reading Peec research, comparing against competitor and top-cited pages, generating recommendations, and then passing those recommendations into a writer agent that creates the optimised article.

It is a workflow for repurposing what you already own.

## How It Works

You give it the blog URL.

The crawler indexes the blog and pulls article content. Run it in batches of 5-10 articles when you want a focused review, or run larger batches when you are ready to work through the whole blog.

Then the workflow runs in stages:

1. **Crawl the blog** - discovers article URLs from the blog index and saves the source content.
2. **Extract brand voice** - builds a reusable voice baseline for that site.
3. **Read Peec MCP gaps** - pulls the relevant Peec project, tracked prompts, AI engine visibility, share of voice, sentiment, ranking position, competitor mentions, cited domains, source gaps, AI response excerpts, and Peec action opportunities.
4. **Build evidence** - gathers the claims, sources, reviewer signals, and internal links the rewrite is allowed to use.
5. **Generate recommendations** - creates a practical optimisation plan: TL;DR, prompt-shaped headings, missing claims, source-backed evidence, internal links, FAQ/schema, trust block, sentiment fixes, engine-specific tactics, and off-page or comparison-page opportunities where Peec shows a gap.
6. **Create the optimised article** - the writer agent turns the recommendation list and original article into a new article with better semantics, structure, content language, evidence placement, and schema.
7. **Check the article package** - confirms schema, FAQ coverage, evidence, trust signals, internal links, recommendation coverage, and quality gate status.

The important part is the waterfall: blog URL in, articles crawled, brand voice generated or reused, Peec MCP visibility gaps read, cited competitors and sources compared, recommendations generated, writer agent creates the optimised article, content team gets the handoff.

Instead of stopping at "here are recommendations", the workflow carries the work into an optimised article package.

## Granola Example

The example run used:

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 2
```

It processed:

- `Granola Chat just got smarter`
- `Granola raises $125M to put your company's context to work`

### 1. Source Blog Post

The crawler pulled the original Granola Chat article. The post was called "Granola Chat just got smarter", written by Jack, and opened by announcing a smarter and faster Granola Chat.

The article had useful product information, but it was written like a launch post. It did not directly answer the buyer prompts the brand needed to win.

### 2. Peec-Backed Gap Analysis

The workflow matched the post to 3 tracked prompts and found:

- ChatGPT visibility was about 4.5%.
- Perplexity visibility was 0%.
- Google AI Overview visibility was about 38%.
- ChatGPT sentiment floor was 59.
- The dominant cited content shape was listicles.
- Granola had 0% owned coverage for that dominant content shape.

The insight: Granola's own blog post was not competing with the listicles and competitor pages that answer engines already trusted.

### 3. Recommendations

The recommendation agent did not produce vague advice like "improve SEO".

It produced concrete changes:

- Add a clear TL;DR that states what changed, what Granola Chat does, and why inline citations make it auditable.
- Add a "Who it is for" or "Works with" section naming Google Meet, Zoom, and Microsoft Teams.
- Replace vague capability language with a specific claim about cross-meeting search, Team Space, and inline citations.
- Add source-backed evidence for the claims that were previously unsupported.
- Reshape headings around the exact questions buyers are likely to ask.

This is the difference: recommendations are based on Peec visibility data, top-cited source patterns, competitor presence, and the article's own structure.

### 4. Optimised Article

The writer agent then used the recommendations and source article to create a new optimised article.

It added a clear TL;DR:

> We've rebuilt Granola Chat from the ground up as an agentic assistant. It searches across all your meeting notes - personal notes, Team Space, and privately shared notes - and returns answers with inline citations that link to the source meeting. Works with Google Meet, Zoom, and Microsoft Teams.

It also reshaped the article around answer-style sections:

- How does Granola Chat search across all your past meetings?
- Who is Granola Chat for, and which meeting platforms does it support?
- How does Granola turn meeting notes into team knowledge?

The output is not just a report. It is an article your content team can review, edit, and publish. The run also creates a quality manifest so the team can see whether evidence, schema, FAQ, trust, internal links, and recommendation coverage passed.

## What You Get Back

For each article, the workflow returns:

- the original article capture
- the Peec MCP gap analysis
- the evidence pack
- the recommendation list
- the optimised markdown article
- rendered HTML with embedded schema
- standalone schema JSON
- a diff from the original article
- a handoff note for the content team
- a manifest showing what passed and what blocked

## Why Run This Weekly?

AI search changes quickly.

Competitors get added to roundups. New Reddit threads appear. Product pages get cited. Sentiment shifts. Your own blog might already have the right raw material, but not the right structure.

This workflow lets a product marketer or content lead run the same process every week:

1. Crawl the blog.
2. Reuse the saved brand voice.
3. Pull fresh Peec visibility data.
4. Find which owned posts can be improved.
5. Generate recommendations at scale.
6. Let the writer agent turn those recommendations into optimised articles.
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
- ready vs blocked status

### 5. Run your own blog

```text
/blog-optimiser https://your-company.com/blog --max-articles 10
```

Then review:

```text
run-summary.md
outputs/recommendations/
outputs/optimised/
```

If an article is blocked, read the reason first. A blocked article usually means the system could not find enough evidence, trust, or source support to ship a defensible rewrite.
