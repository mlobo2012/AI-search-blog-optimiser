# Bug 15 Acceptance Test - Rec Implementation Format

Executable checklist for Lane H.

## Setup

- [ ] Use a fixture run with two critical LLM-source recommendations: `rec-001` and `rec-002`.
- [ ] Run the generator through `record_draft_package`.
- [ ] Set:

```sh
RUN_DIR="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/<run_id>"
SLUG="<article_slug>"
MANIFEST="$RUN_DIR/outputs/optimised/$SLUG.manifest.json"
BAD_MANIFEST="$RUN_DIR/outputs/optimised/$SLUG.bug-15-legacy-rec-map.manifest.json"
BAD_RUN_DIR="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/<bad_run_id>"
BAD_VALIDATED="$BAD_RUN_DIR/outputs/optimised/$SLUG.manifest.json"
```

## Positive Path Assertions

- [ ] Manifest has a `rec_implementation_map.rec-001` object.

```sh
jq -e '.rec_implementation_map["rec-001"] | type == "object"' "$MANIFEST"
```

- [ ] `rec-001.implemented` exists and is boolean `true`.

```sh
jq -e '.rec_implementation_map["rec-001"].implemented == true' "$MANIFEST"
jq -e '.rec_implementation_map["rec-001"].implemented | type == "boolean"' "$MANIFEST"
```

- [ ] `rec-001` does not use the legacy `status` field.

```sh
jq -e '.rec_implementation_map["rec-001"] | has("status") | not' "$MANIFEST"
```

- [ ] `rec-001.section` is non-empty.

```sh
jq -e '.rec_implementation_map["rec-001"].section | type == "string" and length > 0' "$MANIFEST"
```

- [ ] `rec-001.anchor` is non-empty.

```sh
jq -e '.rec_implementation_map["rec-001"].anchor | type == "string" and length > 0' "$MANIFEST"
```

- [ ] `rec-001` has at least one non-empty implementation evidence array.

```sh
jq -e '
  .rec_implementation_map["rec-001"] as $entry
  | (($entry.schema_fields // []) | type == "array" and length > 0)
    or (($entry.evidence_inserted // []) | type == "array" and length > 0)
' "$MANIFEST"
```

- [ ] Validator passes the manifest.

```sh
python3 dashboard/quality_gate.py "$RUN_DIR" "$SLUG"
jq -e '.quality_gate.passed == true' "$MANIFEST"
```

## Negative Path Assertions

- [ ] Build a legacy-shape manifest copy with `{"status": "implemented"}` for `rec-001`.

```sh
jq '.rec_implementation_map["rec-001"] = {"status": "implemented"}' "$MANIFEST" > "$BAD_MANIFEST"
```

- [ ] Bad manifest contains the legacy `status` field and no `implemented` key.

```sh
jq -e '.rec_implementation_map["rec-001"].status == "implemented"' "$BAD_MANIFEST"
jq -e '.rec_implementation_map["rec-001"] | has("implemented") | not' "$BAD_MANIFEST"
```

- [ ] Copy the bad manifest into a duplicate fixture run, then run validation.

```sh
cp "$BAD_MANIFEST" "$BAD_VALIDATED"
! python3 dashboard/quality_gate.py "$BAD_RUN_DIR" "$SLUG"
```

- [ ] Validator blocks the legacy shape with a rec implementation format defect.

```sh
jq -e '.quality_gate.passed == false' "$BAD_VALIDATED"
jq -e '
  [.quality_gate.blocking_issues[]? | select(. == "rec-001 has no valid implementation entry")]
  | length >= 1
' "$BAD_VALIDATED"
```

## Pass Criterion

All positive jq assertions exit with status `0`; the legacy `status` shape exits non-zero through
`quality_gate.py` and leaves `rec-001 has no valid implementation entry` in
`quality_gate.blocking_issues`.
