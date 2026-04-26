# v0.6.3 Iteration 7 predicted bug fixes (target: v0.6.4)

Origin: static audit `2026-04-26-iter7-static-audit.md` performed by Codex
GPT-5.5 BEFORE the Round 4 smoke landed. Each bug below is a structural risk
caught by reading the v0.6.3 source, not from a runtime smoke YELLOW.

## Lane assignment

- **Lane J** (Codex Agent J): Bug 18 — `trust_block.source` still writes `reviewers_json` on passed reviewer-backed author validation. File: `dashboard/quality_gate.py`.

Single-file lane only. No Lane K needed unless Round 4 smoke surfaces a separate
file-local failure.

## Bug 18 — `trust_block.source` can be `reviewers_json` while author validation passed

### Symptom

Round 4 GREEN criterion 1 requires every canonical article to return:

- `trust_block.passed == true`
- `trust_block.author_name == author_validation.display_name`
- `trust_block.source == "author_validation"`

The current v0.6.3 code satisfies this for the documented null-`reviewer_id`
canonical path, but not for a passed author validation that carries a non-null
`reviewer_id`. In that path, `trust_block.source` becomes `"reviewers_json"`,
which would make the smoke YELLOW even though the author was accepted.

### Root cause (verified by audit)

`dashboard/quality_gate.py::_validate_trust_block` uses `reviewer_id` to choose
the trust block source after author validation has already passed:

```python
if author_passed and display_name:
    return {
        "passed": True,
        "source": "reviewers_json" if reviewer_id else "author_validation",
        "author_name": display_name,
    }
```

That conditional source violates the Round 4 risk register, which says there
must be no path that writes `"reviewers_json"` while `status == "passed"`.

### Fix

In `dashboard/quality_gate.py`, change the passed branch of
`_validate_trust_block` so `trust_block.source` is always
`"author_validation"` once `author_validation.status == "passed"` and
`display_name` is non-empty:

```python
if author_passed and display_name:
    return {
        "passed": True,
        "source": "author_validation",
        "author_name": display_name,
    }
```

Do not remove reviewer validation. `author_validation.reviewer_id` can continue
to carry reviewer provenance. If a separate diagnostic source is needed, add a
non-gating field in a later version; do not overload `trust_block.source`
against the Round 4 GREEN contract.

### Acceptance test

Add or update a focused validator test for `_validate_trust_block`:

1. Passed author validation with `reviewer_id: null` and
   `display_name: "Chris Pedregal"` returns
   `{"passed": true, "source": "author_validation", "author_name": "Chris Pedregal"}`.
2. Passed author validation with `reviewer_id: "chris-pedregal"` and
   `display_name: "Chris Pedregal"` returns the same `trust_block.source:
   "author_validation"` value, not `"reviewers_json"`.
3. Failed author validation returns `passed: false`, `source:
   "author_validation"`, and empty `author_name`.
4. Full `validate_article` fixture with a non-null reviewer-backed author passes
   quality gate and still reports `trust_block.author_name ==
   author_validation.display_name`.
