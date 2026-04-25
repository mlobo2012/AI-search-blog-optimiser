# Bug 1 Acceptance Test - Crawler Run-ID Discipline

Manual reproduction sequence for Lane A.

## Setup

Use a clean data root and a blog with at least three article URLs.

Example input:

```text
blog_url: https://www.granola.ai/blog
peec_project_id: or_e15a6ac5-...
max_articles: 3
```

## Steps

1. Call `register_run(blog_url, peec_project_id="or_e15a6ac5-...")`.
2. Capture `run_id_A`, the register timestamp, and the returned absolute paths.
3. Dispatch `blog-crawler` with this prompt block:

```text
run_id: <run_id_A>
blog_url: <blog_url>
max_articles: 3
articles_dir: <articles_dir>
media_dir: <media_dir>
raw_dir: <raw_dir>
state_json: <state_path>

Use dashboard MCP artifact tools for all host-side reads and writes.
Never call register_run.
Never use Bash/Read/Write on /Users/... paths.
```

4. After the crawler completes, call:

```text
list_artifacts(run_id=<run_id_A>, namespace="articles", suffix=".json")
```

5. Inspect the run directory listing under `runs/`.
6. Read `runs/<run_id_A>/state.json`.

## Required Assertions

- `list_artifacts(run_id=<run_id_A>, namespace="articles", suffix=".json")` returns at least one article artifact.
- No other run directory was created after the timestamp of the `register_run` call.
- `runs/<run_id_A>/state.json` contains `peec_project.id == "or_e15a6ac5-..."`.

## Pass Criterion

All three assertions pass on a clean run against any blog with at least three articles.
