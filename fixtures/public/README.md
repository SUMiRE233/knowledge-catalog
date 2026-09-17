# Public fixture

`synthetic_curriculum.pdf` is a fully synthetic, MIT-licensed curriculum table. It is not
derived from a real curriculum standard and contains no private course material.

Files:

- `synthetic_curriculum_spec.json`: human-readable source of truth.
- `synthetic_curriculum.pdf`: two-page visual input used by the reproducible demo.
- `expected_model_output.txt`: deterministic multimodal-client test-double response.

Rebuild the PDF with:

```bash
python scripts/build_public_fixture.py
```

The fixture exercises PDF validation, page rendering, auxiliary-text extraction,
protocol parsing, range resolution, validation and artifact publication. Because the
semantic response is frozen, it does not measure live-model accuracy.
