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
        self.send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        response = self.recv()["result"]
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
            "recommendations_dir",
            "optimised_dir",
            "media_dir",
            "raw_dir",
            "gaps_dir",
            "competitors_dir",
            "peec_cache_dir",
            "decisions_path",
            "gates_path",
            "run_summary_path",
            "site_key",
            "voice_baseline",
            "voice_markdown_path",
            "voice_meta_path",
        }
        self.assertTrue(expected_keys.issubset(result.keys()))
        self.assertEqual(result["site_key"], "granola.ai")
        self.assertTrue(pathlib.Path(result["outputs_dir"]).exists())
        state = json.loads(pathlib.Path(result["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["pipeline"]["prereqs"]["status"], "completed")
        self.assertEqual(state["pipeline"]["draft"]["status"], "pending")
        self.assertEqual(state["session"]["mode"], "fresh")

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
                            "draft": {"status": "completed", "audit_after": 34},
                            "recommendations": {"status": "completed", "recommendation_count": 4},
                        },
                    },
                    {
                        "slug": "pending-post",
                        "title": "Pending Post",
                        "stages": {
                            "draft": {"status": "pending"},
                            "recommendations": {"status": "pending"},
                        },
                    },
                ],
            },
        })
        state = json.loads(pathlib.Path(run["state_path"]).read_text(encoding="utf-8"))
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

    def test_prompt_contract_regressions(self) -> None:
        command = (PLUGIN_ROOT / "commands" / "blog-optimiser.md").read_text(encoding="utf-8")
        skill = (PLUGIN_ROOT / "skills" / "blog-optimiser-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        crawler = (PLUGIN_ROOT / "agents" / "blog-crawler.md").read_text(encoding="utf-8")
        generator = (PLUGIN_ROOT / "agents" / "generator.md").read_text(encoding="utf-8")
        recommender = (PLUGIN_ROOT / "agents" / "recommender.md").read_text(encoding="utf-8")
        self.assertNotIn("get_paths", command)
        self.assertNotIn("mcp__c4ai-sse__ask", skill)
        self.assertIn("Never open the dashboard before `register_run`", command)
        self.assertIn("Immediately after registration, call", skill)
        self.assertIn("dashboard MCP artifact tools", skill)
        self.assertIn("trust the returned status as authoritative", skill)
        self.assertIn("crawl_gate", skill)
        self.assertIn("voice_gate", skill)
        self.assertIn("recommend_gate", skill)
        self.assertIn("Poll `get_gates` every 10 seconds", skill)
        self.assertIn("Never switch to `~/mnt/outputs`", crawler)
        self.assertIn("Never use `mcp__c4ai-sse__ask` to discover article URLs", crawler)
        self.assertIn("Never use `mcp__c4ai-sse__ask` for article extraction either", crawler)
        self.assertIn("Do not escalate to `execute_js`", crawler)
        self.assertIn("mcp__plugin_ai-search-blog-optimiser_blog-optimiser-dashboard__get_artifact_path", crawler)
        self.assertIn("site/voice.json", generator)
        self.assertNotIn("model: opus", generator)
        self.assertIn("Never mark top-level `pipeline.draft`", generator)
        self.assertIn("site/voice.json", recommender)
        self.assertNotIn("skills/blog-optimiser-pipeline/SKILL.md", recommender)
        self.assertNotIn("model: opus", recommender)
        self.assertIn("40-point rubric", recommender)
        self.assertIn("Never mark top-level `pipeline.analysis` or `pipeline.recommendations`", recommender)

    def test_index_file_does_not_auto_select_latest_run(self) -> None:
        html = (PLUGIN_ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("fetch('/api/runs')", html)
        self.assertNotIn("window.location.href = `/runs/", html)
        self.assertIn("View article", html)
        self.assertIn("View recommendations", html)
        self.assertIn("View markdown", html)
        self.assertIn("View HTML", html)
        self.assertIn("View diff", html)
        self.assertIn("Optimized article", html)
        self.assertIn("Structure", html)
        self.assertIn("Image", html)
        self.assertIn("What shipped", html)
        self.assertIn("Implementation notes", html)


if __name__ == "__main__":
    unittest.main()
