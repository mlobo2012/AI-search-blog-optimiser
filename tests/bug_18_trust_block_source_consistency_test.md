# Bug 18 Acceptance Test: trust_block Source Consistency

## Fixtures

- Unit fixture A: passed `author_validation` with `reviewer_id: null` and `display_name: "Chris Pedregal"`.
- Unit fixture B: passed `author_validation` with `reviewer_id: "chris-pedregal"` and `display_name: "Chris Pedregal"`.
- Negative fixture: failed `author_validation`, regardless of reviewer provenance.
- Full validation fixture: canonical article with a non-null reviewer-backed author.

## Steps

```sh
python3 - <<'PY'
from dashboard.quality_gate import _validate_trust_block

cases = [
    (
        {"status": "passed", "reviewer_id": None, "display_name": "Chris Pedregal"},
        {"passed": True, "source": "author_validation", "author_name": "Chris Pedregal"},
    ),
    (
        {"status": "passed", "reviewer_id": "chris-pedregal", "display_name": "Chris Pedregal"},
        {"passed": True, "source": "author_validation", "author_name": "Chris Pedregal"},
    ),
    (
        {"status": "failed", "reviewer_id": "chris-pedregal", "display_name": "Chris Pedregal"},
        {"passed": False, "source": "author_validation", "author_name": ""},
    ),
]

for payload, expected in cases:
    actual = _validate_trust_block(payload, [])
    assert actual == expected, (payload, actual, expected)
PY

RUN="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/2026-04-25T20-12-28"
python3 dashboard/quality_gate.py "$RUN" series-c || true

SERIES_C_MANIFEST="$RUN/outputs/optimised/series-c.manifest.json"
```

The command can return non-zero while unrelated blocking issues from other lanes remain. The assertions below are scoped to Bug 18.

## Unit Assertions

```sh
python3 - <<'PY'
from dashboard.quality_gate import _validate_trust_block

assert _validate_trust_block(
    {"status": "passed", "reviewer_id": None, "display_name": "Chris Pedregal"},
    [],
) == {"passed": True, "source": "author_validation", "author_name": "Chris Pedregal"}

assert _validate_trust_block(
    {"status": "passed", "reviewer_id": "chris-pedregal", "display_name": "Chris Pedregal"},
    [],
) == {"passed": True, "source": "author_validation", "author_name": "Chris Pedregal"}

assert _validate_trust_block(
    {"status": "failed", "reviewer_id": "chris-pedregal", "display_name": "Chris Pedregal"},
    [],
) == {"passed": False, "source": "author_validation", "author_name": ""}
PY
```

## Full validate_article jq Assertions

```sh
jq -e '.author_validation.status == "passed"' "$SERIES_C_MANIFEST"
jq -e '.author_validation.display_name == "Chris Pedregal"' "$SERIES_C_MANIFEST"
jq -e '.author_validation.reviewer_id == "chris-pedregal"' "$SERIES_C_MANIFEST"
jq -e '.trust_block.passed == true' "$SERIES_C_MANIFEST"
jq -e '.trust_block.source == "author_validation"' "$SERIES_C_MANIFEST"
jq -e '.trust_block.source != "reviewers_json"' "$SERIES_C_MANIFEST"
jq -e '.trust_block.author_name == .author_validation.display_name' "$SERIES_C_MANIFEST"
```
