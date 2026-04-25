# Bug 03 acceptance test: dashboard MCP evidence namespace

Manual reproduction sequence for the dashboard MCP.

1. Call `register_run(blog_url, peec_project_id)` and capture the response.
2. Assert the returned `evidence_dir` exists on disk and points to `runs/{run_id}/outputs/evidence/`.
3. Call:

```json
{
  "name": "write_json_artifact",
  "arguments": {
    "run_id": "<run_id>",
    "namespace": "evidence",
    "relative_path": "smoke.json",
    "data": {"k": "v"}
  }
}
```

4. Assert the write succeeds.
5. Call:

```json
{
  "name": "read_json_artifact",
  "arguments": {
    "run_id": "<run_id>",
    "namespace": "evidence",
    "relative_path": "smoke.json"
  }
}
```

6. Assert the response contains `data == {"k": "v"}`.
7. Call:

```json
{
  "name": "list_artifacts",
  "arguments": {
    "run_id": "<run_id>",
    "namespace": "evidence"
  }
}
```

8. Assert the artifacts list contains `smoke.json`.

Pass criterion: `outputs/evidence/` is scaffolded by `register_run`, and `write_json_artifact`, `read_json_artifact`, and `list_artifacts` all accept `namespace="evidence"` and operate on that directory.
