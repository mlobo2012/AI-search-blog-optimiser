# Bug 21 Acceptance Test: question-H2 Enforcement

## Fixtures

- Trigger fixture A: recommendations include a `geo_hygiene` rec mentioning "FAQ block"; the source
  draft has 4 declarative H2s and 0 question H2s.
- Trigger fixture B: recommendations include an `engine_specific` rec mentioning "question H2
  targeting"; the source draft has 6 H2s.
- Non-trigger fixture C: recommendations do not mention FAQ, question H2, question-format headings,
  or question target language.
- Already-compliant fixture D: the source draft already satisfies the question_headings threshold.

## Steps

Run the generator against each fixture and then run the quality gate on the generated draft.

```sh
python3 dashboard/quality_gate.py "$RUN" "$ARTICLE_SLUG" || true
MANIFEST="$RUN/outputs/optimised/$ARTICLE_SLUG.manifest.json"
```

The command can return non-zero while unrelated blockers from other lanes remain. The assertions
below are scoped to Bug 21.

## Trigger Fixture A Assertions

Input recommendation example:

```json
{
  "id": "rec-001",
  "category": "geo_hygiene",
  "title": "Add FAQ block targeting AI search gaps",
  "description": "Use an FAQ block and question-format headings for the highest-value prompts."
}
```

Source H2 examples:

```html
<h2>Auditable by design</h2>
<h2>New Recipes</h2>
<h2>Putting your company's context to work</h2>
<h2>Team rollout</h2>
```

Expected generated H2 examples:

```html
<h2>How is Granola Chat auditable by design?</h2>
<h2>Which new Recipes can I run in Granola Chat?</h2>
<h2>Putting your company's context to work</h2>
<h2>Team rollout</h2>
```

```sh
jq -e '.implemented_modules | index("question_headings") != null' "$MANIFEST"
jq -e '.missing_required_modules | index("question_headings") == null' "$MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") == null' "$MANIFEST"
```

The generated draft must have at least 2 question H2s when it keeps 4 body H2s, or at least 2
question H2s if the body H2 count drops to 3.

## Trigger Fixture B Assertions

Input recommendation example:

```json
{
  "id": "rec-002",
  "category": "engine_specific",
  "title": "Use question H2 targeting for ChatGPT",
  "description": "Rewrite section headings as question targets that mirror retrieval prompts."
}
```

Expected generated H2 examples:

```html
<h2>Which AI meeting assistant is best for searching past meetings?</h2>
<h2>How does Granola Chat make notes auditable?</h2>
<h2>What Recipes can teams run?</h2>
<h2>Rollout checklist</h2>
<h2>Security model</h2>
<h2>Pricing notes</h2>
```

```sh
jq -e '.implemented_modules | index("question_headings") != null' "$MANIFEST"
jq -e '.missing_required_modules | index("question_headings") == null' "$MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") == null' "$MANIFEST"
```

The generated draft must have at least 3 question H2s when it keeps 6 body H2s.

## Non-Trigger Fixture C Assertions

Input recommendation example:

```json
{
  "id": "rec-003",
  "category": "content_gap",
  "title": "Add product rollout details",
  "description": "Expand the implementation notes with clearer sequence and owner details."
}
```

Source and generated H2 examples:

```html
<h2>Product rollout</h2>
<h2>Implementation notes</h2>
<h2>Security model</h2>
```

The generator must not rewrite existing H2s solely to satisfy question_headings when no FAQ,
question H2, question-format heading, or question target recommendation triggered the rule.

## Already-Compliant Fixture D Assertions

Source H2 examples:

```html
<h2>Which meetings can Granola Chat search?</h2>
<h2>How does team knowledge work?</h2>
<h2>Setup notes</h2>
<h2>Pricing details</h2>
```

Expected generated H2 examples:

```html
<h2>Which meetings can Granola Chat search?</h2>
<h2>How does team knowledge work?</h2>
<h2>Setup notes</h2>
<h2>Pricing details</h2>
```

```sh
jq -e '.implemented_modules | index("question_headings") != null' "$MANIFEST"
jq -e '.missing_required_modules | index("question_headings") == null' "$MANIFEST"
jq -e '.quality_gate.missing_required_modules | index("question_headings") == null' "$MANIFEST"
```

The generator must not remove or rewrite existing question H2s into declarative headings when the
source already satisfies the threshold.
