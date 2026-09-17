# Evaluation

The current public regression fixture contains 41 manually readable assertions:

- 33 exact hierarchy/path assertions, including the one-root invariant;
- 8 exact scope assertions.

Run it with:

```bash
python scripts/evaluate_public_fixture.py
```

These assertions were authored during implementation and then reviewed and explicitly
approved by the curriculum owner on 2026-09-17. Their status is
`human_approved_synthetic_gold`.

The candidate set is frozen by SHA-256 in
`gold/public_fixture_gold.manifest.json`. The evaluator verifies every frozen file before
running and fails if the fixture, readable specification, deterministic semantic output or
assertions drift. The completed item-by-item decision is recorded in
`PUBLIC_SYNTHETIC_GOLD_REVIEW.md`; approval metadata is recorded in the manifest.

The checked-in result is `results/public_fixture_eval.json`. The dataset is synthetic,
the run count is one, and the semantic executor is a deterministic test double. The
reported 41/41 result therefore proves reproducibility of the preparation, parsing,
validation and publication contract only. It is deliberately not presented as
multimodal-model accuracy on real curricula.

A future unseen-real-PDF blind set would measure live-model generalization. It is a
separate maturity step, not evidence supplied by this synthetic gold set.

Real-document failure modes and their regression boundaries are recorded in
`docs/BADCASES.md` without retaining the private source PDFs.
