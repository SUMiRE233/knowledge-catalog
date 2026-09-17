# Evaluation

The frozen public evaluation contains 40 manually readable assertions:

- 32 exact hierarchy/path assertions;
- 8 exact scope assertions.

Run it with:

```bash
python scripts/evaluate_public_fixture.py
```

The checked-in result is `results/public_fixture_eval.json`. The dataset is synthetic,
the run count is one, and the semantic executor is a deterministic test double. The
reported 40/40 result therefore proves reproducibility of the preparation, parsing,
validation and publication contract only. It is deliberately not presented as
multimodal-model accuracy on real curricula.

Real-document failure modes and their regression boundaries are recorded in
`docs/BADCASES.md` without retaining the private source PDFs.
