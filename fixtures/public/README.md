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

The builder embeds a Chinese TrueType font so the fixture renders in browser and desktop
PDF viewers. On systems without a supported font in a standard location, set
`PUBLIC_FIXTURE_FONT` to a local TTF/TTC file before rebuilding.

The fixture exercises PDF validation, page rendering, auxiliary-text extraction,
protocol parsing, range resolution, validation and artifact publication. Because the
semantic response is frozen, it does not measure live-model accuracy.

Both pages are uploaded as one PDF and therefore form one published tree asset. The
expected tree has exactly one document root; `七年级上册` and `七年级下册` are range nodes
under that root, not sibling roots.
