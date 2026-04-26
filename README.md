# AI Search Blog Optimiser

## TL;DR

Give AI Search Blog Optimiser a company blog URL. It indexes the blog, learns and reuses the brand voice, reads Peec MCP data, creates GEO recommendations, and uses a writer agent to turn existing posts into optimised articles.

Most company blogs were written for Google search, not for AI answers, citations, and prompt-shaped buyer questions. AI Search Blog Optimiser helps product marketers, SEO teams, SEO/GEO agencies, and content leads migrate existing owned content forward into GEO.

It turns manual AI-search research and rewriting into a repeatable optimisation loop: review owned content every 2-4 weeks, identify which posts are falling behind competitors or missing from AI answers, and refresh the pages that can win back visibility.

Impact: improve 40, 50, or 100 existing articles with the same evidence-led process so the blog stays current with the category, what is working for the brand, and what is working for the competition.

## Quick Start

Run this in Claude Cowork:

```text
/blog-optimiser https://www.granola.ai/blog --max-articles 3
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

Most company blogs were written for Google search, not for AI answers, citations, and prompt-shaped buyer questions.

AI Search Blog Optimiser is for product marketers, SEO teams, SEO/GEO agencies, and content leads who need to migrate existing owned content forward into GEO and keep blog posts visible in AI search.

Teams currently have to manually inspect where their brand appears, which competitors are mentioned instead, which sources AI engines trust, and what each article is missing. Product marketers, content teams, SEO teams, PR teams, and agencies now have to answer questions like:

- Are we mentioned when buyers ask ChatGPT or Perplexity about our category?
- Which competitors are being cited instead?
- Which third-party pages are AI engines trusting?
- What structure or semantics do those cited pages have that our article is missing?
- Can we improve our existing blog post instead of commissioning a new one?

Doing this manually is slow.

Instead of manually checking ChatGPT, Perplexity, Gemini, Claude, and Google AI results, inspecting where the brand appears, which competitors are mentioned instead, which sources AI engines trust, and what each article is missing, the work usually looks like this:

1. Run buyer prompts across ChatGPT, Perplexity, Google AI Overview, Gemini, Claude, and Copilot.
2. Capture which brands appear and which sources get cited.
3. Open competitor pages and top-cited editorial pages.
4. Compare their structure, schema, FAQ coverage, trust signals, evidence, and phrasing.
5. Decide what your article is missing.
6. Turn that into a digestible recommendation list.
7. Hand it to a writer or product marketer.
8. Rewrite the article.
9. Check that the rewrite added the TL;DR, evidence, links, schema, FAQ, trust block, and prompt-shaped sections.
10. Repeat every few weeks because competitors publish, category language shifts, product claims change, and AI engines update which owned pages they trust.

That may be manageable for one or two posts. It breaks down across 40, 50, or 100 articles. At that scale it is not possible to maintain manually as a dynamic system that keeps improving every week and month as the category and market move.

AI Search Blog Optimiser automates the upstream work: crawling your pages, reading Peec research, comparing against competitor and top-cited pages, generating recommendations, and then passing those recommendations into a writer agent that creates the optimised article.

It replaces the manual research and rewrite loop with a repeatable GEO workflow for existing owned content. It helps teams refresh existing articles so the blog stays current with the category, what is working for the brand, and what is working for the competition.

## How It Works

You give the Claude Cowork plugin a blog URL and a Peec project ID.

It crawls the blog, extracts a reusable site-level brand voice, reads Peec MCP data on visibility gaps, competitors, cited sources, sentiment, and prompts, then generates evidence-grounded recommendations. Run it in batches of 5-10 articles when you want a focused review, or run larger batches when you are ready to work through the whole blog.

A writer agent turns those recommendations into GEO-optimised article packages with answer-first TL;DRs, prompt-shaped headings, trust blocks, semantic structure, internal links, FAQ/schema coverage, inline evidence, markdown, HTML, standalone schema, diffs, handoff notes, and a quality manifest ready for your content team to review and integrate.

Then the workflow runs in stages:

1. **Crawl the blog** - discovers article URLs from the blog index and saves the source content.
2. **Extract brand voice** - builds a reusable voice baseline for that site.
3. **Read Peec MCP gaps** - pulls the relevant Peec project, tracked prompts, AI engine visibility, share of voice, sentiment, ranking position, competitor mentions, cited domains, source gaps, AI response excerpts, and Peec action opportunities.
4. **Build evidence** - gathers the claims, sources, reviewer signals, and internal links the rewrite is allowed to use.
5. **Generate recommendations** - creates a practical optimisation plan: TL;DR, prompt-shaped headings, missing claims, source-backed evidence, internal links, FAQ/schema, trust block, sentiment fixes, engine-specific tactics, and off-page or comparison-page opportunities where Peec shows a gap.
6. **Create the optimised article** - the writer agent turns the recommendation list and original article into a GEO-optimised article package with better semantics, structure, content language, evidence placement, internal links, and schema.
7. **Check the article package** - confirms schema, FAQ coverage, evidence, trust signals, internal links, recommendation coverage, quality gate status, and the handoff assets your content team can review and integrate.

The important part is the waterfall: blog URL in, articles crawled, brand voice generated or reused, Peec MCP visibility gaps read, cited competitors and sources compared, recommendations generated, writer agent creates the optimised article, content team gets the handoff.

Instead of stopping at "here are recommendations", the workflow carries the work into an optimised article package with markdown, HTML, standalone schema, diffs, handoff notes, and a pass/block quality manifest.

## Granola Example

The example run used a focused batch of 3 Granola posts:

- `Introducing Granola MCP`
- `Delete parts of a transcript`
- `Sign in with Microsoft is here`

These are better examples because each article maps to a real GEO prompt family: integrations and workflows, privacy and security, and Microsoft Teams/Outlook adoption.

### 1. Peec-Backed Gap Analysis

The workflow matched the articles to Granola's Peec prompt library and found different gaps for each page.

For `Introducing Granola MCP`, the relevant prompt family was integrations and workflows. Granola visibility was 8% in ChatGPT and 5% in Perplexity, while Google AI Overview was 60%. Peec showed competing and adjacent sources such as HubSpot, Notelinker, Fireflies, AssemblyAI, and Otter getting cited around workflow prompts.

For `Delete parts of a transcript`, the relevant prompt family was privacy, security, and no-bot meeting capture. Granola had stronger visibility in Google AI Overview, but sentiment was weak across engines: ChatGPT 53, Perplexity 59, and Google AI Overview 63. Peec showed security and legal sources being cited where Granola needed clearer owned evidence.

For `Sign in with Microsoft is here`, the relevant prompt family was Microsoft Teams and workflow adoption. Granola was absent in Perplexity and only 13% visible in ChatGPT, while Google AI Overview was 63%. Peec showed that answer engines were leaning on integration-specific pages and editorial listicles instead of Granola's own launch post.

Across the project, Peec Actions surfaced the same strategic pattern: owned listicles were the largest opportunity, with a High opportunity score, 100% gap, and 0% owned coverage. Editorial listicles and YouTube were also meaningful secondary surfaces.

### 2. Recommendations

The recommendation agent turned those gaps into specific changes.

For the MCP article, it recommended:

- Add an answer-first TL;DR that names Claude, ChatGPT, Cursor, Linear, HubSpot, and meeting context.
- Rewrite headings around integration prompts such as Jira/Linear workflows, CRM updates, Notion workflows, and cross-tool meeting context.
- Add an owned integrations/listicle play because Peec showed owned listicles as the largest gap.

For the transcript-deletion article, it recommended:

- Explain the security value in the TL;DR: transcript deletion controls what Granola Chat can surface before a note is shared.
- Replace soft "good habit" language with concrete control language: delete transcript chunks, regenerate the note, pause transcription, and cite SOAISEC Labs.
- Add visible trust and evidence from Granola Security, Granola's data FAQ, SOAISEC Labs, and the source article.

For the Microsoft article, it recommended:

- Retitle the page around Microsoft Teams and Outlook demand, not just sign-in.
- Add named Microsoft evidence and setup language to close the Perplexity zero-visibility gap.
- Add a comparison-style table showing Microsoft account/SSO, Outlook calendar, Teams reminders, and searchable meeting notes.

### 3. Optimised Article Sections

The writer agent then generated article packages from the recommendations.

For `Introducing Granola MCP`, the new TL;DR became:

> Granola MCP lets Claude, ChatGPT, Cursor, and other MCP clients use your meeting context when you ask. Instead of copying notes between tools, teams can create Linear tickets, update CRM notes, draft proposals, and use discovery conversations as context.

It also added answer-style sections:

- What does Granola MCP let AI apps do with meeting context?
- Which workflows can Granola MCP support?
- How do you set up Granola MCP?
- Why is this rewrite more citation-ready?

For `Delete parts of a transcript`, the new TL;DR became:

> Granola lets you delete specific transcript chunks while keeping the rest of a meeting note intact. That matters before sharing because Granola Chat can use transcript context. Delete sensitive details, regenerate the note, or pause transcription before discussing private information.

It also added sections that make the privacy value extractable:

- What changes when you delete part of a Granola transcript?
- When should you delete transcript chunks before sharing?
- Which evidence makes the privacy claim stronger?
- How should teams use this as a shared-note habit?

For `Sign in with Microsoft is here`, the new TL;DR became:

> Granola now supports Microsoft account or SSO sign-in, Outlook calendar context, and smoother Teams meeting workflows. Microsoft-based teams can see events in Granola, join Teams calls from reminders, and search meeting notes after the conversation.

It also added Microsoft-specific structure:

- What does Sign in with Microsoft change for Granola users?
- How does Granola support Microsoft Teams meetings?
- Why does this article need more evidence for Perplexity and ChatGPT?
- How does this help teams search meeting knowledge later?

The dashboard quality gate marked all 3 article packages as draft-ready at 36/40 after checking TL;DR, trust block, prompt-shaped headings, inline evidence, internal links, FAQ schema, specialized schema, and recommendation coverage.

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

## Regular GEO Blog Optimisation

Owned content is not static in AI search.

The article that wins today can lose ground when a competitor publishes a stronger comparison page, updates a product claim, adds fresher evidence, earns a citation from a trusted source, or starts appearing more consistently across the same prompts your buyers ask. Your own positioning also changes: new features ship, proof points improve, customer language gets sharper, and old launch posts stop matching how the category is now described.

That is why the sweet spot is usually a 2-4 week optimisation cycle. It is frequent enough to catch movement in Peec visibility, competitor presence, cited domains, sentiment, and source gaps, but not so frequent that teams rewrite pages before there is enough signal to learn from.

This workflow lets a product marketer or content lead run the same process every 2-4 weeks:

1. Crawl the blog.
2. Reuse the saved brand voice.
3. Pull fresh Peec visibility, competitor, source, sentiment, and action data.
4. Find which owned posts are missing, stale, under-structured, or being beaten by competitor pages.
5. Generate recommendations for the next batch of 5-10 articles.
6. Let the writer agent turn those recommendations into optimised articles.
7. Send markdown and handoff notes to the content team.

That is the core value: not a one-off audit, but a repeatable owned-content optimisation loop that keeps your blog aligned with how the category, your brand, and competitor visibility are moving.

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
/blog-optimiser https://www.granola.ai/blog --max-articles 3
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
