# neuromorph

Pure-core, data-oriented spiking neural simulation engine driven by a declarative `brain.json`.

- Specification: [`docs/brain-json-spec.md`](docs/brain-json-spec.md) (schema v4.3)
- Reference configuration: [`examples/brain.json`](examples/brain.json)
- Validator: `python3 tools/validate_brain.py examples/brain_extended.json` (requires numpy)
- Training & testing guide: [`docs/training.md`](docs/training.md), harness root [`examples/brain_training.json`](examples/brain_training.json)
