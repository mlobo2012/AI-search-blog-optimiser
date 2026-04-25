# GEO Article Contract v1

This contract is the plugin-local source of truth for recommendation scoring and draft generation.

It distills the Schmidt, Peec, and Profound guidance already adopted in this project into a format
that the recommender and generator can apply without depending on external skill bundles at runtime.

## Universal required modules

Every optimized article must satisfy these unless the article type makes a module genuinely
inapplicable. If a universal module is missing, the draft cannot pass.

1. `tldr_block`
   - A visible `TL;DR` block at the top of the article.
   - 30-60 words.
   - Direct answer, not scene-setting.

2. `trust_block`
   - Visible full-name author. Do not treat `Team`, `Staff`, or first-name-only bylines as a
     passing trust block.
   - Visible role or credential context relevant to the article.
   - Visible published and updated dates.
   - For security, comparison, and workflow claims, add a visible evidence or reviewer line if the
     source author is not obviously the subject-matter owner.

3. `question_headings`
   - H2/H3 headings should mirror likely user prompts whenever the article type allows.
   - Avoid vague marketing headings like `Our approach`.

4. `atomic_paragraphs`
   - Primary claims should be written in short, chunkable paragraphs.
   - Dense prose blocks should be broken apart.

5. `inline_evidence`
   - Key factual claims should be supported by named evidence, product proof, or cited sources.
   - Do not count unlabeled brand assertions as evidence.
   - Pages making security, comparison, or workflow claims should usually contain at least 3 inline
     named evidence references.
   - At least one evidence reference should be a primary source or an external destination system,
     standard, or institution when the claim type makes that possible.

6. `semantic_html`
   - Use real headings, sections, lists, and tables where appropriate.
   - Do not rely on generic wrapper structure alone.

7. `chunk_complete_sections`
   - Each major section should answer its implied question in isolation.

8. `differentiation`
   - Include at least one brand-specific mechanism, framework, product truth, or concrete point of
     view that prevents sea-of-sameness output.

## Conditional required modules

These modules are required when the article type or article intent makes them applicable.

1. `faq_block`
   - Required when the article naturally supports 3 or more useful Q&A pairs.

2. `faq_schema`
   - Required whenever `faq_block` is present.

3. `table_block`
   - Required when the content involves comparisons, criteria, specs, pricing, rankings, or
     structured rollouts.

4. `howto_steps`
   - Required for how-to content.

5. `howto_schema`
   - Required for how-to content.

6. `comparison_table`
   - Required for comparison intent.

7. `toc_jump_links`
   - Required for pillar or guide content with many sections.

8. `year_modifier`
   - Required for evergreen retrieval pages that compete on current-year demand.
   - Not required for dated launch, announcement, or changelog posts.

9. `specialized_schema`
   - Required whenever a schema more specific than generic article clearly applies.
   - The schema package should also include the core entities needed to make the article legible to
     answer engines: `Organization`, `Person` when a valid author exists, and `BreadcrumbList` for
     standard article pages.

## Article presets

The recommender must classify the article into one of these presets and build the blueprint from
that preset.

- `announcement_update`
- `comparison`
- `how_to`
- `listicle`
- `glossary`
- `case_study`
- `pillar`
- `narrative_editorial`

### `announcement_update`

Must usually include:

- `TL;DR`
- retrieval-oriented title or H1 framing, not just launch copy
- `What changed`
- `How it works`
- `Who it is for`
- `Availability`, rollout, or usage guidance
- FAQ when there are enough natural user questions

### `comparison`

Must usually include:

- answer-first block
- comparison table above the fold
- criteria-based structure
- clear verdict or use-case guidance

### `how_to`

Must usually include:

- answer-first block
- numbered or clearly separated steps
- failure mode or troubleshooting guidance
- HowTo schema

### `pillar`

Must usually include:

- answer-first summary
- TOC with jump links
- section-level completeness
- FAQ when natural

## Audit gate

The generator should fail or mark a draft partial if:

- any universal required module is missing
- any applicable conditional module is missing
- the trust block still relies on an anonymous, team, staff, or first-name-only byline
- the inline evidence standard is not met for the article type
- the schema package omits required core entities or mismatches the visible page structure
- the post-generation audit score is below `32/40`
- the HTML artifact is incomplete or empty

## Recommendation artifact requirements

Every recommendation artifact should make the contract explicit:

- identified article preset
- universal module status
- conditional module status
- blocking issues
- section blueprint
- schema blueprint

## Draft manifest requirements

Every generated draft should declare:

- implemented modules
- missing required modules
- audit before and after
- overall quality gate status
- author validation result
- inline evidence count
- schema checks
