# Real badcases and regression boundaries

The cases below were observed during real curriculum runs. Private source documents and
raw model artifacts are intentionally not committed. Each case is tied to a current
rule, prompt, schema decision or explicit human-review boundary.

## BC-001: unsupported default collapsed content into 初一上

- Observed failure: when a document did not provide an explicit grade node, generated
  content was assigned to `初一上` because the prompt example and fallback were treated
  as evidence.
- Error type: unsupported grade inference.
- Correction: `app/range_resolution.py` now resolves exact model evidence, unique
  text/OCR evidence, stage prefix and finally `DEFAULT_GRADE_RANGE=全部` in that order.
  `app/llm/prompts.py` explicitly forbids inventing a concrete grade.
- Regression evidence: `tests/integration/test_api.py::test_range_and_not_found` and
  unit range-resolution coverage.
- Boundary: code may select or fall back among model-produced nodes; it may not infer
  curriculum semantics or manufacture a grade tree.

## BC-002: learning-objective extraction degraded the original hierarchy

- Observed failure: adding learning objectives to chapter nodes caused a real junior
  curriculum run to collapse useful lower-level content into empty chapter nodes.
- Error type: schema expansion changed the model's extraction priority.
- Correction: the experiment was rolled back. The stable node schema contains only
  `id`, `name`, `scope`, and `children`; objectives are excluded by the prompt and schema.
- Regression evidence: `schemas/knowledge_tree.schema.json` has
  `additionalProperties=false`; parser/guard tests reject unsupported protocol content
  and forbidden node fields.
- Boundary: learning objectives may be retained in separate future trace artifacts,
  but are not part of the authoritative catalog contract.

## BC-003: high-school page slice omitted the grade-allocation table

- Observed failure: a content-only page slice produced one `高中数学内容标准` root and no
  `高一上` to `高三下` boundaries, although the full source contained a later allocation
  table.
- Error type: incomplete source selection, not parser data loss.
- Correction: the reviewed tree was re-parented only after checking the authoritative
  allocation table. The isolated publishing tool is
  `scripts/manual_split_high_school_grades.py`; it is not part of the online pipeline.
- Boundary: post-processing must not guess grade allocations. Missing allocation pages
  require a new source selection or an explicitly reviewed manual publication step.

## BC-004: primary DSKP batch merge promoted topics to learning areas

- Observed failure: cross-page batches occasionally promoted topic names to LEVEL 2 and
  one run duplicated year-five units during final merging.
- Error type: cross-batch hierarchy continuation and duplicate merge.
- Correction: `PRIMARY_DSKP_MERGE_PROMPT` restricts LEVEL 2 to visually observed learning
  area boundaries; `primary_level_2_boundaries` supplies those events to a constrained
  review call. Reviewed per-year trees are merged by
  `scripts/merge_primary_knowledge_trees.py`, which rejects missing/duplicate grades and
  duplicate paths.
- Boundary: the profile remains document-family-specific and requires human review
  before a versioned release. It is not claimed as universal DSKP parsing.
