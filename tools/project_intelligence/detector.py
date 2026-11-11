"""Read-only project framework and toolchain manifest detection.

This module inspects a bounded set of project-root manifests only. It never
installs dependencies, invokes package managers, executes source, or probes
external services. Toolchain constraints are declarations, not readiness.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Any


_MAX_MANIFEST_BYTES = 1024 * 1024
_MANIFESTS = (
    "package.json", "index.html", "pyproject.toml", "requirements.txt",
    "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock",
    "pubspec.yaml", "pubspec.lock", "angular.json", "next.config.js",
    "next.config.mjs", "next.config.ts", "vite.config.js", "vite.config.ts",
    "vite.config.mjs", "vite.config.cjs", "vue.config.js",
)


class ProjectDetectionError(ValueError):
    """The project root or a manifest is unsafe or invalid."""


def _read_regular_file(root: Path, name: str) -> str | None:
    path = root / name
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise ProjectDetectionError(f"cannot inspect manifest: {name}") from None
    if not stat.S_ISREG(info.st_mode):
        raise ProjectDetectionError(f"manifest is not a regular file: {name}")
    if info.st_size > _MAX_MANIFEST_BYTES:
        raise ProjectDetectionError(f"manifest exceeds size limit: {name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ProjectDetectionError(f"manifest changed type: {name}")
            if opened.st_size > _MAX_MANIFEST_BYTES:
                raise ProjectDetectionError(f"manifest exceeds size limit: {name}")
            data = handle.read(_MAX_MANIFEST_BYTES + 1)
    except ProjectDetectionError:
        raise
    except OSError:
        raise ProjectDetectionError(f"cannot read manifest: {name}") from None
    if len(data) > _MAX_MANIFEST_BYTES:
        raise ProjectDetectionError(f"manifest exceeds size limit: {name}")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ProjectDetectionError(f"manifest is not valid UTF-8: {name}") from None


def _package_names(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {key.lower() for key in value if isinstance(key, str)}


def _python_requirements(text: str | None) -> set[str]:
    names: set[str] = set()
    if not text:
        return names
    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith(("#", "-")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", item)
        if match:
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def inspect_project(project_root: str | os.PathLike) -> dict:
    """Detect known project types from bounded root manifests without execution."""
    raw = Path(project_root).expanduser()
    if not raw.is_absolute():
        raise ProjectDetectionError("project root must be an absolute path")
    try:
        if raw.is_symlink() or (hasattr(raw, "is_junction") and raw.is_junction()):
            raise ProjectDetectionError("project root must not be a symlink or junction")
        root = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ProjectDetectionError("project root does not exist or cannot be resolved") from None
    if not root.is_dir() or root == Path(root.anchor):
        raise ProjectDetectionError("project root must be a non-root directory")

    contents = {name: _read_regular_file(root, name) for name in _MANIFESTS}
    evidence = [name for name, value in contents.items() if value is not None]
    package: dict = {}
    if contents["package.json"] is not None:
        try:
            package = json.loads(contents["package.json"])
        except (json.JSONDecodeError, TypeError):
            raise ProjectDetectionError("package.json is invalid JSON") from None
        if not isinstance(package, dict):
            raise ProjectDetectionError("package.json must contain a JSON object")

    deps = _package_names(package.get("dependencies"))
    dev_deps = _package_names(package.get("devDependencies"))
    all_deps = deps | dev_deps
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        scripts = {}
    script_names = sorted(key for key, value in scripts.items()
                          if isinstance(key, str) and isinstance(value, str))

    framework = "UNKNOWN"
    language = "UNKNOWN"
    project_type = "UNKNOWN"
    package_manager = "UNKNOWN"
    toolchain_requirements: dict[str, str] = {}
    build_scripts = [name for name in ("build", "build:web") if name in script_names]
    test_scripts = [name for name in ("test", "test:e2e", "e2e") if name in script_names]

    if "pnpm-lock.yaml" in evidence:
        package_manager = "pnpm"
    elif "yarn.lock" in evidence:
        package_manager = "yarn"
    elif "bun.lock" in evidence or "bun.lockb" in evidence:
        package_manager = "bun"
    elif "package-lock.json" in evidence:
        package_manager = "npm"
    elif contents["package.json"] is not None:
        package_manager = "npm (lockfile missing)"

    engines = package.get("engines", {})
    if isinstance(engines, dict) and isinstance(engines.get("node"), str):
        toolchain_requirements["node"] = engines["node"]

    if "@angular/core" in all_deps or contents["angular.json"] is not None:
        framework, language, project_type = "Angular", "JavaScript/TypeScript", "web"
    elif "next" in all_deps or any(name.startswith("next.config.") for name in evidence):
        framework, language, project_type = "Next.js", "JavaScript/TypeScript", "web"
    elif "vite" in all_deps and "vue" in all_deps:
        framework, language, project_type = "Vue + Vite", "JavaScript/TypeScript", "web"
    elif "vite" in all_deps and ("react" in all_deps or "react-dom" in all_deps):
        framework, language, project_type = "React + Vite", "JavaScript/TypeScript", "web"
    elif "vue" in all_deps:
        framework, language, project_type = "Vue", "JavaScript/TypeScript", "web"
    elif "react" in all_deps or "react-dom" in all_deps:
        framework, language, project_type = "React", "JavaScript/TypeScript", "web"
    elif contents["package.json"] is not None:
        framework, language, project_type = "JavaScript application", "JavaScript/TypeScript", "web"
    elif contents["pubspec.yaml"] is not None:
        pubspec = contents["pubspec.yaml"]
        if re.search(r"(?m)^\s*flutter\s*:", pubspec) and re.search(r"(?m)^\s*sdk\s*:\s*flutter\s*$", pubspec):
            framework, language, project_type = "Flutter", "Dart", "mobile"
            match = re.search(r"(?m)^\s*sdk:\s*['\"]?([^'\"]+)['\"]?\s*$", pubspec)
            if match:
                toolchain_requirements["flutter"] = match.group(1).strip()
        else:
            framework, language, project_type = "Dart application", "Dart", "unknown"
    elif contents["pyproject.toml"] is not None or contents["requirements.txt"] is not None:
        pyproject = {}
        if contents["pyproject.toml"] is not None:
            try:
                pyproject = tomllib.loads(contents["pyproject.toml"])
            except tomllib.TOMLDecodeError:
                raise ProjectDetectionError("pyproject.toml is invalid TOML") from None
        project_table = pyproject.get("project", {})
        if not isinstance(project_table, dict):
            project_table = {}
        requirements = _python_requirements(contents["requirements.txt"])
        dependencies = project_table.get("dependencies", [])
        if isinstance(dependencies, list):
            requirements |= _python_requirements("\n".join(x for x in dependencies if isinstance(x, str)))
        optional = project_table.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    requirements |= _python_requirements("\n".join(x for x in values if isinstance(x, str)))
        if "fastapi" in requirements:
            framework = "FastAPI"
        elif "django" in requirements or (root / "manage.py").is_file():
            framework = "Django"
        elif "flask" in requirements:
            framework = "Flask"
        else:
            framework = "Python"
        language, project_type = "Python", "web" if framework != "Python" else "python"
        requires_python = project_table.get("requires-python")
        if isinstance(requires_python, str):
            toolchain_requirements["python"] = requires_python
        if "poetry.lock" in evidence:
            package_manager = "poetry"
        elif "uv.lock" in evidence:
            package_manager = "uv"
        elif "Pipfile" in evidence or "Pipfile.lock" in evidence:
            package_manager = "pipenv"
        else:
            package_manager = "pip"
    elif contents["index.html"] is not None:
        framework, language, project_type = "Static HTML/CSS/JS", "HTML/CSS/JavaScript", "web"

    return {
        "framework": framework,
        "language": language,
        "project_type": project_type,
        "confidence": "high" if framework != "UNKNOWN" else "unknown",
        "package_manager": package_manager,
        "toolchain_requirements": toolchain_requirements,
        "build_scripts": build_scripts,
        "test_scripts": test_scripts,
        "available_scripts": script_names,
        "evidence": sorted(evidence),
        "execution_performed": False,
        "toolchain_readiness": "NOT_CHECKED",
    }
