# Bug 5 Acceptance Test - Embedded JSON-LD in Rendered HTML

Manual reproduction sequence for Lane E.

## Setup

Use any clean pipeline run with one crawled article, one evidence pack, and one recommendation artifact.

## Steps

1. Run the draft stage for one article through the generator.
2. Capture the `run_id` and `article_slug`.
3. Read the rendered HTML artifact:

```text
read_text_artifact(run_id=<run_id>, namespace="optimised", name="<article_slug>.html")
```

4. Extract every `<script type="application/ld+json">...</script>` block from the HTML.
5. Parse the JSON payload inside each extracted script tag.
6. Call:

```text
validate_article(run_id=<run_id>, article_slug=<article_slug>)
```

## Required Assertions

- `optimised/{article_slug}.html` contains at least one `<script type="application/ld+json">` tag.
- At least one extracted script payload parses as valid JSON.
- At least one parsed JSON-LD payload contains `@context`, `@type`, and a non-empty `headline`.
- If the primary embedded node is not an article type, it contains `@context`, `@type`, and a non-empty `name`.
- `validate_article` returns `schema_checks.passed_embedded_jsonld == true`.

## Pass Criterion

All assertions pass on a clean one-article run.
