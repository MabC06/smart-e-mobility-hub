# M8 Artifact Verification Notes

- Repository snapshot: GitHub/local ZIP supplied by user after syncing `develop` to `6777736`.
- Python test command: `PYTHONPATH=src python -m pytest tests/iot_sim -q`
- Result: **13 passed**.
- Ruff was not available in the artifact-build environment (`ruff: command not found`); run it in the user's project `.venv`.
- Full repository test suite was not run as part of this artifact build.
- All test-case rows remain `Planned` until the user runs the tests in their actual project environment and records the result.
