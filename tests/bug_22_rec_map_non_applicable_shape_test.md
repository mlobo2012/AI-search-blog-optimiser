# Bug 22 Acceptance Test - Rec Implementation Non-Applicable Shape

Executable checklist for Lane M.

## Fixtures

- Unit fixture with one critical LLM-source recommendation: `rec-001`.
- Positive implemented entry uses the Bug 15 shape.
- Positive non-applicable entry uses the new sentinel shape.
- Negative entries cover missing and unsupported `reason` values.

## Steps

```sh
python3 - <<'PY'
from dashboard.quality_gate import _validate_rec_implementation

recommendations = {
    "recommendations": [
        {"id": "rec-001", "priority": "critical", "source": "llm"},
    ],
}

implemented_manifest = {
    "rec_implementation_map": {
        "rec-001": {
            "implemented": True,
            "section": "Trust signals",
            "anchor": "#trust-signals",
            "schema_fields": ["ld.BlogPosting.author"],
            "evidence_inserted": [],
            "notes": "Added reviewer-backed author schema.",
        },
    },
}
assert _validate_rec_implementation(implemented_manifest, recommendations) == []

non_applicable_manifest = {
    "rec_implementation_map": {
        "rec-001": {
            "implemented": False,
            "reason": "non-applicable",
        },
    },
}
assert _validate_rec_implementation(non_applicable_manifest, recommendations) == []

case_variant_manifest = {
    "rec_implementation_map": {
        "rec-001": {
            "implemented": False,
            "reason": "OUT_OF_SCOPE",
        },
    },
}
assert _validate_rec_implementation(case_variant_manifest, recommendations) == []

missing_reason_manifest = {
    "rec_implementation_map": {
        "rec-001": {
            "implemented": False,
        },
    },
}
missing_reason_issues = _validate_rec_implementation(missing_reason_manifest, recommendations)
assert missing_reason_issues == [
    "rec-001 has non-implemented entry without required reason",
], missing_reason_issues

invalid_reason_manifest = {
    "rec_implementation_map": {
        "rec-001": {
            "implemented": False,
            "reason": "made-up-string",
        },
    },
}
invalid_reason_issues = _validate_rec_implementation(invalid_reason_manifest, recommendations)
assert len(invalid_reason_issues) == 1, invalid_reason_issues
assert "unsupported non-implemented reason 'made-up-string'" in invalid_reason_issues[0], invalid_reason_issues
PY
```

## Assertions

- [ ] `{implemented: true, section, anchor, schema_fields, evidence_inserted, notes}` passes.
- [ ] `{implemented: false, reason: "non-applicable"}` passes.
- [ ] Reason matching is case-insensitive and accepts underscores in place of hyphens.
- [ ] `{implemented: false}` rejects with `rec-001 has non-implemented entry without required reason`.
- [ ] `{implemented: false, reason: "made-up-string"}` rejects with an unsupported-reason banner.

## Pass Criterion

The Python assertions exit with status `0`. The validator accepts both documented
rec_implementation_map shapes and rejects only missing or unsupported
non-implemented reasons.
