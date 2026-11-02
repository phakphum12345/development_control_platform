# macOS Cloud Runner Control Plane (legacy documentation link)

The canonical and current documentation is now
[docs/cloud-runner-control-plane.md](cloud-runner-control-plane.md).

This file is retained so existing links do not break. The earlier webhook
contract described here is historical and is **not** the implemented adapter
contract. The current adapter sends:

- `POST /v1/runners` to request a runner.
- `GET /v1/runners/{id}` to inspect lifecycle state.
- `DELETE /v1/runners/{id}` to request teardown.

The provider must return a JSON object containing non-empty string fields
`id` and `state`; optional `runner_name` and `detail` must be strings,
and `labels` must be a list of strings.

No cloud provider is selected, configured, or provisioned by this repository.
A successful mock test is not evidence of a live VM, registered runner, or
macOS build.
