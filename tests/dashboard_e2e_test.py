"""Regression tests for the dashboard MCP + HTTP flow.

Run with:
  python3 tests/dashboard_e2e_test.py
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import time
import urllib.error
import unittest
import urllib.request


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = PLUGIN_ROOT / "dashboard" / "server.py"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DashboardServerHarness:
    def __init__(self, env: dict[str, str]):
        self.env = env
        self.proc: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self.stop_dashboard()
        self.proc = subprocess.Popen(
            ["python3", str(SERVER), "--plugin-root", str(PLUGIN_ROOT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            text=True,
            bufsize=1,
        )
        self.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.recv()

    def stop_dashboard(self) -> None:
        subprocess.run(
            ["python3", str(SERVER), "--plugin-root", str(PLUGIN_ROOT), "--stop-dashboard"],
            check=False,
            capture_output=True,
            env=self.env,
            text=True,
        )

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            for stream_name in ("stdin", "stdout", "stderr"):
                stream = getattr(self.proc, stream_name)
                if stream is not None:
                    stream.close()
            self.proc = None
        self.stop_dashboard()

    def send(self, message: dict) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def recv(self) -> dict:
        assert self.proc is not None and self.proc.stdout is not None
        line = self.proc.stdout.readline()
        return json.loads(line)

    def call_tool(self, request_id: int, name: str, arguments: dict | None = None) -> dict:
        payload = dict(arguments or {})
        if name == "register_run" and "peec_project_id" not in payload:
            payload["peec_project_id"] = "gn-demo"
        self.send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": payload},
        })
        envelope = self.recv()
        if "error" in envelope:
            return {"payload": envelope["error"]["message"], "is_error": True}
        response = envelope["result"]
        text = response["content"][0]["text"]
        payload = text if response["isError"] else json.loads(text)
        return {"payload": payload, "is_error": response["isError"]}


class DashboardE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = pathlib.Path(self.tempdir.name) / "data"
        self.home_root = pathlib.Path(self.tempdir.name) / "home"
        self.home_root.mkdir(parents=True, exist_ok=True)
        self.env = os.environ.copy()
        self.env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        self.env["BLOG_OPTIMISER_DATA_ROOT"] = str(self.data_root)
        self.env["HOME"] = str(self.home_root)
        self.harness = DashboardServerHarness(self.env)
        self.harness.start()

    def tearDown(self) -> None:
        self.harness.stop()
        self.tempdir.cleanup()

    def _urlopen(self, url: str):
        return urllib.request.urlopen(url, timeout=2)

    def _seed_voice(self, site_key: str, summary: str = "Warm, concrete, product-literate.") -> None:
        site_dir = self.data_root / "sites" / site_key
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "brand-voice.md").write_text("# Voice\n", encoding="utf-8")
        (site_dir / "voice.json").write_text(json.dumps({
            "site_key": site_key,
            "canonical_blog_url": f"https://www.{site_key}/blog",
            "source_run_id": "2026-04-22T07-45-15",
            "updated_at": "2026-04-22T08:01:00Z",
            "summary": summary,
            "version": 1,
        }), encoding="utf-8")

    def _seed_reviewers(self, site_key: str, reviewers: list[dict] | None = None) -> None:
        site_dir = self.data_root / "sites" / site_key
        site_dir.mkdir(parents=True, exist_ok=True)
        payload = reviewers or [
            {
                "id": "chris-pedregal",
                "full_name": "Chris Pedregal",
                "role": "Cofounder & CEO",
                "credential_summary": "Cofounder of Granola; public product and company spokesperson.",
                "bio_url": "https://www.granola.ai/blog/announcement",
                "image_url": "https://www.granola.ai/_next/image?url=%2Fteam%2Fchris.jpg&w=256&q=75",
                "same_as": ["https://www.linkedin.com/company/meetgranola"],
                "review_areas": ["category", "workflow"],
                "default_for_article_types": ["announcement_update", "pillar"],
                "source": "publicly_verifiable",
                "active": True,
            },
        ]
        (site_dir / "reviewers.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _sample_article_record(self, slug: str = "sample-post", title: str = "Sample Post", url: str | None = None) -> dict:
        article_url = url or f"https://www.granola.ai/blog/{slug}"
        return {
            "slug": slug,
            "url": article_url,
            "fetched_at": "2026-04-23T18:09:38Z",
            "title": title,
            "meta": {
                "title": title,
                "description": "Sample description",
                "canonical": article_url,
                "og": {"title": title, "description": "", "image": "", "type": "article"},
                "twitter": {"card": "summary_large_image", "title": title, "description": "", "image": ""},
                "robots": "follow, index",
                "hreflang": [],
            },
            "schema": {"types_present": ["Article"], "types_missing": [], "raw_ldjson": []},
            "structure": {
                "h1": title,
                "heading_tree": [title],
                "word_count": 1234,
                "atomic_paragraph_ratio": 0.75,
                "tables": [],
                "lists": [],
                "blockquotes": [],
                "faq_blocks_detected": 0,
                "code_blocks": 0,
            },
            "media": {
                "images": [],
                "videos": [],
                "iframes": [],
                "thumbnail": f"media/{slug}/thumb.png",
            },
            "trust": {
                "author": {"name": "Chris Pedregal", "role": "Cofounder & CEO", "photo": "", "linkedin": "", "bio": ""},
                "published_at": "2026-03-25",
                "updated_at": None,
                "credentials_mentioned": [],
                "entities_mentioned": ["Granola"],
            },
            "summary": {"intro_paragraph": "Sample intro paragraph."},
            "links": {"internal": [], "external": [], "inbound_internal": []},
            "cta": {"primary": [], "inline_product_mentions": 0, "shippable_nouns": []},
            "body_md": "# Sample\n\nBody.",
            "raw_html_path": f"raw/{slug}.html",
        }

    def _write_validator_fixture(
        self,
        run: dict,
        *,
        slug: str,
        selected_reviewer: bool,
        faq_mismatch: bool = False,
    ) -> None:
        article_url = f"https://www.granola.ai/blog/{slug}"
        article = {
            "slug": slug,
            "url": article_url,
            "title": "How Granola + Zapier turns meeting notes into workflows",
            "trust": {
                "author": {
                    "name": "Jack",
                    "role": "Marketing",
                },
                "published_at": "2025-07-28",
                "updated_at": "2026-04-23",
            },
            "structure": {"word_count": 1460},
            "body_md": "# Workflow article\n\nBody.\n",
        }
        evidence = {
            "article_slug": slug,
            "mode": "peec-enriched",
            "intent_class": "workflow",
            "reviewer_candidate_id": "chris-pedregal" if selected_reviewer else None,
            "sources": [
                {
                    "url": article_url,
                    "title": "Granola Zapier launch announcement",
                    "source_type": "primary_internal",
                    "trust_tier": "high",
                    "supports": ["trust_block", "workflow_table"],
                },
                {
                    "url": "https://www.granola.ai/chat",
                    "title": "Granola Chat",
                    "source_type": "primary_internal",
                    "trust_tier": "high",
                    "supports": ["internal_links", "product_context"],
                },
                {
                    "url": "https://www.granola.ai/ai-note-taker",
                    "title": "Granola AI notepad",
                    "source_type": "primary_internal",
                    "trust_tier": "high",
                    "supports": ["category_context"],
                },
                {
                    "url": "https://help.zapier.com/hc/en-us/articles/8496106701453-Quick-start-guide",
                    "title": "Zapier quick-start guide",
                    "source_type": "external_destination_doc",
                    "trust_tier": "high",
                    "supports": ["workflow_setup"],
                },
                {
                    "url": "https://knowledge.hubspot.com/records/create-records",
                    "title": "HubSpot records guide",
                    "source_type": "external_destination_doc",
                    "trust_tier": "high",
                    "supports": ["crm_workflows"],
                },
            ],
            "claims": [
                {
                    "id": "claim_01",
                    "claim": "Zapier lets teams automate workflows across connected apps.",
                    "source_url": "https://help.zapier.com/hc/en-us/articles/8496106701453-Quick-start-guide",
                    "source_label": "Zapier quick-start guide",
                    "source_type": "external_destination_doc",
                    "supports_sections": ["tldr", "setup"],
                },
                {
                    "id": "claim_02",
                    "claim": "Granola Chat is part of the product context for follow-up workflows.",
                    "source_url": "https://www.granola.ai/chat",
                    "source_label": "Granola Chat",
                    "source_type": "primary_internal",
                    "supports_sections": ["product_context"],
                },
                {
                    "id": "claim_03",
                    "claim": "Granola positions itself as an AI notepad for meetings.",
                    "source_url": "https://www.granola.ai/ai-note-taker",
                    "source_label": "Granola AI notepad",
                    "source_type": "primary_internal",
                    "supports_sections": ["category_context"],
                },
            ],
            "evidence_requirements": {
                "minimum_total_sources": 5,
                "minimum_external_sources": 2,
                "minimum_internal_sources": 2,
            },
        }
        recommendations = {
            "article_slug": slug,
            "article_type": "announcement_update",
            "mode": "peec-enriched",
            "geo_contract_version": "v1",
            "captured_article": {
                "url": article_url,
                "title": article["title"],
                "intro_paragraph": "Granola can now push meeting outcomes into downstream workflows.",
                "word_count": 1460,
            },
            "audit": {
                "score_before": 24,
                "score_target": 34,
                "score_max": 40,
            },
            "quality_contract": {
                "universal": [
                    {"key": "tldr_block", "required": True},
                    {"key": "trust_block", "required": True},
                    {"key": "question_headings", "required": True},
                    {"key": "atomic_paragraphs", "required": True},
                    {"key": "inline_evidence", "required": True},
                    {"key": "semantic_html", "required": True},
                    {"key": "chunk_complete_sections", "required": True},
                    {"key": "differentiation", "required": True},
                ],
                "conditional": [
                    {"key": "faq_block", "required": True, "applicable": True},
                    {"key": "faq_schema", "required": True, "applicable": True},
                    {"key": "table_block", "required": True, "applicable": True},
                    {"key": "specialized_schema", "required": True, "applicable": True},
                ],
                "blocking_issues": [],
            },
            "reviewer_plan": (
                {
                    "status": "selected",
                    "reviewer_id": "chris-pedregal",
                    "display_name": "Chris Pedregal",
                    "display_role": "Cofounder & CEO",
                    "reason": "Public full-name spokesperson for workflow and category pages.",
                }
                if selected_reviewer else
                {
                    "status": "missing",
                    "reason": "No valid reviewer selected.",
                }
            ),
            "evidence_plan": {
                "required_source_count": 5,
                "required_external_count": 2,
                "required_internal_count": 2,
                "must_cite_claim_ids": ["claim_01", "claim_02", "claim_03"],
            },
            "internal_link_plan": {
                "minimum_internal_links": 3,
                "targets": [
                    "https://www.granola.ai/chat",
                    "https://www.granola.ai/ai-note-taker",
                    "https://www.granola.ai/pricing",
                ],
            },
            "blueprint": {
                "schema_plan": {
                    "primary_type": "BlogPosting",
                },
            },
            "recommendations": [],
        }
        reviewer_name = "Chris Pedregal" if selected_reviewer else "Jack"
        reviewer_role = "Cofounder & CEO" if selected_reviewer else "Marketing"
        faq_questions = [
            "What changes when Granola connects to Zapier?",
            "Which workflow should teams automate first?",
            "Do teams need to replace their CRM or project tool?",
        ]
        schema_questions = faq_questions[:2] if faq_mismatch else faq_questions
        html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{article["title"]}</title>
    <script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@graph": [
    {{
      "@type": "BlogPosting",
      "headline": "{article["title"]}",
      "datePublished": "2025-07-28",
      "dateModified": "2026-04-23",
      "url": "{article_url}",
      "author": {{
        "@type": "Person",
        "name": "{reviewer_name}",
        "jobTitle": "{reviewer_role}"
      }},
      "publisher": {{
        "@type": "Organization",
        "name": "Granola"
      }}
    }},
    {{
      "@type": "FAQPage",
      "mainEntity": [
        {",".join(json.dumps({"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": "Answer."}}) for question in schema_questions)}
      ]
    }},
    {{
      "@type": "BreadcrumbList",
      "itemListElement": [
        {{"@type": "ListItem", "position": 1, "name": "Home", "item": "https://www.granola.ai"}},
        {{"@type": "ListItem", "position": 2, "name": "Blog", "item": "https://www.granola.ai/blog"}},
        {{"@type": "ListItem", "position": 3, "name": "{article["title"]}", "item": "{article_url}"}}
      ]
    }}
  ]
}}
    </script>
  </head>
  <body>
    <article>
      <h1>{article["title"]}</h1>
      <p>TL;DR: Granola meeting notes can now trigger downstream workflows using cited product and destination-system guidance.</p>
      <div class="trust">
        <p>Reviewed by <strong>{reviewer_name}</strong>, {reviewer_role}. Published 2025-07-28. Reviewed 2026-04-23. Evidence base: Granola Zapier launch announcement, Zapier quick-start guide, Granola Chat, and Granola AI notepad.</p>
      </div>
      <p>Granola's launch post explains the workflow change and cites the <a href="{article_url}">Granola Zapier launch announcement</a>.</p>
      <p>The <a href="https://help.zapier.com/hc/en-us/articles/8496106701453-Quick-start-guide">Zapier quick-start guide</a> explains how connected workflows run across apps.</p>
      <p>The <a href="https://www.granola.ai/chat">Granola Chat</a> page shows how the product keeps post-meeting context available.</p>
      <p>The <a href="https://www.granola.ai/ai-note-taker">Granola AI notepad</a> page reinforces the product positioning for meeting notes.</p>
      <h2>Which workflows should teams automate first?</h2>
      <p>Start with the CRM, project tracker, or hiring tool that already acts as the system of record.</p>
      <table>
        <tr><th>Destination</th><th>Outcome</th></tr>
        <tr><td>HubSpot</td><td>CRM updates</td></tr>
      </table>
      <h2>How does this help customer-facing teams?</h2>
      <p>It removes repetitive copy-paste work after meetings and keeps notes aligned with systems of record.</p>
      <h2>Why does the evidence matter?</h2>
      <p>Linked first-party and destination-system sources make the workflow claims inspectable.</p>
      <p>Explore more in <a href="https://www.granola.ai/chat">Granola Chat</a>, <a href="https://www.granola.ai/ai-note-taker">Granola AI notepad</a>, and <a href="https://www.granola.ai/pricing">Granola pricing</a>.</p>
      <h2>FAQ</h2>
      <h3>{faq_questions[0]}</h3>
      <p>It turns notes into downstream actions using connected apps.</p>
      <h3>{faq_questions[1]}</h3>
      <p>Teams usually begin with their CRM or project tracker.</p>
      <h3>{faq_questions[2]}</h3>
      <p>No. Granola feeds the tools teams already use.</p>
    </article>
  </body>
</html>
"""
        schema = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "BlogPosting",
                    "headline": article["title"],
                    "datePublished": "2025-07-28",
                    "dateModified": "2026-04-23",
                    "url": article_url,
                    "author": {
                        "@type": "Person",
                        "name": reviewer_name,
                        "jobTitle": reviewer_role,
                    },
                    "publisher": {
                        "@type": "Organization",
                        "name": "Granola",
                    },
                },
                {
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": question,
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": "Answer.",
                            },
                        }
                        for question in schema_questions
                    ],
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://www.granola.ai"},
                        {"@type": "ListItem", "position": 2, "name": "Blog", "item": "https://www.granola.ai/blog"},
                        {"@type": "ListItem", "position": 3, "name": article["title"], "item": article_url},
                    ],
                },
            ],
        }
        pathlib.Path(run["articles_dir"], f"{slug}.json").write_text(json.dumps(article, indent=2), encoding="utf-8")
        pathlib.Path(run["evidence_dir"], f"{slug}.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        pathlib.Path(run["recommendations_dir"], f"{slug}.json").write_text(json.dumps(recommendations, indent=2), encoding="utf-8")
        pathlib.Path(run["optimised_dir"], f"{slug}.html").write_text(html, encoding="utf-8")
        pathlib.Path(run["optimised_dir"], f"{slug}.schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        pathlib.Path(run["optimised_dir"], f"{slug}.md").write_text("# Draft\n", encoding="utf-8")
        pathlib.Path(run["optimised_dir"], f"{slug}.diff.md").write_text("# Diff\n", encoding="utf-8")
        pathlib.Path(run["optimised_dir"], f"{slug}.handoff.md").write_text("# Handoff\n", encoding="utf-8")
        self.harness.call_tool(90, "update_state", {
            "run_id": run["run_id"],
            "fragment": {
                "articles": [
                    {
                        "slug": slug,
                        "title": article["title"],
                        "url": article_url,
                        "stages": {
                            "crawl": {"status": "completed", "word_count": 1460},
                            "evidence": {"status": "completed", "source_count": 5},
                            "recommendations": {"status": "completed", "score_before": 24, "score_target": 34},
                            "draft": {"status": "pending"},
                        },
                    }
                ]
            },
        })

    def test_open_dashboard_requires_run_id(self) -> None:
        result = self.harness.call_tool(2, "open_dashboard", {"open_browser": False})
        self.assertTrue(result["is_error"])
        self.assertIn("run_id is required", result["payload"])

    def test_root_is_neutral_home_not_latest_redirect(self) -> None:
        run = self.harness.call_tool(3, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
            "peec_project_id": "gn-demo",
        })["payload"]
        port = int(run["dashboard_url"].split(":")[2].split("/")[0])
        opener = urllib.request.build_opener(NoRedirectHandler)
        response = opener.open(f"http://127.0.0.1:{port}/", timeout=2)
        html = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Fresh-run only", html)
        self.assertIn("View history", html)
        self.assertNotIn(f"/runs/{run['run_id']}/", html)

    def test_register_run_returns_required_paths_and_dashboard_url(self) -> None:
        result = self.harness.call_tool(4, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
            "peec_project_id": "gn-demo",
        })["payload"]
        expected_keys = {
            "run_id",
            "dashboard_url",
            "run_dir",
            "state_path",
            "outputs_dir",
            "articles_dir",
            "evidence_dir",
            "recommendations_dir",
            "optimised_dir",
            "media_dir",
            "raw_dir",
            "gaps_dir",
            "competitors_dir",
            "peec_cache_dir",
            "gates_path",
            "run_summary_path",
            "site_key",
            "voice_baseline",
            "voice_markdown_path",
            "voice_meta_path",
            "reviewers_path",
        }
        self.assertTrue(expected_keys.issubset(result.keys()))
        self.assertEqual(result["site_key"], "granola.ai")
        self.assertTrue(pathlib.Path(result["outputs_dir"]).exists())
        state = json.loads(pathlib.Path(result["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["pipeline"]["prereqs"]["status"], "completed")
        self.assertEqual(state["pipeline"]["evidence"]["status"], "pending")
        self.assertEqual(state["pipeline"]["draft"]["status"], "pending")
        self.assertEqual(state["session"]["mode"], "fresh")
        self.assertFalse((pathlib.Path(result["run_dir"]) / "decisions.json").exists())
        reviewers_path = pathlib.Path(result["reviewers_path"])
        self.assertTrue(reviewers_path.exists())
        self.assertEqual(json.loads(reviewers_path.read_text(encoding="utf-8")), [])

    def test_register_run_requires_peec_project_id(self) -> None:
        result = self.harness.call_tool(4_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
            "peec_project_id": "",
        })
        self.assertTrue(result["is_error"])
        self.assertIn("peec_project_id is required", result["payload"])

    def test_exact_article_urls_are_stored_ordered_and_required(self) -> None:
        requested = [
            "https://www.granola.ai/blog/granola-mcp",
            "https://www.granola.ai/blog/sign-in-with-microsoft",
        ]
        run = self.harness.call_tool(4_2, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
            "article_urls": requested,
            "crawl_backend": "firecrawl",
            "crawl_mcp_server": "firecrawl",
        })["payload"]
        self.assertEqual(run["article_urls"], requested)
        self.assertEqual(run["crawl_backend"], "firecrawl")
        self.assertEqual(run["crawl_mcp_server"], "firecrawl")
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["article_selection"]["mode"], "exact")
        self.assertEqual(state["requested_article_urls"], requested)
        self.assertEqual(state["crawl_backend"]["selected"], "firecrawl")
        self.assertEqual(state["pipeline"]["crawl"]["backend"], "firecrawl")

        self.harness.call_tool(4_3, "record_crawl_discovery", {
            "run_id": run["run_id"],
            "discovered_count": 2,
        })
        self.harness.call_tool(4_4, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("sign-in-with-microsoft", "Sign in with Microsoft", requested[1]),
        })
        self.harness.call_tool(4_5, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("granola-mcp", "Granola MCP", requested[0]),
        })
        result = self.harness.call_tool(4_6, "finalize_crawl", {
            "run_id": run["run_id"],
        })["payload"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["article_slugs"], ["granola-mcp", "sign-in-with-microsoft"])
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual([item["slug"] for item in state["articles"]], ["granola-mcp", "sign-in-with-microsoft"])

        missing_run = self.harness.call_tool(4_7, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
            "article_urls": requested,
        })["payload"]
        self.harness.call_tool(4_8, "record_crawl_discovery", {
            "run_id": missing_run["run_id"],
            "discovered_count": 2,
        })
        self.harness.call_tool(4_9, "record_crawled_article", {
            "run_id": missing_run["run_id"],
            "article": self._sample_article_record("granola-mcp", "Granola MCP", requested[0]),
        })
        missing_result = self.harness.call_tool(4_10, "finalize_crawl", {
            "run_id": missing_run["run_id"],
        })["payload"]
        self.assertEqual(missing_result["status"], "failed")
        self.assertEqual(missing_result["missing_requested_urls"], [requested[1]])
        state = json.loads(pathlib.Path(missing_run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["pipeline"]["crawl"]["status"], "failed")

        extra_result = self.harness.call_tool(4_11, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("unexpected-post", "Unexpected Post", "https://www.granola.ai/blog/unexpected-post"),
        })
        self.assertTrue(extra_result["is_error"])
        self.assertIn("was not requested", extra_result["payload"])

    def test_artifact_tools_persist_article_json_on_host(self) -> None:
        run = self.harness.call_tool(40, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        write_result = self.harness.call_tool(41, "write_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "articles",
            "relative_path": "sample-post.json",
            "data": {
                "slug": "sample-post",
                "title": "Sample Post",
                "body_md": "# Sample",
            },
        })["payload"]
        self.assertTrue(write_result["ok"])
        article_path = pathlib.Path(write_result["absolute_path"])
        self.assertTrue(article_path.exists())
        read_result = self.harness.call_tool(42, "read_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "articles",
            "relative_path": "sample-post.json",
        })["payload"]
        self.assertEqual(read_result["data"]["slug"], "sample-post")
        listed = self.harness.call_tool(43, "list_artifacts", {
            "run_id": run["run_id"],
            "namespace": "articles",
            "suffix": ".json",
        })["payload"]
        self.assertEqual([item["relative_path"] for item in listed["artifacts"]], ["sample-post.json"])

    def test_write_json_artifact_normalizes_stringified_payloads(self) -> None:
        run = self.harness.call_tool(43_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        payload = {
            "slug": "sample-post",
            "title": "Sample Post",
            "body_md": "# Sample",
        }
        write_result = self.harness.call_tool(43_2, "write_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "articles",
            "relative_path": "sample-post.json",
            "data": json.dumps(payload),
        })["payload"]
        stored = pathlib.Path(write_result["absolute_path"]).read_text(encoding="utf-8")
        self.assertTrue(stored.lstrip().startswith("{"))
        read_result = self.harness.call_tool(43_3, "read_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "articles",
            "relative_path": "sample-post.json",
        })["payload"]
        self.assertEqual(read_result["data"]["slug"], "sample-post")

    def test_record_crawled_article_writes_artifact_and_state_atomically(self) -> None:
        run = self.harness.call_tool(43_4, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        article = self._sample_article_record()
        result = self.harness.call_tool(43_5, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": article,
        })["payload"]
        self.assertTrue(pathlib.Path(result["absolute_path"]).exists())
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        saved = next(item for item in state["articles"] if item["slug"] == "sample-post")
        self.assertEqual(saved["title"], "Sample Post")
        self.assertEqual(saved["thumbnail"], "media/sample-post/thumb.png")
        self.assertEqual(saved["stages"]["crawl"]["status"], "completed")
        self.assertEqual(saved["stages"]["crawl"]["word_count"], 1234)

    def test_finalize_crawl_prunes_ghost_rows_and_marks_partial(self) -> None:
        run = self.harness.call_tool(43_6, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(43_7, "record_crawl_discovery", {
            "run_id": run["run_id"],
            "discovered_count": 3,
        })
        self.harness.call_tool(43_8, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("one-post", "One Post"),
        })
        self.harness.call_tool(43_9, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("two-posts", "Two Posts"),
        })
        self.harness.call_tool(43_10, "update_state", {
            "run_id": run["run_id"],
            "fragment": {
                "crawl": {
                    "status": "running",
                    "detail": "legacy top-level crawl blob",
                },
                "articles": [
                    {
                        "slug": "ghost-post",
                        "title": "Ghost",
                        "stages": {"crawl": {"status": "completed", "word_count": 999}},
                    }
                ]
            },
        })
        result = self.harness.call_tool(43_11, "finalize_crawl", {
            "run_id": run["run_id"],
        })["payload"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["persisted_count"], 2)
        self.assertEqual(result["discovered_count"], 3)
        self.assertIn("ghost-post", result["dropped_slugs"])
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(state["articles"]), 2)
        self.assertEqual(state["pipeline"]["crawl"]["status"], "partial")
        self.assertEqual(state["pipeline"]["crawl"]["article_count"], 2)
        self.assertEqual(state["pipeline"]["crawl"]["discovered_count"], 3)
        self.assertNotIn("crawl", state)

    def test_finalize_crawl_recovers_discovered_count_from_detail(self) -> None:
        run = self.harness.call_tool(43_12, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(43_13, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("one-post", "One Post"),
        })
        self.harness.call_tool(43_14, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("two-posts", "Two Posts"),
        })
        self.harness.call_tool(43_15, "update_state", {
            "run_id": run["run_id"],
            "fragment": {
                "pipeline": {
                    "crawl": {
                        "status": "partial",
                        "article_count": 2,
                        "detail": "Crawler discovered 20 articles but only 2 JSON files were written to disk.",
                    }
                }
            },
        })
        result = self.harness.call_tool(43_16, "finalize_crawl", {
            "run_id": run["run_id"],
        })["payload"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["discovered_count"], 20)
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["pipeline"]["crawl"]["discovered_count"], 20)
        self.assertEqual(state["pipeline"]["crawl"]["article_count"], 2)

    def test_artifact_tools_persist_site_voice_files_on_host(self) -> None:
        run = self.harness.call_tool(44, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        markdown_result = self.harness.call_tool(45, "write_text_artifact", {
            "run_id": run["run_id"],
            "namespace": "site",
            "relative_path": "brand-voice.md",
            "content": "# Voice\nWarm and concrete.\n",
        })["payload"]
        meta_result = self.harness.call_tool(46, "write_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "site",
            "relative_path": "voice.json",
            "data": {
                "site_key": "granola.ai",
                "canonical_blog_url": "https://www.granola.ai/blog",
                "source_run_id": run["run_id"],
                "updated_at": "2026-04-22T09:15:00Z",
                "summary": "Warm and concrete.",
                "version": 1,
            },
        })["payload"]
        self.assertTrue(pathlib.Path(markdown_result["absolute_path"]).exists())
        self.assertTrue(pathlib.Path(meta_result["absolute_path"]).exists())
        read_markdown = self.harness.call_tool(47, "read_text_artifact", {
            "run_id": run["run_id"],
            "namespace": "site",
            "relative_path": "brand-voice.md",
        })["payload"]
        self.assertIn("Warm and concrete", read_markdown["content"])
        read_meta = self.harness.call_tool(48, "read_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "site",
            "relative_path": "voice.json",
        })["payload"]
        self.assertEqual(read_meta["data"]["summary"], "Warm and concrete.")

    def test_record_voice_baseline_writes_site_files_and_state(self) -> None:
        run = self.harness.call_tool(48_0, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        result = self.harness.call_tool(48_0_1, "record_voice_baseline", {
            "run_id": run["run_id"],
            "markdown": "# Voice\nWarm and concrete.\n",
            "metadata": {
                "summary": "Warm and concrete.",
                "source_run_id": run["run_id"],
            },
        })["payload"]
        self.assertTrue(pathlib.Path(result["markdown_path"]).exists())
        self.assertTrue(pathlib.Path(result["meta_path"]).exists())
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["voice"]["mode"], "generated")
        self.assertEqual(state["voice"]["summary"], "Warm and concrete.")
        self.assertEqual(state["pipeline"]["voice"]["status"], "completed")

    def test_artifact_tools_persist_site_reviewers_json_on_host(self) -> None:
        run = self.harness.call_tool(48_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        reviewers = [
            {
                "id": "chris-pedregal",
                "full_name": "Chris Pedregal",
                "role": "Cofounder & CEO",
                "review_areas": ["category", "workflow"],
                "default_for_article_types": ["announcement_update"],
                "source": "publicly_verifiable",
                "active": True,
            }
        ]
        write_result = self.harness.call_tool(48_2, "write_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "site",
            "relative_path": "reviewers.json",
            "data": reviewers,
        })["payload"]
        self.assertTrue(pathlib.Path(write_result["absolute_path"]).exists())
        read_result = self.harness.call_tool(48_3, "read_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "site",
            "relative_path": "reviewers.json",
        })["payload"]
        self.assertEqual(read_result["data"][0]["full_name"], "Chris Pedregal")

    def test_record_evidence_pack_writes_artifact_and_stage(self) -> None:
        run = self.harness.call_tool(48_3_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(48_3_2, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("evidence-post", "Evidence Post"),
        })
        evidence = {
            "article_slug": "evidence-post",
            "mode": "voice-rubric",
            "intent_class": "category",
            "reviewer_candidate_id": "chris-pedregal",
            "sources": [
                {"url": "https://www.granola.ai/evidence-post", "title": "Source 1"},
                {"url": "https://docs.example.com/source-2", "title": "Source 2"},
            ],
            "claims": [],
            "evidence_requirements": {"minimum_total_sources": 2, "minimum_external_sources": 1, "minimum_internal_sources": 1},
        }
        result = self.harness.call_tool(48_3_3, "record_evidence_pack", {
            "run_id": run["run_id"],
            "article_slug": "evidence-post",
            "evidence": evidence,
        })["payload"]
        self.assertEqual(result["source_count"], 2)
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        article = next(item for item in state["articles"] if item["slug"] == "evidence-post")
        self.assertEqual(article["stages"]["evidence"]["status"], "completed")
        self.assertEqual(article["stages"]["evidence"]["source_count"], 2)

    def test_record_peec_gap_marks_analysis_stage(self) -> None:
        run = self.harness.call_tool(48_3_3_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        result = self.harness.call_tool(48_3_3_2, "record_peec_gap", {
            "run_id": run["run_id"],
            "article_slug": "gap-post",
            "gap": {
                "article_slug": "gap-post",
                "admissible": False,
                "blocker_reason": "Matched prompt set is too sparse to support a rewrite.",
                "matched_prompts": [{"prompt_text": "granola zapier workflows"}],
            },
        })["payload"]
        self.assertFalse(result["admissible"])
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        article = next(item for item in state["articles"] if item["slug"] == "gap-post")
        self.assertEqual(article["stages"]["analysis"]["status"], "failed")
        self.assertIn("sparse", article["stages"]["analysis"]["blocker_summary"])

    def test_record_competitor_snapshot_updates_analysis_stage(self) -> None:
        run = self.harness.call_tool(48_3_3_3, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        result = self.harness.call_tool(48_3_3_4, "record_competitor_snapshot", {
            "run_id": run["run_id"],
            "article_slug": "comp-post",
            "snapshot": {
                "article_slug": "comp-post",
                "competitors": [
                    {"url": "https://example.com/a"},
                    {"url": "https://example.com/b"},
                ],
            },
        })["payload"]
        self.assertEqual(result["competitor_count"], 2)
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        article = next(item for item in state["articles"] if item["slug"] == "comp-post")
        self.assertEqual(article["stages"]["analysis"]["status"], "completed")
        self.assertEqual(article["stages"]["analysis"]["competitor_count"], 2)

    def test_record_recommendations_writes_artifact_and_stage(self) -> None:
        run = self.harness.call_tool(48_3_4, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(48_3_5, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("rec-post", "Recommendation Post"),
        })
        recommendations = {
            "article_slug": "rec-post",
            "article_type": "announcement_update",
            "mode": "voice-rubric",
            "geo_contract_version": "v1",
            "captured_article": {
                "url": "https://www.granola.ai/blog/rec-post",
                "title": "Recommendation Post",
                "intro_paragraph": "Intro.",
                "word_count": 1234,
            },
            "audit": {"score_before": 22, "score_target": 34, "score_max": 40},
            "category_lens": {"summary": "Voice-rubric fixture.", "topic_cluster": "workflow"},
            "brand_lens": {"summary": "Voice-rubric fixture.", "visibility_per_engine": {}},
            "competition_lens": {"summary": "Voice-rubric fixture.", "by_classification": {}, "strategy_implication": "Improve owned article."},
            "engine_gap_strategy": {},
            "primary_gaps": [],
            "summary": {
                "preset": "announcement_update",
                "audit_before": 22,
                "audit_target": 34,
                "audit_max": 40,
                "primary_geo_gap": "Missing answer-ready structure.",
                "engine_weakness": "general",
                "top_competitors_to_displace": [],
                "highest_leverage_action": "Add answer-ready sections.",
            },
            "matched_prompts": [{"prompt_text": "One"}],
            "recommendation_count": 4,
            "critical_count": 2,
            "recommendations": [
                {
                    "id": "rec-001",
                    "source": "llm",
                    "category": "content_gap",
                    "severity": "critical",
                    "priority": "critical",
                    "title": "One",
                    "signal_types": ["prompt_visibility"],
                    "evidence": ["voice_fixture"],
                    "target_engines": ["chatgpt-scraper"],
                    "per_engine_lift": {"chatgpt-scraper": "Better answer coverage."},
                },
                {
                    "id": "rec-002",
                    "source": "llm",
                    "category": "engine_specific",
                    "severity": "critical",
                    "priority": "critical",
                    "title": "Two",
                    "signal_types": ["engine_pattern_asymmetry"],
                    "evidence": ["voice_fixture"],
                    "target_engines": ["perplexity-scraper"],
                    "per_engine_lift": {"perplexity-scraper": "Clearer citations."},
                },
                {
                    "id": "rec-003",
                    "source": "llm",
                    "category": "content_gap",
                    "severity": "medium",
                    "priority": "medium",
                    "title": "Three",
                    "signal_types": ["gap_chat_excerpt"],
                    "evidence": ["voice_fixture"],
                    "target_engines": ["google-ai-overview-scraper"],
                    "per_engine_lift": {"google-ai-overview-scraper": "Preserve coverage."},
                },
                {
                    "id": "rec-004",
                    "source": "llm",
                    "category": "content_gap",
                    "severity": "medium",
                    "priority": "medium",
                    "title": "Four",
                    "signal_types": ["retrieval_rate"],
                    "evidence": ["voice_fixture"],
                    "target_engines": ["chatgpt-scraper"],
                    "per_engine_lift": {"chatgpt-scraper": "More retrievable chunks."},
                },
            ],
        }
        result = self.harness.call_tool(48_3_6, "record_recommendations", {
            "run_id": run["run_id"],
            "article_slug": "rec-post",
            "recommendations": recommendations,
        })["payload"]
        self.assertEqual(result["recommendation_count"], 4)
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        article = next(item for item in state["articles"] if item["slug"] == "rec-post")
        self.assertEqual(article["stages"]["recommendations"]["status"], "completed")
        self.assertEqual(article["stages"]["recommendations"]["score_target"], 34)
        self.assertEqual(article["stages"]["recommendations"]["critical_count"], 2)

    def test_record_recommendations_backfills_prompt_ids_from_evidence_refs(self) -> None:
        run = self.harness.call_tool(48_3_6_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(48_3_6_2, "record_crawled_article", {
            "run_id": run["run_id"],
            "article": self._sample_article_record("peec-rec-post", "Peec Recommendation Post"),
        })
        prompt_ids = [
            "pr_11111111-1111-1111-1111-111111111111",
            "pr_22222222-2222-2222-2222-222222222222",
            "pr_33333333-3333-3333-3333-333333333333",
        ]
        self.harness.call_tool(48_3_6_3, "record_peec_gap", {
            "run_id": run["run_id"],
            "article_slug": "peec-rec-post",
            "gap": {
                "article_slug": "peec-rec-post",
                "admissible": True,
                "matched_prompts": [{"prompt_id": prompt_id, "prompt_text": f"Prompt {index}"} for index, prompt_id in enumerate(prompt_ids, 1)],
            },
        })
        recommendations = {
            "article_slug": "peec-rec-post",
            "mode": "peec-prompt-matched",
            "audit": {"score_before": 22, "score_target": 34, "score_max": 40},
            "category_lens": {"summary": "Fixture."},
            "brand_lens": {"summary": "Fixture."},
            "competition_lens": {"summary": "Fixture."},
            "engine_gap_strategy": {},
            "primary_gaps": [],
            "summary": {"highest_leverage_action": "Fixture."},
            "recommendations": [
                {
                    "id": "rec-001",
                    "source": "llm",
                    "category": "content_gap",
                    "severity": "critical",
                    "priority": "critical",
                    "signal_types": ["prompt_visibility"],
                    "evidence": [f"peec_prompt_{prompt_id}" for prompt_id in prompt_ids],
                    "target_engines": ["chatgpt-scraper"],
                    "per_engine_lift": {"chatgpt-scraper": "Fixture."},
                },
                {
                    "id": "rec-002",
                    "source": "llm",
                    "category": "engine_specific",
                    "severity": "high",
                    "priority": "high",
                    "signal_types": ["engine_pattern_asymmetry"],
                    "evidence": [f"peec_prompt_{prompt_id}" for prompt_id in prompt_ids],
                    "target_engines": ["perplexity-scraper"],
                    "per_engine_lift": {"perplexity-scraper": "Fixture."},
                },
                {
                    "id": "rec-003",
                    "source": "llm",
                    "category": "content_gap",
                    "severity": "medium",
                    "priority": "medium",
                    "signal_types": ["retrieval_rate"],
                    "evidence": [f"peec_prompt_{prompt_id}" for prompt_id in prompt_ids],
                    "target_engines": ["google-ai-overview-scraper"],
                    "per_engine_lift": {"google-ai-overview-scraper": "Fixture."},
                },
            ],
        }
        result = self.harness.call_tool(48_3_6_4, "record_recommendations", {
            "run_id": run["run_id"],
            "article_slug": "peec-rec-post",
            "recommendations": recommendations,
        })["payload"]
        self.assertEqual(result["recommendation_count"], 3)
        artifact = json.loads(pathlib.Path(run["recommendations_dir"], "peec-rec-post.json").read_text(encoding="utf-8"))
        for item in artifact["recommendations"]:
            self.assertEqual(item["addresses_prompts"], prompt_ids)

    def test_record_recommendations_rejects_wrong_count(self) -> None:
        run = self.harness.call_tool(48_3_7, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        result = self.harness.call_tool(48_3_8, "record_recommendations", {
            "run_id": run["run_id"],
            "article_slug": "bad-rec-post",
            "recommendations": {
                "article_slug": "bad-rec-post",
                "mode": "voice-rubric",
                "audit": {"score_before": 20, "score_target": 32, "score_max": 40},
                "category_lens": {"summary": "Fixture."},
                "brand_lens": {"summary": "Fixture."},
                "competition_lens": {"summary": "Fixture."},
                "engine_gap_strategy": {},
                "primary_gaps": [],
                "summary": {"highest_leverage_action": "Fixture."},
                "recommendations": [
                    {
                        "id": "rec-001",
                        "source": "llm",
                        "category": "content_gap",
                        "severity": "critical",
                        "priority": "critical",
                        "signal_types": ["prompt_visibility"],
                        "evidence": ["fixture"],
                        "target_engines": ["chatgpt-scraper"],
                        "per_engine_lift": {"chatgpt-scraper": "Fixture."},
                    }
                ],
            },
        })
        self.assertTrue(result["is_error"])
        self.assertIn("LLM-source recommendation count", result["payload"])

    def test_read_bundle_text_reads_plugin_scoped_references(self) -> None:
        contract = self.harness.call_tool(48_4, "read_bundle_text", {
            "relative_path": "references/geo-article-contract.md",
        })["payload"]
        recipe = self.harness.call_tool(48_5, "read_bundle_text", {
            "relative_path": "skills/peec-gap-read/SKILL.md",
        })["payload"]
        self.assertIn("GEO Article Contract v1", contract["content"])
        self.assertIn("Peec Gap Read Recipe", recipe["content"])

    def test_run_namespace_text_writes_are_limited(self) -> None:
        run = self.harness.call_tool(49, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        result = self.harness.call_tool(50, "write_text_artifact", {
            "run_id": run["run_id"],
            "namespace": "run",
            "relative_path": "state.json",
            "content": "{}",
        })
        self.assertTrue(result["is_error"])
        self.assertIn("run namespace text writes are limited", result["payload"])

    def test_same_site_second_run_reuses_voice(self) -> None:
        self._seed_voice("granola.ai")
        result = self.harness.call_tool(5, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.assertTrue(result["voice_baseline"]["will_reuse"])
        state = json.loads(pathlib.Path(result["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["voice"]["mode"], "reused")
        self.assertEqual(state["pipeline"]["voice"]["status"], "completed")

    def test_refresh_voice_bypasses_reuse(self) -> None:
        self._seed_voice("granola.ai")
        result = self.harness.call_tool(6, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
            "refresh_voice": True,
        })["payload"]
        self.assertFalse(result["voice_baseline"]["will_reuse"])
        state = json.loads(pathlib.Path(result["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["voice"]["mode"], "pending")
        self.assertEqual(state["pipeline"]["voice"]["status"], "pending")

    def test_different_site_does_not_reuse_prior_voice(self) -> None:
        self._seed_voice("granola.ai")
        result = self.harness.call_tool(7, "register_run", {
            "blog_url": "https://www.other.ai/blog",
        })["payload"]
        self.assertEqual(result["site_key"], "other.ai")
        self.assertFalse(result["voice_baseline"]["will_reuse"])

    def test_malformed_voice_metadata_is_cache_miss(self) -> None:
        site_dir = self.data_root / "sites" / "granola.ai"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "brand-voice.md").write_text("# Voice\n", encoding="utf-8")
        (site_dir / "voice.json").write_text("{not-json", encoding="utf-8")
        result = self.harness.call_tool(8, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.assertFalse(result["voice_baseline"]["exists"])
        self.assertFalse(result["voice_baseline"]["will_reuse"])

    def test_legacy_old_root_is_ignored(self) -> None:
        self.harness.stop()
        del self.env["BLOG_OPTIMISER_DATA_ROOT"]
        legacy_site_dir = self.home_root / ".ai-search-blog-optimiser" / "sites" / "granola.ai"
        legacy_site_dir.mkdir(parents=True, exist_ok=True)
        (legacy_site_dir / "brand-voice.md").write_text("# legacy voice\n", encoding="utf-8")
        (legacy_site_dir / "voice.json").write_text(json.dumps({
            "site_key": "granola.ai",
            "canonical_blog_url": "https://www.granola.ai/blog",
            "source_run_id": "legacy-run",
            "updated_at": "2026-04-21T08:01:00Z",
            "summary": "legacy summary",
            "version": 1,
        }), encoding="utf-8")
        self.harness = DashboardServerHarness(self.env)
        self.harness.start()
        result = self.harness.call_tool(9, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.assertFalse(result["voice_baseline"]["will_reuse"])
        default_data_root = self.home_root / "Library" / "Application Support" / "ai-search-blog-optimiser" / "v3"
        self.assertTrue(str(pathlib.Path(result["run_dir"])).startswith(str(default_data_root)))

    def test_claude_plugin_data_imports_default_legacy_root_once(self) -> None:
        self.harness.stop()
        del self.env["BLOG_OPTIMISER_DATA_ROOT"]
        plugin_data_root = pathlib.Path(self.tempdir.name) / "plugin-data"
        self.env["CLAUDE_PLUGIN_DATA"] = str(plugin_data_root)
        legacy_site_dir = self.home_root / "Library" / "Application Support" / "ai-search-blog-optimiser" / "v3" / "sites" / "granola.ai"
        legacy_site_dir.mkdir(parents=True, exist_ok=True)
        (legacy_site_dir / "brand-voice.md").write_text("# imported voice\n", encoding="utf-8")
        (legacy_site_dir / "voice.json").write_text(json.dumps({
            "site_key": "granola.ai",
            "canonical_blog_url": "https://www.granola.ai/blog",
            "source_run_id": "legacy-run",
            "updated_at": "2026-04-21T08:01:00Z",
            "summary": "imported summary",
            "version": 1,
        }), encoding="utf-8")
        self.harness = DashboardServerHarness(self.env)
        self.harness.start()
        result = self.harness.call_tool(9_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.assertTrue(result["voice_baseline"]["will_reuse"])
        self.assertTrue(str(pathlib.Path(result["run_dir"]).resolve()).startswith(str(plugin_data_root.resolve())))
        marker = plugin_data_root / ".legacy-import.json"
        self.assertTrue(marker.exists())

    def test_update_state_normalizes_common_agent_fragment_shapes(self) -> None:
        run = self.harness.call_tool(51, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(52, "update_state", {
            "run_id": run["run_id"],
            "fragment": {
                "articles": {
                    "sample-post": {
                        "stages": {
                            "recommendations": {
                                "status": "complete",
                                "score": 24,
                            }
                        }
                    }
                },
                "stages": {
                    "draft": {
                        "sample-post": {
                            "status": "complete",
                            "audit_after": 34,
                        }
                    }
                },
            },
        })
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertIsInstance(state["articles"], list)
        article = next(item for item in state["articles"] if item["slug"] == "sample-post")
        self.assertEqual(article["stages"]["recommendations"]["status"], "completed")
        self.assertEqual(article["stages"]["draft"]["status"], "completed")
        self.assertEqual(article["stages"]["draft"]["audit_after"], 34)
        self.assertNotIn("stages", state)

    def test_state_reads_repair_legacy_draft_shape(self) -> None:
        run = self.harness.call_tool(52_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        state_path = pathlib.Path(run["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["articles"] = [
            {
                "slug": "legacy-post",
                "title": "Legacy Post",
                "status": "draft_completed",
                "quality_gate": "passed",
                "audit_before": 22,
                "audit_after": 34,
                "generated_at": "2026-04-23T17:35:00Z",
                "stages": {
                    "recommendations": {
                        "status": "completed",
                        "score_before": 22,
                        "score_target": 34,
                    }
                },
            }
        ]
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        port = int(run["dashboard_url"].split(":")[2].split("/")[0])
        response = self._urlopen(f"http://127.0.0.1:{port}/api/runs/{run['run_id']}/state")
        payload = json.loads(response.read().decode("utf-8"))
        article = payload["articles"][0]
        self.assertEqual(article["stages"]["draft"]["status"], "completed")
        self.assertEqual(article["stages"]["draft"]["quality_gate"], "passed")
        self.assertEqual(article["stages"]["draft"]["audit_after"], 34)
        repaired = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(repaired["articles"][0]["stages"]["draft"]["status"], "completed")

    def test_gate_timeout_is_enforced_server_side(self) -> None:
        run = self.harness.call_tool(53, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(54, "set_gate", {
            "run_id": run["run_id"],
            "gate": "crawl_gate",
            "status": "pending",
            "prompt": "Review crawl output",
            "timeout_seconds": 1,
        })
        time.sleep(1.2)
        gates = self.harness.call_tool(55, "get_gates", {
            "run_id": run["run_id"],
        })["payload"]
        gate = gates["crawl_gate"]
        self.assertEqual(gate["status"], "resolved")
        self.assertEqual(gate["user_action"], "timeout-auto-proceed")
        self.assertEqual(gate["timeout_seconds"], 1)
        self.assertIn("expires_at", gate)

    def test_pipeline_draft_aggregate_is_derived_from_article_stage_truth(self) -> None:
        run = self.harness.call_tool(56, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(57, "update_state", {
            "run_id": run["run_id"],
            "fragment": {
                "pipeline": {
                    "draft": {
                        "status": "completed",
                    }
                },
                "articles": [
                    {
                        "slug": "done-post",
                        "title": "Done Post",
                        "stages": {
                            "evidence": {"status": "completed", "source_count": 5},
                            "draft": {"status": "completed", "audit_after": 34},
                            "recommendations": {"status": "completed", "recommendation_count": 4},
                        },
                    },
                    {
                        "slug": "pending-post",
                        "title": "Pending Post",
                        "stages": {
                            "evidence": {"status": "pending"},
                            "draft": {"status": "pending"},
                            "recommendations": {"status": "pending"},
                        },
                    },
                ],
            },
        })
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["pipeline"]["evidence"]["status"], "partial")
        self.assertEqual(state["pipeline"]["evidence"]["completed_articles"], 1)
        self.assertEqual(state["pipeline"]["evidence"]["total"], 2)
        self.assertEqual(state["pipeline"]["draft"]["status"], "partial")
        self.assertEqual(state["pipeline"]["draft"]["completed_articles"], 1)
        self.assertEqual(state["pipeline"]["draft"]["total"], 2)
        self.assertEqual(state["pipeline"]["recommendations"]["status"], "partial")
        self.assertEqual(state["pipeline"]["recommendations"]["completed_articles"], 1)
        self.assertEqual(state["pipeline"]["recommendations"]["total"], 2)
        pending_article = next(item for item in state["articles"] if item["slug"] == "pending-post")
        self.assertEqual(pending_article["stages"]["draft"]["status"], "pending")

    def test_article_preview_route_renders_captured_markdown(self) -> None:
        run = self.harness.call_tool(58, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self.harness.call_tool(59, "write_json_artifact", {
            "run_id": run["run_id"],
            "namespace": "articles",
            "relative_path": "sample-post.json",
            "data": {
                "slug": "sample-post",
                "title": "Sample Post",
                "url": "https://www.granola.ai/blog/sample-post",
                "body_md": "# Heading\n\nCaptured body paragraph.",
                "trust": {
                    "author": {"name": "Marco", "role": "Editor"},
                    "published_at": "2026-04-22",
                },
                "structure": {"word_count": 1234},
            },
        })
        port = int(run["dashboard_url"].split(":")[2].split("/")[0])
        response = self._urlopen(
            f"http://127.0.0.1:{port}/api/runs/{run['run_id']}/article-preview/sample-post.html"
        )
        html = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Sample Post", html)
        self.assertIn("Captured body paragraph.", html)
        self.assertIn("1234 words", html)

    def test_validate_article_passes_with_selected_site_reviewer_and_evidence(self) -> None:
        run = self.harness.call_tool(58_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-pass", selected_reviewer=True)
        result = self.harness.call_tool(58_2, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-pass",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "passed")
        self.assertEqual(result["author_validation"]["status"], "passed")
        self.assertEqual(result["internal_source_count"], 3)
        self.assertEqual(result["external_source_count"], 2)
        self.assertEqual(result["schema_checks"]["status"], "passed")
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        article = next(item for item in state["articles"] if item["slug"] == "workflow-pass")
        self.assertEqual(article["stages"]["draft"]["status"], "completed")
        self.assertEqual(article["stages"]["draft"]["quality_gate"], "passed")

    def test_record_draft_package_writes_outputs_and_validates(self) -> None:
        run = self.harness.call_tool(58_1_0, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-package", selected_reviewer=True)
        html_text = pathlib.Path(run["optimised_dir"], "workflow-package.html").read_text(encoding="utf-8")
        schema_payload = json.loads(pathlib.Path(run["optimised_dir"], "workflow-package.schema.json").read_text(encoding="utf-8"))
        result = self.harness.call_tool(58_1_0_1, "record_draft_package", {
            "run_id": run["run_id"],
            "article_slug": "workflow-package",
            "package": {
                "markdown": "# Draft\n",
                "html": html_text,
                "schema": schema_payload,
                "diff_markdown": "# Diff\n",
                "handoff_markdown": "# Handoff\n",
                "audit_after": 34,
            },
        })["payload"]
        self.assertEqual(result["quality_gate_status"], "passed")
        self.assertEqual(result["manifest"]["quality_gate"]["status"], "passed")
        stored_html = pathlib.Path(run["optimised_dir"], "workflow-package.html").read_text(encoding="utf-8")
        self.assertIn("data-blog-optimiser-article-style", stored_html)
        self.assertIn("border-left: 5px solid var(--bo-accent)", stored_html)

    def test_validate_article_recovers_from_stringified_json_artifacts(self) -> None:
        run = self.harness.call_tool(58_1_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-stringified", selected_reviewer=True)
        recommendations_path = pathlib.Path(run["recommendations_dir"], "workflow-stringified.json")
        recommendations_payload = json.loads(recommendations_path.read_text(encoding="utf-8"))
        recommendations_path.write_text(json.dumps(json.dumps(recommendations_payload)), encoding="utf-8")
        manifest_path = pathlib.Path(run["optimised_dir"], "workflow-stringified.manifest.json")
        manifest_path.write_text(json.dumps(json.dumps({"audit_after": 30})), encoding="utf-8")
        result = self.harness.call_tool(58_1_2, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-stringified",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "passed")
        stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(stored_manifest["quality_gate"]["status"], "passed")

    def test_validate_article_blocks_first_name_only_byline_and_faq_mismatch(self) -> None:
        run = self.harness.call_tool(58_3, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._write_validator_fixture(run, slug="workflow-fail", selected_reviewer=False, faq_mismatch=True)
        result = self.harness.call_tool(58_4, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-fail",
            "audit_after": 31,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "failed")
        self.assertEqual(result["author_validation"]["status"], "failed")
        self.assertIn("trust_block", result["missing_required_modules"])
        self.assertIn("faq_schema", result["missing_required_modules"])
        self.assertIn("Visible byline", result["author_validation"]["detail"])
        self.assertIn("Visible FAQ questions do not match FAQPage schema.", "\n".join(result["schema_checks"]["notes"]))
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
        article = next(item for item in state["articles"] if item["slug"] == "workflow-fail")
        self.assertEqual(article["stages"]["draft"]["status"], "failed")
        self.assertEqual(article["stages"]["draft"]["quality_gate"], "failed")

    def test_validate_article_blocks_scope_drift(self) -> None:
        run = self.harness.call_tool(58_4_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-drift", selected_reviewer=True)
        drifted_html = """<!DOCTYPE html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Series C fundraising benchmarks</title></head>
  <body>
    <article>
      <h1>Series C fundraising benchmarks</h1>
      <p>TL;DR: This rewrite now talks about venture fundraising instead of Granola workflows.</p>
      <p>Reviewed by <strong>Chris Pedregal</strong>, Cofounder & CEO. Published 2025-07-28. Reviewed 2026-04-23.</p>
      <h2>What Series C companies optimize for?</h2>
      <p>Fundraising benchmarks vary by market cycle.</p>
      <h2>How should boards evaluate growth?</h2>
      <p>Board narratives differ from workflow automation topics.</p>
      <h2>FAQ</h2>
      <h3>What matters most?</h3>
      <p>Growth efficiency.</p>
      <h3>How long does it take?</h3>
      <p>It depends.</p>
      <h3>Should teams automate workflows?</h3>
      <p>Not the focus here.</p>
    </article>
  </body>
</html>
"""
        pathlib.Path(run["optimised_dir"], "workflow-drift.html").write_text(drifted_html, encoding="utf-8")
        result = self.harness.call_tool(58_4_2, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-drift",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "failed")
        self.assertEqual(result["scope_drift"]["status"], "failed")
        self.assertIn("pivot away", result["scope_drift"]["detail"])

    def test_validate_article_blocks_visible_advisory_meta_language(self) -> None:
        run = self.harness.call_tool(58_4_2_1, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-meta-language", selected_reviewer=True)
        html_path = pathlib.Path(run["optimised_dir"], "workflow-meta-language.html")
        html_path.write_text(
            html_path.read_text(encoding="utf-8").replace(
                "<p>The <a href=\"https://help.zapier.com",
                "<p>This rewrite follows the recommendation for AI search.</p>\n"
                "      <p>The <a href=\"https://help.zapier.com",
            ),
            encoding="utf-8",
        )
        result = self.harness.call_tool(58_4_2_2, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-meta-language",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "failed")
        issues = "\n".join(result["reader_safety"]["visible_meta_language_issues"])
        self.assertIn("this rewrite", issues)
        self.assertIn("recommendation", issues)

    def test_validate_article_blocks_unsupported_added_workflow_entity(self) -> None:
        run = self.harness.call_tool(58_4_2_3, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-unsupported-entity", selected_reviewer=True)
        html_path = pathlib.Path(run["optimised_dir"], "workflow-unsupported-entity.html")
        html_path.write_text(
            html_path.read_text(encoding="utf-8").replace(
                "<h2>Why does the evidence matter?</h2>",
                "<p>Teams can sync Salesforce pipeline updates from Slack approvals after each meeting.</p>\n"
                "      <h2>Why does the evidence matter?</h2>",
            ),
            encoding="utf-8",
        )
        result = self.harness.call_tool(58_4_2_4, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-unsupported-entity",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "failed")
        self.assertEqual(result["source_grounding"]["status"], "failed")
        self.assertIn("salesforce", result["source_grounding"]["unsupported_visible_entities"])
        self.assertIn("slack", result["source_grounding"]["unsupported_visible_entities"])

    def test_validate_article_passes_conservative_source_grounded_rewrite(self) -> None:
        run = self.harness.call_tool(58_4_2_5, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-source-grounded", selected_reviewer=True)
        result = self.harness.call_tool(58_4_2_6, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-source-grounded",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(result["quality_gate"]["status"], "passed")
        self.assertEqual(result["source_grounding"]["status"], "passed")
        self.assertEqual(result["reader_safety"]["visible_meta_language_issues"], [])

    def test_off_page_recommendations_stay_out_of_visible_html(self) -> None:
        run = self.harness.call_tool(58_4_2_7, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-off-page", selected_reviewer=True)
        recommendations_path = pathlib.Path(run["recommendations_dir"], "workflow-off-page.json")
        recommendations = json.loads(recommendations_path.read_text(encoding="utf-8"))
        recommendations["recommendations"].append({
            "id": "rec-off-1",
            "source": "llm",
            "category": "off_page",
            "priority": "critical",
            "title": "Contact AutoPedia for YouTube collaboration",
            "description": "Contact AutoPedia and ask for a collaboration on YouTube.",
        })
        recommendations_path.write_text(json.dumps(recommendations, indent=2), encoding="utf-8")
        manifest_path = pathlib.Path(run["optimised_dir"], "workflow-off-page.manifest.json")
        manifest_path.write_text(json.dumps({
            "rec_implementation_map": {
                "rec-off-1": {"implemented": False, "reason": "non-applicable"}
            }
        }), encoding="utf-8")
        passing = self.harness.call_tool(58_4_2_8, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-off-page",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(passing["quality_gate"]["status"], "passed")

        html_path = pathlib.Path(run["optimised_dir"], "workflow-off-page.html")
        html_path.write_text(
            html_path.read_text(encoding="utf-8").replace(
                "</article>",
                "<p>Contact AutoPedia for YouTube collaboration.</p>\n    </article>",
            ),
            encoding="utf-8",
        )
        failing = self.harness.call_tool(58_4_2_9, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-off-page",
            "audit_after": 34,
        })["payload"]
        self.assertEqual(failing["quality_gate"]["status"], "failed")
        self.assertIn("off-page recommendation appears", "\n".join(failing["reader_safety"]["off_page_issues"]))

    def test_finalize_run_report_writes_summary_from_disk_truth(self) -> None:
        run = self.harness.call_tool(58_4_3, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        self._seed_reviewers("granola.ai")
        self._write_validator_fixture(run, slug="workflow-report", selected_reviewer=True)
        self.harness.call_tool(58_4_4, "validate_article", {
            "run_id": run["run_id"],
            "article_slug": "workflow-report",
            "audit_after": 34,
        })
        self.harness.call_tool(58_4_5, "fail_article_stage", {
            "run_id": run["run_id"],
            "article_slug": "blocked-report",
            "stage": "draft",
            "reason": "Peec evidence was too weak to support a rewrite.",
        })
        result = self.harness.call_tool(58_4_6, "finalize_run_report", {
            "run_id": run["run_id"],
        })["payload"]
        self.assertEqual(result["status"], "partial")
        report = pathlib.Path(result["report_path"]).read_text(encoding="utf-8")
        self.assertIn("workflow-report", report)
        self.assertIn("draft-ready", report)
        self.assertIn("blocked-report", report)
        self.assertIn("blocked", report)

    def test_prompt_contract_regressions(self) -> None:
        command = (PLUGIN_ROOT / "commands" / "blog-optimiser.md").read_text(encoding="utf-8")
        skill = (PLUGIN_ROOT / "skills" / "blog-optimiser-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        crawler = (PLUGIN_ROOT / "agents" / "blog-crawler.md").read_text(encoding="utf-8")
        evidence_builder = (PLUGIN_ROOT / "agents" / "evidence-builder.md").read_text(encoding="utf-8")
        generator = (PLUGIN_ROOT / "agents" / "generator.md").read_text(encoding="utf-8")
        peec_gap_reader = (PLUGIN_ROOT / "agents" / "peec-gap-reader.md").read_text(encoding="utf-8")
        peec_gap_skill = (PLUGIN_ROOT / "skills" / "peec-gap-read" / "SKILL.md").read_text(encoding="utf-8")
        recommender = (PLUGIN_ROOT / "agents" / "recommender.md").read_text(encoding="utf-8")
        contract = (PLUGIN_ROOT / "references" / "geo-article-contract.md").read_text(encoding="utf-8")
        self.assertNotIn("get_paths", command)
        self.assertNotIn("mcp__c4ai-sse__ask", skill)
        self.assertIn("Never open the dashboard before `register_run`", command)
        self.assertIn("Draft visibility is driven by the dashboard validator output", command)
        self.assertIn("allowed-tools: \"*\"", command)
        self.assertIn("Do not assume the Peec MCP server is literally named `peec`", command)
        self.assertIn("Do not assume the Firecrawl MCP server is literally named `firecrawl`", command)
        self.assertIn("Use `ToolSearch` when you need to resolve external MCP tool names dynamically", command)
        self.assertIn("draft-ready vs blocked", command)
        self.assertIn("record_crawled_article", command)
        self.assertIn("record_voice_baseline", command)
        self.assertIn("record_peec_gap", command)
        self.assertIn("record_draft_package", command)
        self.assertIn("finalize_run_report", command)
        self.assertIn("--article-url <url>", command)
        self.assertIn("article_urls", command)
        self.assertIn("report surface only", command)
        self.assertIn("Immediately after registration, call", skill)
        self.assertIn("dashboard MCP artifact tools", skill)
        self.assertIn("If article_urls is non-empty", skill)
        self.assertIn("Use `ToolSearch` to discover whether a connected Firecrawl MCP is available", skill)
        self.assertIn("crawl_backend = \"firecrawl\"", skill)
        self.assertIn("\"crawl_backend\": \"firecrawl\"|\"crawl4ai\"", skill)
        self.assertIn("record_evidence_pack", skill)
        self.assertIn("record_recommendations", skill)
        self.assertIn("finalize_crawl", skill)
        self.assertIn("Use articles/{article_slug}.json.body_md as the rewrite spine", skill)
        self.assertIn("Use `ToolSearch` to discover whether a connected Peec MCP is available", skill)
        self.assertIn("Do not emit \"No Peec connection\" unless you first attempted capability-based discovery via `ToolSearch`", skill)
        self.assertIn("Peec is required for this product", skill)
        self.assertIn("record_peec_gap", skill)
        self.assertIn("record_draft_package", skill)
        self.assertIn("finalize_run_report", skill)
        self.assertIn("Deprecated `set_gate` / `get_gates` tools should not be part of the main flow.", skill)
        self.assertIn("raw JSON object or array", command)
        self.assertIn("### Stage 5 — Evidence", skill)
        self.assertIn("evidence-builder", skill)
        self.assertIn("Write draft artefacts through `record_draft_package`.", skill)
        self.assertIn("Never switch to `~/mnt/outputs`", crawler)
        self.assertIn("Never use `mcp__c4ai-sse__ask` to discover article URLs", crawler)
        self.assertIn("Never use `mcp__c4ai-sse__ask` for article extraction either", crawler)
        self.assertIn("Do not escalate to `execute_js`", crawler)
        self.assertIn("mcp__blog-optimiser-dashboard__", crawler)
        self.assertIn("record_crawl_discovery", crawler)
        self.assertIn("record_crawled_article", crawler)
        self.assertIn("finalize_crawl", crawler)
        self.assertIn("crawl only those URLs in the received order", crawler)
        self.assertIn("Never assume the Firecrawl MCP server prefix is literally `firecrawl`", crawler)
        self.assertIn("firecrawl_scrape", crawler)
        self.assertIn("firecrawl_map", crawler)
        self.assertIn("Do not invent reviewers, claims, or sources.", evidence_builder)
        self.assertIn("Fetch only real public source pages. If `crawl_backend` is `firecrawl`", evidence_builder)
        self.assertIn("record_evidence_pack", evidence_builder)
        self.assertIn("reviewer_candidate_id", evidence_builder)
        self.assertIn("evidence/{article_slug}.json", evidence_builder)
        self.assertIn("JSON array and may be empty", evidence_builder)
        self.assertIn("record_voice_baseline", (PLUGIN_ROOT / "agents" / "voice-extractor.md").read_text(encoding="utf-8"))
        self.assertIn("read_bundle_text", peec_gap_reader)
        self.assertIn("ToolSearch", peec_gap_reader)
        self.assertIn("Do not assume the server prefix is `peec`", peec_gap_reader)
        self.assertIn("Never conclude that Peec is missing solely because there is no `mcp__peec__...` prefix", peec_gap_reader)
        self.assertIn("skills/peec-gap-read/SKILL.md` via `read_bundle_text`", peec_gap_reader)
        self.assertIn("record_peec_gap", peec_gap_reader)
        self.assertIn("scope=overview", peec_gap_skill)
        self.assertIn("do **not** drill into `scope=owned`", peec_gap_skill)
        self.assertIn("\"overview_top_opportunities\"", peec_gap_skill)
        self.assertIn("Do not assume the server prefix is literally `peec`", peec_gap_skill)
        self.assertIn("<connected-peec>__list_projects", peec_gap_skill)
        self.assertNotIn("→ drill into relevant taxonomy branch", peec_gap_skill)
        self.assertIn("site/voice.json", generator)
        self.assertNotIn("model: opus", generator)
        self.assertIn("read_bundle_text", generator)
        self.assertIn("references/geo-article-contract.md", generator)
        self.assertIn("40-point GEO audit", generator)
        self.assertIn("record_draft_package", generator)
        self.assertIn("fail_article_stage", generator)
        self.assertIn("body_md` as the rewrite spine", generator)
        self.assertIn("Keep the visible H1 anchored to the source title", generator)
        self.assertIn("Off-page-only recommendations belong only in `diff_markdown` or `handoff_markdown`", generator)
        self.assertIn("controller-generated, not self-reported", generator)
        self.assertIn("anonymous, `Team`, `Staff`, or first-name-only", generator)
        self.assertIn("must_cite_claim_id", generator)
        self.assertIn("Never mark top-level `pipeline.draft`", generator)
        self.assertIn("site/voice.json", recommender)
        self.assertNotIn("skills/blog-optimiser-pipeline/SKILL.md", recommender)
        self.assertNotIn("model: opus", recommender)
        self.assertIn("40-point GEO audit", recommender)
        self.assertIn("quality_contract", recommender)
        self.assertIn("blueprint", recommender)
        self.assertIn("matched_prompts", recommender)
        self.assertIn("reviewer_plan", recommender)
        self.assertIn("evidence_plan", recommender)
        self.assertIn("internal_link_plan", recommender)
        self.assertIn("site/reviewers.json", recommender)
        self.assertIn("read_bundle_text", recommender)
        self.assertIn("references/geo-article-contract.md", recommender)
        self.assertIn("evidence/{article_slug}.json", recommender)
        self.assertIn("record_recommendations", recommender)
        self.assertIn("Use all matched prompts for synthesis", recommender)
        self.assertIn("Each recommendation object must include `addresses_prompts` directly", recommender)
        self.assertIn("exactly 3-8 LLM-source", recommender)
        self.assertIn("companion actions only", recommender)
        self.assertIn("Prefer at least four article-specific", recommender)
        self.assertIn("Do not copy large excerpts", recommender)
        self.assertIn("Never mark top-level `pipeline.analysis` or `pipeline.recommendations`", recommender)
        self.assertNotIn("voice-rubric", recommender)
        self.assertIn("first-name-only bylines", contract)
        self.assertIn("inline evidence count", contract)
        self.assertIn("schema checks", contract)
        self.assertIn("TL;DR", contract)
        self.assertIn("faq_block", contract)
        self.assertIn("comparison_table", contract)

    def test_index_file_does_not_auto_select_latest_run(self) -> None:
        html = (PLUGIN_ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("fetch('/api/runs')", html)
        self.assertNotIn("window.location.href = `/runs/", html)
        self.assertNotIn("/gates`", html)
        self.assertNotIn("Continue in Claude Cowork", html)
        self.assertNotIn("reply <code>continue</code> to resume the run", html)
        self.assertIn("label: 'Evidence'", html)
        self.assertIn("crawlStageDetail", html)
        self.assertIn("Firecrawl", html)
        self.assertIn("stage?.quality_gate === 'passed'", html)
        self.assertNotIn("stage?.quality_gate !== 'failed'", html)
        self.assertIn('x-data="articleDetail(article, expanded)"', html)
        self.assertIn("activePanel() === 'recommendations'", html)
        self.assertIn("activePanel() === 'draft'", html)
        self.assertIn("activePanel()", html)
        self.assertNotIn("articleDetail(article, expanded.panel)", html)
        self.assertNotIn("&& panel === 'recommendations'", html)
        self.assertNotIn("&& panel === 'draft'", html)
        self.assertIn("View recommendations", html)
        self.assertIn("View draft article", html)
        self.assertIn('x-data="articleDetail(article, expanded)"', html)
        self.assertIn('x-init="load()"', html)
        self.assertIn("loaded: false", html)
        self.assertIn('x-if="panelOpen(article.slug)"', html)
        self.assertNotIn('<tr x-show="panelOpen(article.slug)">', html)
        self.assertIn('x-show="!loading && activePanel() === \'recommendations\'"', html)
        self.assertIn('x-show="!loading && activePanel() === \'draft\'"', html)
        self.assertIn("this.expanded.slug = slug;", html)
        self.assertNotIn("this.expanded = {slug, panel};", html)
        self.assertNotIn('x-data="articleDetail(article, expanded.panel)"', html)
        self.assertIn("Open full article", html)
        self.assertIn("Open in new tab", html)
        self.assertIn("Updated at", html)
        self.assertNotIn("voice-rubric", html)
        self.assertNotIn("View article", html)
        self.assertNotIn("View markdown", html)
        self.assertNotIn("View HTML", html)
        self.assertNotIn("View diff", html)
        self.assertNotIn("@click=\"resolveGate", html)
        self.assertNotIn("Accept", html)
        self.assertNotIn("Reject", html)
        self.assertNotIn("Approve", html)
        self.assertNotIn("Preview draft", html)
        self.assertNotIn("Re-run", html)
        self.assertNotIn("Structure", html)
        self.assertNotIn("Image", html)
        self.assertNotIn("What shipped", html)
        self.assertNotIn("Implementation notes", html)

    def test_decisions_api_and_tool_are_removed(self) -> None:
        run = self.harness.call_tool(60, "register_run", {
            "blog_url": "https://www.granola.ai/blog",
        })["payload"]
        result = self.harness.call_tool(61, "get_decisions", {
            "run_id": run["run_id"],
        })
        self.assertTrue(result["is_error"])
        self.assertIn("Unknown tool", result["payload"])
        port = int(run["dashboard_url"].split(":")[2].split("/")[0])
        with self.assertRaises(urllib.error.HTTPError) as err:
            self._urlopen(f"http://127.0.0.1:{port}/api/runs/{run['run_id']}/decisions")
        self.assertEqual(err.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
