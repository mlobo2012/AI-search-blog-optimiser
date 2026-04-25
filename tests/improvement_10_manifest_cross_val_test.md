# Improvement 10 Acceptance Test: Manifest Cross-Validation

## Fixture

- Run fixture: `fixtures/v0.6.0/rec-map/run.json`
- Recommendation fixture: `outputs/recommendations/rec-map.json`
- Manifest output: `outputs/optimised/rec-map.manifest.json`
- Recommendation fixture contains two critical LLM-source recs: `rec-001` and `rec-002`.
- `rec-001` is implementable.
- `rec-002` is non-applicable.

## Steps

1. Run the generator for `rec-map`.
2. Read `outputs/optimised/rec-map.manifest.json`.
3. Run `validate_article(run_id, "rec-map")`.
4. Mutate a copy of the manifest for each failure assertion below and rerun `validate_article`.

## Assertions

- Passing manifest has `rec_implementation_map.rec-001.implemented == true`.
- Passing manifest has non-empty `rec_implementation_map.rec-001.section`.
- Passing manifest has non-empty `rec_implementation_map.rec-001.anchor`.
- Passing manifest has non-empty `rec_implementation_map.rec-001.schema_fields[]` or non-empty `rec_implementation_map.rec-001.evidence_inserted[]`.
- Passing manifest has `rec_implementation_map.rec-002.implemented == false`.
- Passing manifest has `rec_implementation_map.rec-002.reason == "non-applicable"`.
- Validator passes with complete valid map: `quality_gate.passed == true`.
- Validator fails when `rec-001` is missing from the map: `quality_gate.passed == false` and `quality_gate.blocking_issues.length >= 1`.
- Validator fails when `rec-001.implemented == true` but `section`, `anchor`, and both implementation arrays are missing.
- Validator fails when `rec-002.implemented == false` and `reason` is missing or not one of `non-applicable`, `data_missing`, or `superseded_by_<rec_id>`.
