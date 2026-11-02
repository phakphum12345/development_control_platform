"""Mock-only local image build lifecycle.

This module never invokes Docker, a shell, a network client, or a cloud provider.
A SIMULATED_PASS is not evidence that a real container image was built.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_IMAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,127}$")
_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_blueprint(path: str | Path) -> tuple[dict[str, Any], str]:
    """Read and validate a JSON blueprint without executing its contents."""
    blueprint_path = Path(path)
    raw = blueprint_path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("blueprint must be valid UTF-8 JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("blueprint root must be a JSON object")
    if data.get("schema_version") != 1:
        raise ValueError("unsupported blueprint schema_version")
    if data.get("build_mode") != "mock":
        raise ValueError("only build_mode=mock is permitted in this phase")

    name, tag, base = data.get("image_name"), data.get("tag"), data.get("base_image")
    if not isinstance(name, str) or not _IMAGE_NAME.fullmatch(name):
        raise ValueError("invalid image_name")
    if not isinstance(tag, str) or not _TAG.fullmatch(tag):
        raise ValueError("invalid image tag")
    if not isinstance(base, str) or not base.strip() or len(base) > 256:
        raise ValueError("base_image must be a non-empty string")

    return data, sha256_bytes(raw)


def run_mock_build(
    blueprint_path: str | Path,
    evidence_root: str | Path,
    source_sha: str,
) -> dict[str, Any]:
    """Create a clearly labelled simulation record; never create an image."""
    if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
        raise ValueError("source_sha must be a full 40-character Git SHA")

    blueprint, blueprint_sha = load_blueprint(blueprint_path)
    run_id = f"mock-{uuid.uuid4().hex}"
    output_root = Path(evidence_root)
    output_root.mkdir(parents=True, exist_ok=True)

    evidence = {
        "contract": "dcp.local-image-lab.evidence.v1",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "SIMULATED_PASS",
        "execution_mode": "mock",
        "source_sha": source_sha.lower(),
        "blueprint_sha256": blueprint_sha,
        "image": {
            "name": blueprint["image_name"],
            "tag": blueprint["tag"],
            "base_image": blueprint["base_image"],
        },
        "execution": {
            "docker_invoked": False,
            "network_used": False,
            "cloud_provider_used": False,
            "vm_created": False,
            "image_built": False,
        },
        "limitations": [
            "Mock simulation only",
            "No Docker daemon or image build was used",
            "SIMULATED_PASS is not a real image-build PASS",
        ],
    }

    destination = output_root / f"{run_id}.json"
    temporary = output_root / f".{run_id}.tmp"
    encoded = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    evidence["evidence_path"] = str(destination)
    evidence["evidence_sha256"] = sha256_bytes(encoded)
    return evidence
