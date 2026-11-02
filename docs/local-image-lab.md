# DCP Local Image Lab

## Phase 1: Mock-only

This phase validates the local build lifecycle and evidence contract without
starting Docker, WSL, a VM, a cloud provider, or a network connection.

The blueprint is declarative JSON. Its `build_mode` must be `mock`.
The backend reads and validates the blueprint, calculates its SHA-256, and
writes a JSON evidence record tied to a full 40-character source Git SHA.

## Evidence semantics

`SIMULATED_PASS` means only that the mock lifecycle and evidence write completed.
It does not mean a container image was built, tested, scanned, or deployed.

The evidence explicitly records:
- `docker_invoked: false`
- `image_built: false`
- `network_used: false`
- `cloud_provider_used: false`
- `vm_created: false`

Evidence files are written under the caller-selected local evidence directory.
Do not commit generated run evidence.

## Run tests

    python -m unittest discover -s tests -p "test_local_image_lab.py" -v

    python -m unittest discover -s tests -v

## Safety boundary

No subprocess, shell command, Docker SDK, HTTP client, or provider adapter is
used by this module. Real Docker builds require a separately reviewed phase,
explicit user approval, and a verified Docker Engine.
