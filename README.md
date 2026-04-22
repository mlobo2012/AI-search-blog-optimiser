# AI Search Blog Optimiser

A Claude Cowork desktop plugin that rewrites your blog's long tail for **AI-search citation** — grounded in your own live Peec AI gap data, the competitor URLs AI engines are actually citing for your prompts this week, and evidence-backed GEO best practices.

Point it at any blog URL. Get back optimised article drafts with a full evidence trail, rendered in a live local dashboard and exported to disk for your content team.

**Built by [AI Heroes](https://aiheroes.site). Submitted to the [Peec AI MCP Challenge](https://peec-ai.notion.site/Peec-MCP-Challenge-Quick-Start-Kit-33ccac05310f805fb0a8dbcabe1a66d9).**

---

## Quick demo

```
/blog-optimiser https://www.your-blog.com/blog --max-articles 3 --no-gates
```

1. Browser opens to a live AI Heroes branded dashboard.
2. 4 stages run: crawl → brand voice → recommendations → generation.
3. Each article gets a before/after audit score (40-point rubric), 5–7 evidence-grounded recommendations, and an optimised rewrite with FAQPage/Person/Organization schema.
4. Outputs land in `~/.ai-search-blog-optimiser/runs/{timestamp}/optimised/{slug}/` as self-contained folders ready for CMS upload.

Proven on Granola (3 articles): **audit scores 22→35, 24→36, 26→36**; average lift **+11.7 points**. Every recommendation carries a Peec gap signal + Schmidt GEO rule + competitor example + original-article field provenance.

---

## For a content team: install + use

### Prerequisites (one-time)

1. **Claude Desktop** (Cowork) — April 2026 or later
2. **Peec AI MCP** connected in Claude Desktop. Follow the [Peec MCP Quick Start](https://peec-ai.notion.site/Peec-MCP-Challenge-Quick-Start-Kit-33ccac05310f805fb0a8dbcabe1a66d9). You need at least one project with tracked topics, prompts, and competitors.
3. **Crawl4AI MCP** connected as an `stdio→SSE bridge` in Claude Desktop. See [Development setup below](#development-setup) for the exact config.
4. **Python 3.8+** — macOS bundles this by default. Verify with `which python3`.

### Install

1. Download `ai-search-blog-optimiser-v0.2.0.zip` from [the latest release](https://github.com/mlobo2012/AI-search-blog-optimiser/releases).
2. In Claude Desktop → Settings → Plugins → Upload plugin → pick the zip.
3. Confirm the `blog-optimiser-dashboard` MCP shows as connected in Settings → MCP Servers.

### Run

```
/blog-optimiser https://www.your-blog.com/blog --max-articles 3 --no-gates
```

Arguments:

| Flag | Effect |
|---|---|
| *(positional URL)* | Blog index URL. Required unless `--resume`. |
| `--max-articles N` | Cap. Default 20. Use 3 for first test runs. |
| `--no-gates` | Skip human-in-the-loop review pauses between stages. For autonomous runs. |
| `--resume {run_id}` | Resume from last completed stage. Use the timestamp from `~/.ai-search-blog-optimiser/runs/`. |

Typical wall-clock with `--max-articles 20` + 3-way parallelism: ~15 minutes.

### Outputs

```
~/.ai-search-blog-optimiser/runs/{timestamp}/
  state.json              ← Source of truth for pipeline state
  gates.json              ← Gate decisions (if --no-gates not set)
  run-summary.md          ← Aggregate table, before/after scores
  articles/{slug}.json    ← Per-article structural fingerprint
  recommendations/{slug}.json   ← 5–7 grounded recs per article
  optimised/{slug}/
    {slug}.md             ← CMS-ready markdown
    {slug}.html           ← Styled preview with schema embedded
    {slug}.schema.json    ← Standalone JSON-LD payload
    {slug}.handoff.md     ← Review brief for content team
    {slug}.diff.md        ← What changed vs original
```

---

## Architecture

Slash command → skill running in main session → parallel leaf sub-agents. No orchestrator sub-agent. See [Implementation nuances](#implementation-nuances--11-hard-lessons) for why.

```
┌──────────────────────────────────────────────────────────────────┐
│  User: /blog-optimiser https://www.granola.ai/blog              │
└────────────────────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
         ┌──────────────────────────────────────────────┐
         │  MAIN SESSION (Opus 4.7, 1M context)         │
         │  loads skills/blog-optimiser-pipeline/       │
         │  SKILL.md and runs these stages:             │
         └───┬──────────────────────────────────────────┘
             │
 Stage 0/1 ──┼─▶  mcp__blog-optimiser-dashboard__open_dashboard   (main-session only)
             ├─▶  mcp__peec__list_projects → match domain → register_run
 Stage 2   ──┼─▶  Task(blog-crawler)                              ← Haiku 4.5
 Stage 3   ──┼─▶  Task(voice-extractor)                           ← Sonnet 4.6
 Stage 4   ──┼─▶  Task(recommender) × N (parallel batches of 3)   ← Opus 4.7
             │       └─▶ Task(peec-gap-reader) + Task(competitor-crawler)
 Stage 5   ──┼─▶  Task(generator) × N (parallel batches of 3)     ← Opus 4.7
 Stage 6   ──┴─▶  write run-summary.md + final state push
                                     │
                                     ▼
┌─────────────────────────────────┐  ┌──────────────────────────────┐
│  Disk (source of truth)         │  │  Dashboard HTTP daemon       │
│  ~/.ai-search-blog-optimiser/   │  │  detached subprocess          │
│    runs/{ts}/state.json         │◀─┤  reads disk; polls 1.5s       │
│    runs/{ts}/articles/*.json    │  │  lockfile: dashboard.lock     │
│    runs/{ts}/recommendations/*  │  │  survives MCP restarts        │
│    runs/{ts}/optimised/*        │  │  http://127.0.0.1:{port}/     │
│    brands/{peec_id}/*.md        │  │  Live UI with AI Heroes theme │
└─────────────────────────────────┘  └──────────────────────────────┘
```

### Directory tree

```
AI-search-blog-optimiser/
├── .claude-plugin/
│   └── plugin.json             # Manifest: name, version, description
├── .mcp.json                   # Declares the embedded dashboard MCP (stdio)
├── commands/
│   └── blog-optimiser.md       # Slash command entry — loads skill in main session
├── skills/
│   ├── blog-optimiser-pipeline/
│   │   └── SKILL.md            # Canonical 7-stage orchestration playbook
│   └── peec-gap-read/
│       └── SKILL.md            # Reusable Peec MCP recipe
├── agents/                     # Leaf sub-agents (Task-invocable)
│   ├── blog-crawler.md         # Haiku — Crawl4AI extraction
│   ├── voice-extractor.md      # Sonnet — brand voice artefact
│   ├── peec-gap-reader.md      # Sonnet — Peec gap analysis
│   ├── competitor-crawler.md   # Haiku — competitor URL structural crawl
│   ├── recommender.md          # Opus — synthesis with evidence trails
│   └── generator.md            # Opus — augment-not-rewrite article generation
├── dashboard/
│   ├── server.py               # MCP stdio + detached HTTP daemon (stdlib only)
│   ├── index.html              # Live dashboard (Tailwind + Alpine via CDN)
│   ├── welcome.html            # No-run state
│   └── assets/
│       ├── ai-heroes.css       # AI Heroes brand tokens
│       ├── fonts/              # Miftah + Outfit-Variable (from ai-heroes-website)
│       └── img/                # Logo + icon SVGs
├── config/
│   └── brand-config.example.yaml
├── tests/
│   └── dashboard_e2e_test.py   # MCP stdio + HTTP smoke test
├── CHANGELOG.md                # Version notes (v0.1.0 → v0.2.0)
├── LICENSE                     # Apache 2.0 + Commons Clause
└── README.md                   # this file
```

### Tech stack

- **Runtime:** Claude Cowork (desktop) with Opus 4.7 / 4.6 (1M context), Sonnet 4.6, Haiku 4.5 via plugin-defined sub-agents
- **Plugin surface:** `.claude-plugin/plugin.json`, `.mcp.json`, `commands/`, `skills/`, `agents/`
- **Local HTTP dashboard:** Python 3 stdlib only (`http.server` + `socketserver` + `subprocess`). Zero pip deps. ~550 lines in one file.
- **Frontend:** Tailwind CSS + Alpine.js, both via CDN. No build step.
- **Bundled fonts:** Miftah (display) + Outfit Variable (body) — AI Heroes brand
- **External MCPs (user must connect):** Peec AI MCP, Crawl4AI MCP
- **Embedded MCP (ships with plugin):** `blog-optimiser-dashboard` — exposes 10 tools: `open_dashboard`, `get_dashboard_url`, `register_run`, `update_state`, `list_runs`, `get_decisions`, `show_banner`, `get_paths`, `set_gate`, `get_gates`

### Pipeline stages

| # | Stage | Agent | Model | Typical time | Outputs |
|---|---|---|---|---|---|
| 0 | Prereq + dashboard | main session | Opus 4.7 | 5s | `dashboard.lock`, browser open |
| 1 | Peec project resolve | main session | Opus 4.7 | 5–30s | `state.json` with `brand.peec_project_id` |
| 2 | Blog crawl | `blog-crawler` | Haiku 4.5 | 60–120s | `articles/*.json`, `media/*` |
| 3 | Brand voice | `voice-extractor` | Sonnet 4.6 | 30–60s | `brands/{peec_id}/brand-voice.md` |
| 4 | Recommendations | `recommender` × N (cap=3 concurrent) | Opus 4.7 | ~2–4 min per batch of 3 | `recommendations/{slug}.json`, `gaps/{slug}.json`, `competitors/{slug}.json` |
| 5 | Generate | `generator` × N (cap=3 concurrent) | Opus 4.7 | ~1–2 min per batch of 3 | `optimised/{slug}/{md,html,schema,handoff,diff}` |
| 6 | Finalise | main session | — | 5s | `run-summary.md`, final `state.json` |

### The evidence trail (why every recommendation is credible)

Each of the 5–7 recommendations per article ships with all four evidence slots populated:

```json
{
  "id": "rec-1",
  "fix": "Add a 30-60 word trust block above the fold directly answering 'how do I take good meeting notes with AI'...",
  "severity": "critical",
  "effort": "<1h",
  "expected_lift_per_engine": { "chatgpt": "+0.8 citation rate", "perplexity": "+0.3", "google_ai_mode": "+0.5" },
  "evidence": {
    "peec_gap": {                                   // ← LIVE data, your own Peec project
      "prompt": "how do I take good meeting notes with AI",
      "engines_lost": ["perplexity", "chatgpt"],
      "cited_competitors": ["otter.ai/blog/take-better-notes"],
      "brand_visibility_baseline": { "chatgpt": 0.12, "perplexity": 0.0 }
    },
    "schmidt_rule": "blog-optimiser-pipeline#1 (trust block at top)",       // ← GEO best-practice citation
    "competitor_example": {                          // ← What competitors are doing
      "url": "otter.ai/blog/take-better-notes",
      "excerpt": "The best meeting notes capture decisions...",
      "evidence_of_citation_rate": "cited 2.1x on ChatGPT for this prompt"
    },
    "step1_field": "structure.heading_tree[0]"      // ← Original article's exact failing field
  },
  "auto_fix": { "action": "prepend_block", "payload": {...} }               // ← Generator consumes this
}
```

---

## Implementation nuances — 11 hard lessons

Every rule here prevents a shipped-version regression. If you skip these, you'll ship `v0.1.0` and immediately need to rewrite. See also `~/.claude/skills/plugin-development/SKILL.md` for the generalised pattern.

1. **Plugin install dir is READ-ONLY for sub-agents** in Cowork's sandbox. `${CLAUDE_PLUGIN_ROOT}/runs/` writes silently no-op. All writable state lives under `$HOME/.ai-search-blog-optimiser/`. Static assets (HTML, CSS, fonts) stay under plugin root (read access is fine).

2. **Claude Desktop MCP config only supports `stdio`.** `type: "sse"` or `type: "http"` in `claude_desktop_config.json` is silently rejected. Use `mcp-remote` as a stdio→SSE bridge for SSE servers like Crawl4AI.

3. **Claude Desktop spawns MCPs with empty PATH.** `command: "npx"` fails with "No such file or directory" in a log the user never sees. Use **absolute path** to executables + explicit `env.PATH` including node bin dir.

4. **Desktop side effects (browser open, notifications) ONLY fire from main-session MCP calls.** Sub-agent calls to `open_dashboard` are silently dropped at the Cowork sandbox boundary. That's why v0.2 removed the `orchestrator` sub-agent and makes the main session itself run the orchestration skill directly.

5. **MCP stdio processes get killed on idle + session boundaries.** A daemon thread inside the MCP process dies with it; port changes on reconnect. The dashboard uses `subprocess.Popen(start_new_session=True)` to detach the HTTP daemon with a `dashboard.lock` (PID + port). Next MCP spawn reuses if healthy, respawns if stale. URL stays stable.

6. **MCP is a transient comms channel, not a state channel.** When MCP disconnects mid-run, `update_state` pushes are lost. The main session writes `state.json` **directly via the Write tool** from disk; MCP push is a best-effort browser wake-up signal only. Disk is the source of truth.

7. **1M Cowork context still compacts at turn boundaries** when accumulated sub-agent summaries overflow. Every sub-agent returns ≤300 tokens to the main session. All artefacts go to disk; main carries paths + counts only.

8. **Task parallelism requires a single message.** Multiple `Task(...)` calls spread across messages run serially. The skill explicitly instructs the main session to dispatch 3 Task calls in one assistant message per batch.

9. **`osascript` + `screencapture` can't automate Claude Desktop from a sandboxed terminal.** Conductor lacks Accessibility + Screen Recording permissions. Observability is via `~/Library/Logs/Claude/main.log` + `state.json` + HTTP endpoints — no screenshots needed.

10. **Electron apps (Cowork) hide their AX tree.** Only ~12 top-level nodes visible. Don't script Claude Desktop UI — test the plugin via its MCPs + disk state directly.

11. **Main session IS the orchestrator. Do NOT name an "orchestrator" sub-agent.** The command loads the skill; the skill's instructions run in the main session; sub-agents are leaf workers. A handoff to a sub-agent breaks dashboard auto-open, parallel fan-out, and introduces context compaction.

---

## Development setup

Target audience: another engineer who wants to hack on this plugin.

### 1. Clone

```bash
git clone https://github.com/mlobo2012/AI-search-blog-optimiser.git
cd AI-search-blog-optimiser
```

### 2. Install dev dependencies

None. The plugin is stdlib-only Python + vanilla HTML/JS. Verify:

```bash
python3 --version     # ≥ 3.8
python3 -m py_compile dashboard/server.py   # must exit 0
```

### 3. Wire up MCPs in Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` to add the Peec + Crawl4AI MCPs. Minimal reference (adjust paths to your system):

```json
{
  "mcpServers": {
    "peec": {
      "type": "http",
      "url": "https://api.peec.ai/mcp"
    },
    "c4ai-sse": {
      "command": "/Users/YOU/local/node-v22.16.0-darwin-arm64/bin/npx",
      "args": ["-y", "mcp-remote", "http://localhost:11235/mcp/sse", "--transport", "sse-only"],
      "env": {
        "PATH": "/Users/YOU/local/node-v22.16.0-darwin-arm64/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
      }
    }
  }
}
```

> **Note:** `peec` uses `type: "http"` because Peec provides an official hosted HTTP MCP. `c4ai-sse` uses the stdio→SSE bridge because it's a locally-hosted SSE server. See nuances #2 and #3 above for why the bridge pattern exists.

For Crawl4AI setup, see [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai). Run it via Docker or the Python package — default port 11235.

### 4. Install the plugin for development

Either:
- **Symlink** (recommended for dev): `ln -s $(pwd) ~/.claude/plugins/marketplaces/local-desktop-app-uploads/ai-search-blog-optimiser`
- **Zip + upload**: `zip -r /tmp/plugin.zip .claude-plugin .mcp.json commands agents skills dashboard config tests README.md CHANGELOG.md LICENSE -x "*.DS_Store" "runs/*"` then upload via Claude Desktop's plugin uploader

Fully quit Claude Desktop (⌘Q) + reopen after either install method.

### 5. Run the smoke test

```bash
python3 tests/dashboard_e2e_test.py
```

This spawns the MCP stdio server, verifies it exposes all 10 tools, registers a run, sets a gate, resolves it via the HTTP endpoint (simulating the Continue button), and cleans up. Takes ~5 seconds. Must print `ALL GREEN`.

### 6. Live test

In Claude Desktop:

```
/blog-optimiser https://www.granola.ai/blog --max-articles 3 --no-gates
```

Observability:

```bash
# Watch Claude Desktop's agent activity
tail -f ~/Library/Logs/Claude/main.log | grep -iE "blog-optimiser|Task|peec|c4ai"

# Watch our MCP server's stderr
tail -f ~/Library/Logs/Claude/mcp-server-blog-optimiser-dashboard.log

# Watch pipeline state update live
watch -n 2 'ls -t ~/.ai-search-blog-optimiser/runs/ | head -1 | xargs -I {} cat ~/.ai-search-blog-optimiser/runs/{}/state.json | python3 -m json.tool | head -40'
```

### 7. Iterate

- Edit `dashboard/server.py` → `/plugin reload` in Claude Desktop (or quit+reopen)
- Edit `skills/blog-optimiser-pipeline/SKILL.md` → takes effect on next `/blog-optimiser` invocation
- Edit `agents/{name}.md` → same
- Edit `dashboard/index.html` → refresh the browser tab

If something's broken, run `bash ~/.claude/skills/plugin-doctor/run.sh ai-search-blog-optimiser` — it runs 8 diagnostic checks in order and reports the first failure with a concrete fix.

---

## Privacy

Everything runs on your machine except what goes to:

- **Claude** (via Claude Desktop) — agent reasoning, article text, recommendations
- **Peec AI MCP** — your existing connection, per your Peec account
- **Crawl4AI MCP** — your local instance (or whatever host you configured)
- **CDNs** — the dashboard HTML loads Tailwind + Alpine from jsdelivr; no data leaves

No telemetry. No lead tracking. Nothing leaves unless you explicitly export from `~/.ai-search-blog-optimiser/runs/`.

---

## Versioning + releases

See `CHANGELOG.md` for version notes. Current release: **v0.2.0**.

Release process:

```bash
# 1. Bump version in .claude-plugin/plugin.json
# 2. Update CHANGELOG.md
# 3. Build zip
rm -f ~/Downloads/ai-search-blog-optimiser-v{VERSION}.zip
zip -r ~/Downloads/ai-search-blog-optimiser-v{VERSION}.zip \
  .claude-plugin .mcp.json commands agents skills dashboard config tests \
  README.md CHANGELOG.md LICENSE .gitignore \
  -x "*.DS_Store" "*/__pycache__/*" "runs/*" ".context/*" "*.pyc"
# 4. git commit + tag
git commit -am "v{VERSION}: ..."
git tag v{VERSION}
git push --tags origin main
# 5. gh release create v{VERSION} ~/Downloads/ai-search-blog-optimiser-v{VERSION}.zip
```

---

## License

Apache 2.0 with Commons Clause. See `LICENSE`.

## Contributing

Built by Marco Lobo + Claude Opus for AI Heroes. Issues + PRs welcome.

Reading order before contributing:

1. `CHANGELOG.md` — how we got here
2. `skills/blog-optimiser-pipeline/SKILL.md` — the canonical orchestration playbook
3. `dashboard/server.py` — reference implementation for the detached-daemon + disk-first-state pattern
4. `~/.claude/skills/plugin-development/SKILL.md` — generalised learnings applicable to any Cowork plugin (if you have it installed)

## Built for

[AI Heroes](https://aiheroes.site) · [Peec AI MCP Challenge](https://peec-ai.notion.site/Peec-MCP-Challenge-Quick-Start-Kit-33ccac05310f805fb0a8dbcabe1a66d9)
