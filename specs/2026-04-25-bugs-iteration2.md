# Bug-fix Spec — Iteration 2 (target: v0.5.8)

Source: live `claude -p` smoke run on 2026-04-25 against `https://www.granola.ai/blog --max-articles 2`, plugin v0.5.7. Run id `2026-04-25T13-47-29`.

The v0.5.7 fixes hold up at runtime — pipeline runs all 7 stages, evidence stage produces files, validate_article returns full manifests. **Both articles failed quality_gate** for legitimate reasons: the generator output and the validator's strictness aren't aligned.

| Article | audit_before | audit_after | quality_gate |
|---|---|---|---|
| granola-chat-just-got-smarter | 20/40 | 28/40 | failed |
| series-c | 24/40 | 34/40 | failed |

Four blockers came out of the validator manifest. Each maps to either generator output or validator logic. None are content-creation issues; they're contract gaps. This spec closes them.

Two parallel lanes, zero file overlap:

- **Lane E** (Codex Agent E): Bug 5 + Bug 7 — generator output formatting (`agents/generator.md` only).
- **Lane F** (Codex Agent F): Bug 6 + Bug 8 — validator strictness (`dashboard/server.py` only).

---

## Bug 5 — Generator must embed JSON-LD inside the rendered HTML, not just emit it as a side artefact

### Reproduction (from run `2026-04-25T13-47-29`)

`validate_article` returned `schema_checks.passed_embedded_jsonld = false` for both articles. The generator wrote `optimised/{slug}.schema.json` as a separate artefact, but the validator parses the rendered HTML at `optimised/{slug}.html` and looks for `<script type="application/ld+json">` blocks. None present.

### Root-cause hypothesis

The generator's draft contract treats schema.json as a sibling output, not as content that must also live inside the HTML. The current prompt likely says "write the schema as a JSON-LD object" without specifying inline embedding.

### Fix scope

`agents/generator.md` only:

- Update the draft-output contract to require:
  - The HTML file MUST contain at least one `<script type="application/ld+json">…</script>` block in the `<head>` containing the canonical schema object (same content as `schema.json`).
  - Multiple schema types may share one block via `@graph` or be split into multiple blocks; either is acceptable.
  - The standalone `schema.json` artefact remains for downstream tooling, but the embedded copy is the source of truth for validation.
- The prompt must give a concrete example HTML snippet so the generator doesn't drift on whitespace/format.

### Acceptance test

`tests/bug_05_jsonld_embedded_in_html_test.md` (NEW):

1. Run pipeline against any 1 article.
2. Read `optimised/{slug}.html` content.
3. Assert `<script type="application/ld+json">` appears at least once in the file.
4. Parse the JSON inside the script tag — must be valid JSON, must contain `@context`, `@type`, and a non-empty `headline` (or `name` for non-article types).
5. Call `validate_article(run_id, slug)` — `schema_checks.passed_embedded_jsonld` MUST be `true`.

---

## Bug 6 — Validator must treat all `*.<site_key>` subdomains as internal links

### Reproduction

`validate_article` returned `internal_link_count = 1` for both articles. Manual inspection of the optimised HTML showed 3+ links, several to `docs.granola.ai`. The validator's domain matcher only accepts exact `granola.ai` host, so `docs.granola.ai`, `www.granola.ai`, `app.granola.ai`, etc. are all classified as external.

### Root-cause hypothesis

Inside `validate_article` (`dashboard/server.py`), the internal-link tally compares `urlparse(href).hostname` exactly to `site_key`. It should accept any host that ends with `.<site_key>` or equals `site_key` or equals `www.<site_key>`.

### Fix scope

`dashboard/server.py` only — likely in `_tool_validate_article` or its helpers:

- Refactor the internal-link domain check to a small helper:
  ```python
  def _is_internal_host(host: str, site_key: str) -> bool:
      if not host:
          return False
      host = host.lower().lstrip("www.")
      site = site_key.lower().lstrip("www.")
      return host == site or host.endswith("." + site)
  ```
- Apply this helper everywhere the validator currently does an exact host match for internal-link counting and for any sitemap / canonical / nav-link checks that share the same logic.
- Do not change the threshold (whatever it is); this is purely about correctly classifying links that already exist.

### Acceptance test

`tests/bug_06_internal_link_domain_test.md` (NEW):

1. Construct a fixture article with 4 hrefs in body: `https://www.granola.ai/team`, `https://docs.granola.ai/api`, `https://app.granola.ai/login`, `https://example.com/external`.
2. Call `validate_article` on the fixture.
3. Assert `internal_link_count == 3` (the three granola.ai-anything links are internal; example.com is external).

---

## Bug 7 — Generator must output FAQ blocks the validator can extract

### Reproduction

`validate_article` returned `faq_questions_visible = []` for both articles, even though both rendered drafts include FAQ-style content per the recommendations. The validator extracts FAQ via DOM-pattern lookup; the generator's output didn't match the pattern.

### Root-cause hypothesis

The validator likely looks for `<dl><dt>…</dt><dd>…</dd></dl>` structure (definition list semantics for FAQ — the schema.org `FAQPage` mainEntity expectation). The generator emits questions as `<h3>` headings followed by `<p>` answers, which the validator's pattern doesn't catch.

### Fix scope

`agents/generator.md` only:

- Update the draft contract: any FAQ section in the draft MUST use `<dl><dt>Question text?</dt><dd>Answer paragraph.</dd></dl>` format.
- If the recommendations don't explicitly call for an FAQ section, the generator MAY add one when at least 3 distinct user-question patterns are detectable in the recommendations (e.g. "How do I…", "What is…", "Can Granola…").
- Provide a concrete example block in the prompt so the generator doesn't fall back to heading-based FAQ.

### Acceptance test

`tests/bug_07_faq_visible_test.md` (NEW):

1. Run pipeline against 1 article whose recommendations imply or include an FAQ.
2. Read `optimised/{slug}.html`. Assert it contains at least one `<dl>…<dt>…</dt><dd>…</dd>…</dl>` structure.
3. Call `validate_article` — `faq_questions_visible` array MUST contain at least one extracted question text.

---

## Bug 8 — Validator must handle empty `reviewers.json` gracefully (fallback to article author)

### Reproduction

`validate_article` returned `trust_block.passed = false` because `site/reviewers.json` is an empty JSON array (`[]`). The articles themselves clearly name authors (Chris Pedregal for series-c, Jack and Dante for the engineering posts), but the validator only consults `reviewers.json` and ignores `articles/{slug}.json` `trust.author`.

### Root-cause hypothesis

In `dashboard/server.py` `_tool_validate_article` (or the trust check inside it), the reviewer match is too strict: it looks up reviewers in `site/reviewers.json` only and fails when the array is empty.

### Fix scope

`dashboard/server.py` only:

- Modify the trust-block check inside `validate_article`:
  - First pass: try to match the article's named author against `site/reviewers.json` entries (existing behaviour).
  - If `reviewers.json` is empty AND the article's `trust.author.name` is non-empty AND the author has at least a first AND last name (i.e., name contains at least one space and is not a common single-word handle), accept the author as the trust signal and set `trust_block.passed = true` with `trust_block.source = "article_author_fallback"`.
  - If even that fails, keep the existing `trust_block.passed = false`.
- This is a softening of the strict reviewer requirement that matches the practical reality of single-author engineering blog posts and announcement posts where there isn't yet a separate review pipeline.

### Acceptance test

`tests/bug_08_trust_block_author_fallback_test.md` (NEW):

1. Set `site/reviewers.json` to `[]`.
2. Construct a fixture article with `trust.author.name = "Chris Pedregal"`.
3. Call `validate_article`. Assert `trust_block.passed == true` and `trust_block.source == "article_author_fallback"`.
4. Construct a second fixture with `trust.author.name = "Jack"` (single name).
5. Call `validate_article`. Assert `trust_block.passed == false` (single name is too weak for fallback).
6. Reset `site/reviewers.json` to a non-empty array including the article's author. Call `validate_article`. Assert `trust_block.passed == true` and `trust_block.source == "reviewers_json"`.

---

## Lane assignment

- **Lane E** (Codex Agent E): Bugs 5 + 7. Branch `fix/v0.5.8-lane-e` off `fix/v0.5.7-bugs-integration`. Worktree `~/conductor/workspaces/ai-search-blog-optimiser/lane-e`. Files: `agents/generator.md`, two new test files.
- **Lane F** (Codex Agent F): Bugs 6 + 8. Branch `fix/v0.5.8-lane-f` off `fix/v0.5.7-bugs-integration`. Worktree `~/conductor/workspaces/ai-search-blog-optimiser/lane-f`. Files: `dashboard/server.py`, two new test files.

After both lanes finish, merge into `fix/v0.5.8-bugs-integration`, bump `plugin.json` to 0.5.8, update CHANGELOG, sync to marketplace cache, re-run the 2-article subprocess smoke.

## Definition of done (whole iteration 2)

- All 4 acceptance tests pass.
- Re-run smoke produces:
  - `granola-chat-just-got-smarter` `audit_after >= 32` AND `quality_gate = "passed"`.
  - `series-c` `audit_after >= 32` AND `quality_gate = "passed"`.
  - `schema_checks.passed_embedded_jsonld = true` for both.
  - `internal_link_count >= 2` for both.
  - `faq_questions_visible.length >= 1` for both.
  - `trust_block.passed = true` for both (via reviewers.json or fallback).
- `plugin.json` bumped to `0.5.8`.
- CHANGELOG documents iteration 2.
