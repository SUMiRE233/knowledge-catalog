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

## BC-005: cover-page Vanguard batches contain no node hierarchy

- Observed failure: a batch containing only covers or publication notes correctly found
  no knowledge-node levels, but strict partial validation rejected it before later
  curriculum pages could establish the document structure.
- Error type: partial-document evidence was validated as if it were a final profile.
- Correction: partial LayoutProfiles may describe exclusion-only pages with empty
  `node_levels`; the final merged and reviewed profile must still contain an extractable
  hierarchy and must not retain blocking unresolved items.
- Regression evidence: `tests/unit/test_layout_profile.py` covers partial acceptance and
  final-profile rejection.
- Boundary: allowing an empty partial profile does not create a fallback extractor; an
  unresolved final layout still fails with `VANGUARD_LAYOUT_UNRESOLVED`.

## BC-006: explicit numbered children were swallowed into a parent scope

- Observed failure: a real visual-table run attached several explicitly numbered child
  items to the parent `SCOPE`, producing a shallower tree and a non-leaf scope.
- Error type: semantic-role conflict during cross-page consolidation.
- Correction: the composed extraction/merge/review prompts require explicit child rows
  to remain nodes. `OutputGuard` now rejects numbered-node content inside scope and any
  scope attached to a node that also has children.
- Regression evidence: `tests/unit/test_parser_guard.py` and the real Qwen smoke audit.
- Boundary: code detects structural risk but does not decide how ambiguous prose should
  be split; genuinely ambiguous rows remain a model or human-review decision.

## BC-007: one PDF was published as multiple sibling roots

- Observed failure: the two-page public synthetic PDF placed `七年级上册` and
  `七年级下册` at separate LEVEL 1 roots instead of ranges below one document root.
- Error type: document ranges were misclassified as asset roots, producing a forest.
- Correction: LayoutProfile permits at most one `root_labels` item; Vanguard and business
  prompts treat all internal batches as parts of one PDF asset; the final Pipeline rejects
  anything other than exactly one LEVEL 1 after merge/review. Unknown identity uses the
  same single-root invariant through the fixed `未知学科` root.
- Regression evidence: the public fixture now has one document root, two range nodes and
  a 41-item candidate gold set; unit and integration tests cover multiple-profile-root and
  multiple-final-root rejection.
- Boundary: upstream must submit one PDF whose pages are intended to form one catalog.
  Unrelated curricula that require separate publication must use separate requests.
