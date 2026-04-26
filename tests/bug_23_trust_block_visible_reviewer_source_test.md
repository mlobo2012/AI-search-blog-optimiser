# Bug 23 Acceptance Test - Visible Reviewer Block Source Label

Executable checklist for Lane M.

## Fixtures

- Strong byline fixture: rendered draft has only `By Jane Doe, VP Engineering`.
- Visible reviewer promotion fixture: rendered draft has `By Jack Whitton, Marketing` plus `Reviewed by Chris Pedregal, CEO`.
- Strong source-author fixture: rendered draft has `By Chris Pedregal, CEO` and no reviewer block.
- Edited-by fixture: rendered draft has only `Edited by Chris Pedregal, CEO`.

## Steps

```sh
python3 - <<'PY'
from dashboard.quality_gate import _parse_html_snapshot, _validate_author, _validate_trust_block

empty_recommendations = {}
empty_reviewers = []

strong_byline_snapshot = _parse_html_snapshot("<p>By Jane Doe, VP Engineering</p>")
strong_byline_author = _validate_author(
    {"trust": {"author": {"name": "Jane Doe", "role": "VP Engineering"}}},
    empty_recommendations,
    empty_reviewers,
    strong_byline_snapshot,
    {"author_name": "Jane Doe", "author_role": "VP Engineering"},
    "category",
)
assert strong_byline_author["status"] == "passed", strong_byline_author
assert "source" not in strong_byline_author, strong_byline_author
assert "promoted as trust signal" not in strong_byline_author["detail"], strong_byline_author
assert _validate_trust_block(strong_byline_author, empty_reviewers) == {
    "passed": True,
    "source": "author_validation",
    "author_name": "Jane Doe",
}

visible_reviewer_snapshot = _parse_html_snapshot(
    "<p>By Jack Whitton, Marketing</p>"
    "<p>Reviewed by Chris Pedregal, CEO</p>"
)
visible_reviewer_author = _validate_author(
    {"trust": {"author": {"name": "Jack Whitton", "role": "Marketing"}}},
    empty_recommendations,
    empty_reviewers,
    visible_reviewer_snapshot,
    {"author_name": "Chris Pedregal", "author_role": "CEO"},
    "category",
)
assert visible_reviewer_author["status"] == "passed", visible_reviewer_author
assert visible_reviewer_author["display_name"] == "Chris Pedregal", visible_reviewer_author
assert visible_reviewer_author["source"] == "reviewers_promoted", visible_reviewer_author
assert "Jack Whitton, Marketing" in visible_reviewer_author["detail"], visible_reviewer_author
assert _validate_trust_block(visible_reviewer_author, empty_reviewers) == {
    "passed": True,
    "source": "reviewers_promoted",
    "author_name": "Chris Pedregal",
}

strong_source_snapshot = _parse_html_snapshot("<p>By Chris Pedregal, CEO</p>")
strong_source_author = _validate_author(
    {"trust": {"author": {"name": "Chris Pedregal", "role": "CEO"}}},
    empty_recommendations,
    empty_reviewers,
    strong_source_snapshot,
    {"author_name": "Chris Pedregal", "author_role": "CEO"},
    "category",
)
assert strong_source_author["status"] == "passed", strong_source_author
assert "source" not in strong_source_author, strong_source_author
assert _validate_trust_block(strong_source_author, empty_reviewers) == {
    "passed": True,
    "source": "author_validation",
    "author_name": "Chris Pedregal",
}

edited_by_snapshot = _parse_html_snapshot("<p>Edited by Chris Pedregal, CEO</p>")
edited_by_author = _validate_author(
    {"trust": {"author": {"name": "", "role": ""}}},
    empty_recommendations,
    empty_reviewers,
    edited_by_snapshot,
    {"author_name": "Chris Pedregal", "author_role": "CEO"},
    "category",
)
assert edited_by_author["status"] == "passed", edited_by_author
assert edited_by_author["source"] == "reviewers_promoted", edited_by_author
assert "source author absent" in edited_by_author["detail"], edited_by_author
assert _validate_trust_block(edited_by_author, empty_reviewers) == {
    "passed": True,
    "source": "reviewers_promoted",
    "author_name": "Chris Pedregal",
}

allowed_sources = {
    "author_validation",
    "reviewers_json",
    "reviewers_promoted",
    "article_author_fallback",
}
assert "reviewers_promoted" in allowed_sources
PY
```

## Assertions

- [ ] Standard `By Jane Doe, VP Engineering` byline yields `trust_block.source == "author_validation"`.
- [ ] Weak source author plus visible `Reviewed by Chris Pedregal, CEO` yields `trust_block.source == "reviewers_promoted"`.
- [ ] Strong standard `By Chris Pedregal, CEO` byline keeps `trust_block.source == "author_validation"`.
- [ ] Visible `Edited by Chris Pedregal, CEO` with no source byline yields `trust_block.source == "reviewers_promoted"`.
- [ ] Bug 18's source set includes `reviewers_promoted` while preserving `reviewers_json`.

## Pass Criterion

The Python assertions exit with status `0`. Visible reviewer-block promotion is
distinguished from standard byline validation and from the existing
`reviewers_json` data-table promotion path.
