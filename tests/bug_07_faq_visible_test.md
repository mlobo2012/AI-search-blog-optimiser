# Bug 7 Acceptance Test - Visible FAQ Definition Lists

Manual reproduction sequence for Lane E.

## Setup

Use a clean one-article run where the recommendation blueprint explicitly includes an FAQ block or contains at least three natural user-question patterns.

## Steps

1. Run the draft stage for the selected article through the generator.
2. Capture the `run_id` and `article_slug`.
3. Read the rendered HTML artifact:

```text
read_text_artifact(run_id=<run_id>, namespace="optimised", name="<article_slug>.html")
```

4. Inspect the FAQ section in `optimised/{article_slug}.html`.
5. Call:

```text
validate_article(run_id=<run_id>, article_slug=<article_slug>)
```

## Required Assertions

- `optimised/{article_slug}.html` contains at least one `<dl>...</dl>` FAQ block.
- The FAQ block contains at least one `<dt>...</dt>` question followed by a matching `<dd>...</dd>` answer.
- FAQ questions are not rendered only as heading tags followed by paragraphs.
- `validate_article` returns `schema_checks.faq_questions_visible` with at least one extracted question text.

## Pass Criterion

All assertions pass on a clean one-article run whose recommendations imply or include an FAQ.
