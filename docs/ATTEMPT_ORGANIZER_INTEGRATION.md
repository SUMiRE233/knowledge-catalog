# attempt-organizer integration contract

Knowledge Catalog publishes immutable, versioned JSON assets. It does not implement or
invoke attempt-organizer runtime logic.

## Stable asset

- Logical name: `KT_MICSS_junior`
- Current catalog version: `1.0.0`
- Tree: `releases/v1.0.0/KT_MICSS_junior.json`
- Manifest: `releases/v1.0.0/KT_MICSS_junior.manifest.json`
- JSON Schema: `schemas/knowledge_tree.schema.json` (`1.0.0`)

Canonical external request:

```json
{
  "knowledge_tree_file": "KT_MICSS_junior"
}
```

The receiving layer resolves the logical name to `KT_MICSS_junior.json`. A caller may
still send `KT_MICSS_junior.json` for backward compatibility, but examples and new
integrations must use the extensionless form.

## Consumer expectations

1. Resolve the release through `releases/catalog-index.json` or pin `v1.0.0`.
2. Verify the artifact SHA-256 from the manifest before deployment.
3. Treat node IDs as stable only within the pinned catalog version.
4. Read only `id`, `name`, `scope`, and `children` from nodes.
5. Do not infer missing scope, alter hierarchy, or merge equal names across branches.
6. Upgrade only after validating the new manifest/schema versions and recording the
   pinned catalog version with downstream results.
