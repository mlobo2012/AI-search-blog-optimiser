# Bug 19 Acceptance Test: trust_block Reviewer Promotion When Source Author Is Weak

## Fixtures

- Promotion fixture: failed source author validation for `Jack Whitton, Marketing`; `reviewers_json` contains active reviewer `Chris Pedregal, CEO & Co-founder` with LinkedIn.
- Strong-author fixture: passed source author validation for `Jane Doe, VP Engineering`; `reviewers_json` is non-empty and must not override the already accepted source author.
- Negative fixture: failed source author validation for `Jack, Marketing`; `reviewers_json` is empty.
- Bug 14 retention fixture: missing source author validation signal; `reviewers_json` contains an active strong reviewer.

## Steps

```sh
python3 - <<'PY'
from dashboard.quality_gate import _validate_trust_block

strong_reviewer = {
    "id": "chris-pedregal",
    "display_name": "Chris Pedregal",
    "display_role": "CEO & Co-founder",
    "linkedin": "https://www.linkedin.com/in/chris-pedregal/",
}

weak_source_author = {
    "status": "failed",
    "display_name": "Jack Whitton",
    "display_role": "Marketing",
    "reviewer_id": None,
    "detail": "Author role is too weak to act as a reviewer-backed trust signal.",
}
actual = _validate_trust_block(weak_source_author, [strong_reviewer])
assert actual == {
    "passed": True,
    "source": "reviewers_json",
    "author_name": "Chris Pedregal",
}, actual
assert weak_source_author["status"] == "passed", weak_source_author
assert weak_source_author["display_name"] == "Chris Pedregal", weak_source_author
assert weak_source_author["display_role"] == "CEO & Co-founder", weak_source_author
assert weak_source_author["reviewer_id"] == "chris-pedregal", weak_source_author
assert weak_source_author["source"] == "reviewers_promoted", weak_source_author
assert weak_source_author["detail"] == (
    "Jack Whitton rejected as Marketing; reviewer Chris Pedregal "
    "(CEO & Co-founder) promoted from reviewers.json."
), weak_source_author

strong_source_author = {
    "status": "passed",
    "display_name": "Jane Doe",
    "display_role": "VP Engineering",
    "reviewer_id": None,
    "detail": "Jane Doe is a visible full-name reviewer with a rendered role line.",
}
assert _validate_trust_block(strong_source_author, [strong_reviewer]) == {
    "passed": True,
    "source": "author_validation",
    "author_name": "Jane Doe",
}
assert strong_source_author["display_name"] == "Jane Doe", strong_source_author
assert strong_source_author["display_role"] == "VP Engineering", strong_source_author

no_reviewer = {
    "status": "failed",
    "display_name": "Jack",
    "display_role": "Marketing",
    "reviewer_id": None,
    "detail": "Visible byline is anonymous, team-based, or missing a full name.",
}
assert _validate_trust_block(no_reviewer, []) == {
    "passed": False,
    "source": "author_validation",
    "author_name": "",
}
assert no_reviewer["status"] == "failed", no_reviewer

missing_source_author = {
    "status": "failed",
    "display_name": "",
    "display_role": "",
    "reviewer_id": None,
    "detail": "Visible byline is anonymous, team-based, or missing a full name.",
}
assert _validate_trust_block(missing_source_author, [strong_reviewer]) == {
    "passed": True,
    "source": "reviewers_json",
    "author_name": "Chris Pedregal",
}
assert missing_source_author["status"] == "passed", missing_source_author
assert missing_source_author["display_name"] == "Chris Pedregal", missing_source_author
assert missing_source_author["source"] == "reviewers_promoted", missing_source_author
PY
```

## Assertions

```sh
python3 - <<'PY'
from dashboard.quality_gate import _validate_trust_block

reviewers = [{
    "id": "chris-pedregal",
    "display_name": "Chris Pedregal",
    "display_role": "CEO & Co-founder",
    "linkedin": "https://www.linkedin.com/in/chris-pedregal/",
}]

payload = {"status": "failed", "display_name": "Jack Whitton", "display_role": "Marketing"}
assert _validate_trust_block(payload, reviewers)["source"] == "reviewers_json"
assert payload["status"] == "passed"
assert payload["display_name"] == "Chris Pedregal"
assert payload["reviewer_id"] == "chris-pedregal"
assert "promoted from reviewers.json" in payload["detail"]

assert _validate_trust_block(
    {"status": "passed", "display_name": "Jane Doe", "display_role": "VP Engineering"},
    reviewers,
) == {"passed": True, "source": "author_validation", "author_name": "Jane Doe"}

assert _validate_trust_block(
    {"status": "failed", "display_name": "Jack", "display_role": "Marketing"},
    [],
) == {"passed": False, "source": "author_validation", "author_name": ""}

missing = {"status": "failed", "display_name": "", "display_role": ""}
assert _validate_trust_block(missing, reviewers) == {
    "passed": True,
    "source": "reviewers_json",
    "author_name": "Chris Pedregal",
}
PY
```
