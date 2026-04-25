# Bug 10 Acceptance Test - Single-Name Author With Role Trust

Manual validator acceptance sequence for Lane G Bug 10.

## Setup

Use a clean Granola validator fixture run with `site/reviewers.json` written as an empty array:

```json
[]
```

Each fixture must render the author name visibly in the trust block, render the published or updated date visibly, and include otherwise valid recommendation, evidence, HTML, and schema artifacts.

## Required Assertions

### Single Name With Role

Construct `articles/{slug}.json` with:

```json
{
  "trust": {
    "author": {
      "name": "Jack",
      "role": "Engineering Lead"
    }
  }
}
```

Run `validate_article(run_id, slug)`.

- `trust_block.passed == true`.
- `author_validation.status == "passed"`.
- `author_validation.detail` mentions `single-name-with-role`.

### Single Name Without Role

Construct the same fixture with:

```json
{
  "trust": {
    "author": {
      "name": "Jack",
      "role": ""
    }
  }
}
```

Run `validate_article(run_id, slug)`.

- `trust_block.passed == false`.
- `author_validation.status == "failed"`.

### Full Name Without Role

Construct the same fixture with:

```json
{
  "trust": {
    "author": {
      "name": "Chris Pedregal",
      "role": ""
    }
  }
}
```

Run `validate_article(run_id, slug)`.

- `trust_block.passed == true`.
- `author_validation.status == "passed"`.

### Live Smoke

Re-run the smoke against `granola-chat-just-got-smarter`.

- `trust_block.passed == true`.
- `author_validation.status == "passed"`.
- `author_validation.detail` mentions `single-name-with-role`.

## Pass Criterion

The validator accepts a visible single-name article author only when the article artifact supplies a substantive `trust.author.role`, while preserving failure for roleless single-name authors and the existing full-name author fallback.
