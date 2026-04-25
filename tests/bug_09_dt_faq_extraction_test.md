# Bug 9 Acceptance Test - FAQ Extraction From Definition Lists

Manual validator acceptance sequence for Lane G Bug 9.

## Parser Fixture

Construct an HTML snapshot fixture with both supported FAQ render styles:

```html
<h2>FAQ</h2>
<h3>What is Granola Chat?</h3>
<p>An agentic chat interface for your meeting notes.</p>

<dl>
  <dt>How do I add my team?</dt>
  <dd>Open Settings -> Team Space and invite by email.</dd>
  <dt>Does Granola work offline?</dt>
  <dd>Yes, Granola caches notes locally.</dd>
</dl>
```

## Required Parser Assertions

- Pass the fixture through `_HTMLSnapshotParser` via `_parse_html_snapshot`.
- `snapshot.faq_questions` contains exactly these questions in document order:
  - `What is Granola Chat?`
  - `How do I add my team?`
  - `Does Granola work offline?`
- Heading-based FAQ extraction still works when the `<dl>` block is removed.
- Definition-list FAQ extraction still works when the `<h2>FAQ</h2>` and `<h3>` block are removed.

## Required validate_article Assertion

Run `validate_article` on a Granola fixture article whose rendered `optimised/{slug}.html` contains FAQ blocks as `<dl><dt>question</dt><dd>answer</dd></dl>` and whose FAQPage schema contains matching Question names.

- `schema_checks.faq_questions_visible.length >= 1`.
- `schema_checks.faq_questions_visible` includes the `<dt>` question text.
- `schema_checks.status == "passed"` when the visible `<dt>` questions match the schema questions.

## Pass Criterion

The validator reports visible FAQ questions for definition-list FAQ markup without regressing the existing heading-based FAQ path.
