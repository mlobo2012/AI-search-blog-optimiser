# Bug 8 Acceptance Test - Trust Block Author Fallback

Manual reproduction sequence for Lane F Bug 8.

## Setup

Use clean validator fixtures for site key `granola.ai`.

## Steps

1. Register a run for `https://www.granola.ai/blog`.
2. Write `site/reviewers.json` as an empty array:

```json
[]
```

3. Construct a valid article fixture whose `articles/{slug}.json` includes:

```json
{
  "trust": {
    "author": {
      "name": "Chris Pedregal",
      "role": "Cofounder & CEO"
    }
  }
}
```

4. Write normal recommendation, evidence, HTML, and schema artifacts for that slug.
5. Call `validate_article(run_id, slug)`.
6. Construct a second fixture with `trust.author.name = "Jack"` and call `validate_article`.
7. Reset `site/reviewers.json` to a non-empty array containing an active reviewer named `Chris Pedregal`, then call `validate_article` again for the Chris fixture.

## Required Assertions

- With empty `reviewers.json` and `trust.author.name = "Chris Pedregal"`, `trust_block.passed == true`.
- With empty `reviewers.json` and `trust.author.name = "Chris Pedregal"`, `trust_block.source == "article_author_fallback"`.
- With empty `reviewers.json` and `trust.author.name = "Jack"`, `trust_block.passed == false`.
- With an active matching reviewer in `reviewers.json`, `trust_block.passed == true`.
- With an active matching reviewer in `reviewers.json`, `trust_block.source == "reviewers_json"`.

## Pass Criterion

The validator accepts a full-name article author as the trust signal only when `reviewers.json` is empty, while preserving the stricter failure for single-name authors.
