# Bug 20 Acceptance Test: Internal Source Subdomain Classification

## Fixtures

- Same-apex fixture A: canonical blog URL `https://www.granola.ai/blog` with evidence sources on `www.granola.ai`, `docs.granola.ai`, and `app.granola.ai`.
- Same-apex fixture B: canonical blog URL `https://granola.ai/blog` with evidence sources on `granola.ai` and `www.granola.ai`.
- External fixture: canonical blog URL `https://www.granola.ai/blog` with evidence sources on `techtarget.com` and `atlassian.com`.
- Substring-trick fixture: canonical blog URL `https://www.granola.ai/blog` with evidence source `https://granolafake.com/x`.

## Steps

```sh
python3 - <<'PY'
from dashboard.quality_gate import _source_mix

def counts(urls, canonical_blog_url):
    sources = [{"url": url} for url in urls]
    internal_count, external_count, internal_sources, external_sources = _source_mix(sources, canonical_blog_url)
    return internal_count, external_count, internal_sources, external_sources

internal_count, external_count, internal_sources, external_sources = counts([
    "https://www.granola.ai/blog/foo",
    "https://docs.granola.ai/help",
    "https://app.granola.ai/x",
], "https://www.granola.ai/blog")
assert internal_count == 3, (internal_count, internal_sources)
assert external_count == 0, (external_count, external_sources)

internal_count, external_count, internal_sources, external_sources = counts([
    "https://granola.ai/blog/foo",
    "https://www.granola.ai/x",
], "https://granola.ai/blog")
assert internal_count == 2, (internal_count, internal_sources)
assert external_count == 0, (external_count, external_sources)

internal_count, external_count, internal_sources, external_sources = counts([
    "https://techtarget.com/x",
    "https://atlassian.com/y",
], "https://www.granola.ai/blog")
assert internal_count == 0, (internal_count, internal_sources)
assert external_count == 2, (external_count, external_sources)

internal_count, external_count, internal_sources, external_sources = counts([
    "https://granolafake.com/x",
], "https://www.granola.ai/blog")
assert internal_count == 0, (internal_count, internal_sources)
assert external_count == 1, (external_count, external_sources)
PY
```

## Assertions

```sh
python3 - <<'PY'
from dashboard.quality_gate import _is_internal, _source_mix

assert _is_internal("https://www.granola.ai/blog/foo", "https://www.granola.ai/blog")
assert _is_internal("https://docs.granola.ai/help", "https://www.granola.ai/blog")
assert _is_internal("https://app.granola.ai/x", "https://www.granola.ai/blog")
assert _source_mix([
    {"url": "https://www.granola.ai/blog/foo"},
    {"url": "https://docs.granola.ai/help"},
    {"url": "https://app.granola.ai/x"},
], "https://www.granola.ai/blog")[:2] == (3, 0)

assert _is_internal("https://granola.ai/blog/foo", "https://granola.ai/blog")
assert _is_internal("https://www.granola.ai/x", "https://granola.ai/blog")
assert _source_mix([
    {"url": "https://granola.ai/blog/foo"},
    {"url": "https://www.granola.ai/x"},
], "https://granola.ai/blog")[:2] == (2, 0)

assert _source_mix([
    {"url": "https://techtarget.com/x"},
    {"url": "https://atlassian.com/y"},
], "https://www.granola.ai/blog")[:2] == (0, 2)

assert not _is_internal("https://granolafake.com/x", "https://www.granola.ai/blog")
assert _source_mix([
    {"url": "https://granolafake.com/x"},
], "https://www.granola.ai/blog")[:2] == (0, 1)
PY
```
