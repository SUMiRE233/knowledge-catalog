# Versioned releases

`catalog-index.json` maps a stable logical name to the latest immutable version. Each
version directory contains the downstream-compatible tree and a provenance manifest.

Source PDFs are not distributed here. The manifest records their SHA-256 and explicitly
states whether the source is included. Catalog releases must be produced from a reviewed
tree with `scripts/publish_catalog.py`; ad-hoc runtime artifacts are not releases.
