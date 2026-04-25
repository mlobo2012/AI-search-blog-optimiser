# Improvement 05 Acceptance Test: Rubric Lint Pre-Pass

## Fixture

- Run fixture: `fixtures/v0.6.0/rubric-gaps/run.json`
- Article fixture: `outputs/articles/rubric-gaps.json`
- Rubric output: `outputs/rubric/rubric-gaps.json`
- Recommendation output: `outputs/recommendations/rubric-gaps.json`
- Article has empty `meta.description`, no JSON-LD, preset `announcement_update`, and byline `Jack`.
- Article has no reviewer fallback in `outputs/evidence/rubric-gaps.json` or `site/voice.json`.

## Steps

1. Run `rubric_lint(run_id, "rubric-gaps")`.
2. Run the recommender for `rubric-gaps`.
3. Read `outputs/rubric/rubric-gaps.json`.
4. Read `outputs/recommendations/rubric-gaps.json`.

## Assertions

- `outputs/rubric/rubric-gaps.json` exists.
- `rubric.items[].id` contains `meta_description_empty`.
- `rubric.items[].id` contains `jsonld_missing`.
- `rubric.items[].id` contains `faq_schema_missing`.
- `rubric.items[].id` contains `byline_weak`.
- Every matching rubric item has `source == "rubric"` and `category == "geo_hygiene"`.
- `recommendations.recommendations[]` contains the same four rubric ids with `source == "rubric"`.
- No `source == "llm"` recommendation has `category == "geo_hygiene"`.
- Every `source == "llm"` recommendation category is one of `claim_synthesis`, `sentiment`, `engine_specific`, `off_page`, `source_displacement`, or `content_gap`.
