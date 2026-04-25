# Bug 6 Acceptance Test - Internal Subdomain Links

Manual reproduction sequence for Lane F Bug 6.

## Setup

Use a clean validator fixture for site key `granola.ai`.

## Steps

1. Register a run for `https://www.granola.ai/blog`.
2. Write `outputs/articles/subdomain-links.json` with `url = "https://www.granola.ai/blog/subdomain-links"`.
3. Write normal recommendation, evidence, HTML, and schema artifacts for `subdomain-links`.
4. In `optimised/subdomain-links.html`, include these body links:

```html
<a href="https://www.granola.ai/team">Team</a>
<a href="https://docs.granola.ai/api">Docs</a>
<a href="https://app.granola.ai/login">App</a>
<a href="https://example.com/external">External</a>
```

5. Call `validate_article(run_id, "subdomain-links")`.
6. Read the returned manifest and `optimised/subdomain-links.manifest.json`.

## Required Assertions

- `internal_link_count == 3`.
- `internal_links` contains the `www.granola.ai`, `docs.granola.ai`, and `app.granola.ai` URLs.
- `internal_links` does not contain `https://example.com/external`.
- The internal-link blocker is absent when the recommendation threshold is 3 or lower.

## Pass Criterion

All `*.granola.ai` subdomains are classified as internal links without lowering the validator threshold.
