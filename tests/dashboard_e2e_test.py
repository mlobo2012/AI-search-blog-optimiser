"""E2E smoke test for the dashboard v0.2.0 HTTP + MCP flow.
Run with: python3 tests/dashboard_e2e_test.py
"""
import subprocess, json, os, time, urllib.request, pathlib, sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = "/tmp/bo-html"
env = os.environ.copy()
env["CLAUDE_PLUGIN_ROOT"] = PLUGIN

# Clean up any prior test daemon
subprocess.run(
    ["python3", f"{PLUGIN}/dashboard/server.py", "--plugin-root", PLUGIN,
     "--data-dir", DATA, "--stop-dashboard"],
    check=False, capture_output=True,
)

proc = subprocess.Popen(
    ["python3", f"{PLUGIN}/dashboard/server.py", "--plugin-root", PLUGIN, "--data-dir", DATA],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=env, text=True, bufsize=1,
)


def send(m):
    proc.stdin.write(json.dumps(m) + "\n")
    proc.stdin.flush()


def recv():
    return json.loads(proc.stdout.readline())


try:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    recv()
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": "open_dashboard", "arguments": {"open_browser": False}}})
    port = json.loads(recv()["result"]["content"][0]["text"])["port"]

    send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
          "params": {"name": "register_run",
                     "arguments": {"blog_url": "https://granola.ai/blog",
                                   "brand_name": "Granola",
                                   "peec_project_id": "gn-demo", "role": "own"}}})
    run_id = json.loads(recv()["result"]["content"][0]["text"])["run_id"]
    print(f"run_id={run_id}, dashboard port={port}")

    fragment = {
        "pipeline": {
            "crawl": {"status": "completed", "count": 3},
            "voice": {"status": "completed", "summary": "Warm founder voice"},
        },
        "articles": [
            {"slug": "a-one", "url": "https://granola.ai/blog/a-one",
             "title": "Article One",
             "stages": {"crawl": {"status": "completed", "word_count": 1200}}},
            {"slug": "a-two", "url": "https://granola.ai/blog/a-two",
             "title": "Article Two",
             "stages": {"crawl": {"status": "completed", "word_count": 1500}}},
            {"slug": "a-three", "url": "https://granola.ai/blog/a-three",
             "title": "Article Three",
             "stages": {"crawl": {"status": "completed", "word_count": 1800}}},
        ],
    }
    send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
          "params": {"name": "update_state",
                     "arguments": {"run_id": run_id, "fragment": fragment}}})
    recv()

    send({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
          "params": {"name": "set_gate",
                     "arguments": {"run_id": run_id, "gate": "crawl_gate",
                                   "status": "pending",
                                   "prompt": "Review crawled articles and continue."}}})
    recv()

    recs_dir = pathlib.Path(DATA) / "runs" / run_id / "recommendations"
    recs_dir.mkdir(parents=True, exist_ok=True)
    (recs_dir / "a-one.json").write_text(json.dumps({
        "slug": "a-one", "article_type": "how-to", "audit_score": 21, "audit_max": 40,
        "recommendations": [{
            "id": "rec-1", "fix": "Add trust block",
            "severity": "critical", "effort": "<1h",
            "expected_lift_per_engine": {"chatgpt": "+0.8", "perplexity": "+0.3"},
            "evidence": {
                "peec_gap": {"prompt": "how do X",
                             "engines_lost": ["chatgpt"],
                             "cited_competitors": ["https://otter.ai/blog/x"]},
                "schmidt_rule": "geo-content-engineering#1 (trust block)",
                "competitor_example": {"url": "https://otter.ai/blog/x",
                                       "excerpt": "Opens with..."},
                "step1_field": "structure.heading_tree[0]",
            },
            "auto_fix": {"action": "prepend_block"},
        }],
    }, indent=2))

    html = urllib.request.urlopen(
        f"http://127.0.0.1:{port}/runs/{run_id}/", timeout=2,
    ).read().decode()
    checks = [
        ("Blog Optimiser" in html, "title renders"),
        ("Continue" in html, "Continue button markup present"),
        ("articleStage" in html, "articleStage helper present"),
        ("resolveGate" in html, "resolveGate handler present"),
        ("version: '0.2.0'" in html, "v0.2.0 JS version marker"),
    ]
    for ok, label in checks:
        print(f"  {'OK' if ok else 'FAIL'} {label}")
    assert all(ok for ok, _ in checks)

    s = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/runs/{run_id}/state", timeout=2).read())
    assert s["pipeline"]["crawl"]["status"] == "completed"
    assert len(s["articles"]) == 3
    print("OK /api/runs/.../state reflects crawl=completed with 3 articles")

    g = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/runs/{run_id}/gates", timeout=2).read())
    assert g["crawl_gate"]["status"] == "pending"
    print("OK /api/runs/.../gates shows crawl_gate pending")

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/runs/{run_id}/gate",
        data=json.dumps({"gate": "crawl_gate", "action": "proceed"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    body = json.loads(urllib.request.urlopen(req, timeout=2).read())
    assert body["gates"]["crawl_gate"]["status"] == "resolved"
    print(f"OK Continue-button POST resolves gate -> status=resolved, action={body['gates']['crawl_gate']['user_action']}")

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/runs/{run_id}/actions",
        data=json.dumps({"action": "accept", "slug": "a-one", "rec_id": "rec-1"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    body = json.loads(urllib.request.urlopen(req, timeout=2).read())
    assert body["decisions"]["articles"]["a-one"]["recs"]["rec-1"] == "accept"
    print("OK accept/reject POST /actions round-trips")

    print("\nALL GREEN")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    subprocess.run(
        ["python3", f"{PLUGIN}/dashboard/server.py", "--plugin-root", PLUGIN,
         "--data-dir", DATA, "--stop-dashboard"],
        check=False, capture_output=True,
    )
