# Bug 16 Acceptance Test: question_headings Detection

## Fixtures

- Regression fixture A: rendered HTML with 4 H2s, 3 in question format. At least one starts with a question word and does not end with `?`.
- Negative fixture B: rendered HTML with 4 H2s, 0 in question format.
- Boundary fixture C: rendered HTML with 4 H2s, exactly 2 in question format.
- Smoke fixture: v0.6.1 run `2026-04-25T20-12-28`, article `granola-chat-just-got-smarter`, which includes H2s beginning with `Which` and `How`.

## Steps

```sh
RUN="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/2026-04-25T20-12-28"
python3 dashboard/quality_gate.py "$RUN" granola-chat-just-got-smarter || true
GRANOLA_MANIFEST="$RUN/outputs/optimised/granola-chat-just-got-smarter.manifest.json"
```

The command can return non-zero while unrelated blockers from other lanes remain. The assertions below are scoped to Bug 16.

## Smoke jq Assertions

```sh
jq -e '.implemented_modules | index("question_headings") != null' "$GRANOLA_MANIFEST"
jq -e '.missing_required_modules | index("question_headings") == null' "$GRANOLA_MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") == null' "$GRANOLA_MANIFEST"
```

## Positive Fixture jq Assertions

```sh
POSITIVE_MANIFEST="outputs/optimised/question-headings-positive.manifest.json"
jq -e '.implemented_modules | index("question_headings") != null' "$POSITIVE_MANIFEST"
jq -e '.missing_required_modules | index("question_headings") == null' "$POSITIVE_MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") == null' "$POSITIVE_MANIFEST"
```

Fixture H2 examples:

```html
<h2>Which AI meeting assistant is best for searching past meetings?</h2>
<h2>How Granola Chat turns notes into team knowledge</h2>
<h2>What should teams check before adopting AI notes</h2>
<h2>Implementation details</h2>
```

## Negative Fixture jq Assertions

```sh
NEGATIVE_MANIFEST="outputs/optimised/question-headings-negative.manifest.json"
jq -e '.implemented_modules | index("question_headings") == null' "$NEGATIVE_MANIFEST"
jq -e '.missing_required_modules | index("question_headings") != null' "$NEGATIVE_MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") != null' "$NEGATIVE_MANIFEST"
```

Fixture H2 examples:

```html
<h2>Overview</h2>
<h2>Product details</h2>
<h2>Team workflows</h2>
<h2>Implementation notes</h2>
```

## Boundary Fixture jq Assertions

```sh
BOUNDARY_MANIFEST="outputs/optimised/question-headings-boundary.manifest.json"
jq -e '.implemented_modules | index("question_headings") != null' "$BOUNDARY_MANIFEST"
jq -e '.missing_required_modules | index("question_headings") == null' "$BOUNDARY_MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") == null' "$BOUNDARY_MANIFEST"
```

Fixture H2 examples:

```html
<h2>Which meetings can Granola Chat search?</h2>
<h2>How does team knowledge work?</h2>
<h2>Setup notes</h2>
<h2>Pricing details</h2>
```

The positive and boundary fixtures prove that the detector does not require every H2 to be a question and recognises question-word starts without requiring a literal `?` suffix.
