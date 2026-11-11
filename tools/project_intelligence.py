"""Bounded, read-only project discovery for DCP.

This module inspects repository structure and common manifests. It never imports
project code, executes project commands, follows symlinks, or reads credentials.
"""
from __future__ import annotations
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_MAX_FILES = 20_000
MAX_MANIFEST_BYTES = 256 * 1024
IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    "dist", "build", "target", "coverage", ".next", ".dart_tool", "Pods",
    "DerivedData", ".gradle",
}
MANIFESTS = {
    "pyproject.toml": "python", "requirements.txt": "python",
    "Pipfile": "python", "setup.py": "python", "package.json": "node",
    "pnpm-lock.yaml": "node", "yarn.lock": "node", "package-lock.json": "node",
    "pubspec.yaml": "flutter", "Cargo.toml": "rust", "go.mod": "go",
    "pom.xml": "java", "build.gradle": "java", "build.gradle.kts": "java",
    "Gemfile": "ruby", "composer.json": "php", "Dockerfile": "container",
}
EXTENSIONS = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".dart": "dart", ".java": "java", ".kt": "kotlin",
    ".kts": "kotlin", ".go": "go", ".rs": "rust", ".cs": "csharp",
    ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".swift": "swift", ".sh": "shell",
    ".ps1": "powershell", ".html": "html", ".css": "css", ".sql": "sql",
}
FRAMEWORK_MARKERS = {
    "fastapi": ("fastapi",), "django": ("django",), "flask": ("flask",),
    "pytest": ("pytest",), "playwright": ("playwright",),
    "react": ("react",), "nextjs": ("next",), "vite": ("vite",),
    "vue": ("vue",), "angular": ("@angular/core",), "flutter": ("flutter",),
    "firebase": ("firebase",), "express": ("express",), "nestjs": ("@nestjs/core",),
}


class DiscoveryError(ValueError):
    """Raised when a requested workspace cannot be inspected safely."""


def _safe_root(root: str | os.PathLike[str]) -> Path:
    path = Path(root).expanduser()
    if path.is_symlink():
        raise DiscoveryError("Workspace root must not be a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DiscoveryError("Workspace path does not exist or cannot be resolved") from exc
    if not resolved.is_dir() or resolved.is_symlink():
        raise DiscoveryError("Workspace must be a real directory")
    return resolved


def _read_small(path: Path) -> str:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_MANIFEST_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _classify_path(relative: str) -> str:
    parts = {part.lower() for part in Path(relative).parts}
    name = Path(relative).name.lower()
    if parts & {"tests", "test", "__tests__", "spec"} or name.startswith(("test_", "spec_")) or name.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts")):
        return "tests"
    if parts & {"docs", "documentation"} or name in {"readme.md", "contributing.md", "changelog.md"}:
        return "documentation"
    if parts & {".github", "workflows"}:
        return "automation"
    if parts & {"tools", "scripts", "bin"}:
        return "tooling"
    if parts & {"src", "lib", "app", "apps", "packages"}:
        return "application"
    if name in {"dockerfile", "makefile", "justfile"} or name.endswith((".yml", ".yaml", ".toml")):
        return "configuration"
    return "other"



def detect_frameworks(workspace: Path) -> dict[str, Any]:
    """Return explicit framework/toolchain evidence from root manifests only.

    This is static inspection: it never checks installed tools, resolves
    dependencies, imports project modules, or executes manifest scripts.
    """
    package_text = _read_small(workspace / "package.json")
    package: dict[str, Any] = {}
    warnings: list[str] = []
    if package_text:
        try:
            parsed = json.loads(package_text)
            if isinstance(parsed, dict):
                package = parsed
            else:
                warnings.append("package.json must contain an object")
        except json.JSONDecodeError:
            warnings.append("package.json is invalid JSON")

    dependencies: dict[str, Any] = {}
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        values = package.get(group, {})
        if isinstance(values, dict):
            dependencies.update(values)
    names = {name.lower() for name in dependencies if isinstance(name, str)}
    framework = "UNKNOWN"
    language = "UNKNOWN"
    project_type = "UNKNOWN"

    if "@angular/core" in names or (workspace / "angular.json").is_file():
        framework, language, project_type = "Angular", "JavaScript/TypeScript", "web"
    elif "next" in names or any((workspace / name).is_file() for name in (
        "next.config.js", "next.config.mjs", "next.config.ts"
    )):
        framework, language, project_type = "Next.js", "JavaScript/TypeScript", "web"
    elif "vite" in names and "vue" in names:
        framework, language, project_type = "Vue + Vite", "JavaScript/TypeScript", "web"
    elif "vite" in names and ({"react", "react-dom"} & names):
        framework, language, project_type = "React + Vite", "JavaScript/TypeScript", "web"
    elif "vue" in names:
        framework, language, project_type = "Vue", "JavaScript/TypeScript", "web"
    elif {"react", "react-dom"} & names:
        framework, language, project_type = "React", "JavaScript/TypeScript", "web"
    elif package_text and not warnings:
        framework, language, project_type = "JavaScript application", "JavaScript/TypeScript", "web"

    pubspec = _read_small(workspace / "pubspec.yaml")
    if framework == "UNKNOWN" and pubspec:
        if re.search(r"(?m)^\s*flutter\s*:", pubspec) and re.search(
            r"(?m)^\s*sdk\s*:\s*flutter\s*$", pubspec
        ):
            framework, language, project_type = "Flutter", "Dart", "mobile"
        else:
            framework, language, project_type = "Dart application", "Dart", "unknown"

    python_manifest = _read_small(workspace / "pyproject.toml")
    requirements = _read_small(workspace / "requirements.txt")
    python_text = "\n".join(value for value in (python_manifest, requirements) if value).lower()
    if framework == "UNKNOWN" and python_text:
        if re.search(r"(?i)\bfastapi\b", python_text):
            framework = "FastAPI"
        elif re.search(r"(?i)\bdjango\b", python_text) or (workspace / "manage.py").is_file():
            framework = "Django"
        elif re.search(r"(?i)\bflask\b", python_text):
            framework = "Flask"
        else:
            framework = "Python"
        language = "Python"
        project_type = "web" if framework in {"FastAPI", "Django", "Flask"} else "python"

    if framework == "UNKNOWN" and (workspace / "index.html").is_file():
        framework, language, project_type = "Static HTML/CSS/JS", "HTML/CSS/JavaScript", "web"

    package_manager = "UNKNOWN"
    lockfiles = (
        ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
        ("bun.lock", "bun"), ("bun.lockb", "bun"),
        ("package-lock.json", "npm"),
    )
    for filename, manager in lockfiles:
        if (workspace / filename).is_file():
            package_manager = manager
            break
    if package_manager == "UNKNOWN" and package_text:
        declared = package.get("packageManager")
        package_manager = declared if isinstance(declared, str) else "npm (lockfile missing)"
    if framework in {"Python", "FastAPI", "Django", "Flask"}:
        package_manager = (
            "uv" if (workspace / "uv.lock").is_file() else
            "poetry" if (workspace / "poetry.lock").is_file() else
            "pipenv" if (workspace / "Pipfile.lock").is_file() else "pip"
        )

    toolchain: dict[str, str] = {}
    engines = package.get("engines", {})
    if isinstance(engines, dict) and isinstance(engines.get("node"), str):
        toolchain["node"] = engines["node"]
    if pubspec:
        environment = re.search(r"(?ms)^environment:\s*\n((?:^[ \t]+.*\n?)*)", pubspec)
        if environment:
            match = re.search(r"(?m)^[ \t]+sdk:\s*['\"]([^'\"]+)['\"]", environment.group(1))
            if match:
                toolchain["dart"] = match.group(1).strip()
    if python_manifest:
        match = re.search(r"""(?m)^requires-python\s*=\s*['"]([^'"]+)['"]""", python_manifest)
        if match:
            toolchain["python"] = match.group(1).strip()

    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        scripts = {}
    available_scripts = sorted(
        key for key, value in scripts.items()
        if isinstance(key, str) and isinstance(value, str)
    )
    return {
        "framework": framework,
        "language": language,
        "project_type": project_type,
        "confidence": "high" if framework != "UNKNOWN" else "unknown",
        "package_manager": package_manager,
        "toolchain_requirements": toolchain,
        "available_scripts": available_scripts,
        "build_scripts": [name for name in ("build", "build:web") if name in available_scripts],
        "test_scripts": [name for name in ("test", "test:e2e", "e2e") if name in available_scripts],
        "evidence": sorted(name for name in (
            "package.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
            "package-lock.json", "angular.json", "next.config.js", "next.config.mjs",
            "next.config.ts", "pubspec.yaml", "pyproject.toml", "requirements.txt", "index.html"
        ) if (workspace / name).is_file()),
        "warnings": warnings,
        "toolchain_readiness": "NOT_CHECKED",
        "execution_performed": False,
    }


def discover_project(root: str | os.PathLike[str], task_description: str = "",
                     max_files: int = DEFAULT_MAX_FILES) -> dict[str, Any]:
    """Inspect a workspace without executing code or following symlinks."""
    workspace = _safe_root(root)
    if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= 100_000:
        raise DiscoveryError("max_files must be an integer between 1 and 100000")
    if not isinstance(task_description, str) or len(task_description) > 20_000:
        raise DiscoveryError("task_description must be text no longer than 20000 characters")

    languages: Counter[str] = Counter()
    areas: Counter[str] = Counter()
    manifests: list[dict[str, str]] = []
    samples: list[str] = []
    frameworks: set[str] = set()
    manifest_texts: list[str] = []
    file_count = 0
    truncated = False

    for current, dirs, filenames in os.walk(workspace, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(name for name in dirs
                         if name not in IGNORED_DIRS and not (current_path / name).is_symlink())
        for filename in sorted(filenames):
            candidate = current_path / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            file_count += 1
            relative = candidate.relative_to(workspace).as_posix()
            areas[_classify_path(relative)] += 1
            language = EXTENSIONS.get(candidate.suffix.lower())
            if language:
                languages[language] += 1
            if len(samples) < 80:
                samples.append(relative)
            kind = MANIFESTS.get(filename)
            if filename.endswith((".sln", ".csproj")):
                kind = "dotnet"
            if kind:
                manifests.append({"path": relative, "kind": kind})
                text = _read_small(candidate)
                if text:
                    manifest_texts.append(text.lower())
            if file_count >= max_files:
                truncated = True
                break
        if truncated:
            break

    all_manifest_text = "\n".join(manifest_texts)
    framework_detection = detect_frameworks(workspace)
    for framework, markers in FRAMEWORK_MARKERS.items():
        if any(marker in all_manifest_text for marker in markers):
            frameworks.add(framework)
    kinds = {item["kind"] for item in manifests}
    if "flutter" in kinds:
        frameworks.add("flutter")

    tools: set[str] = set()
    builds: list[list[str]] = []
    tests: list[list[str]] = []
    if "python" in kinds or "python" in languages:
        tools.update(("python", "pip"))
        if "pytest" in all_manifest_text:
            tools.add("pytest")
            tests.append(["python", "-m", "pytest", "-q"])
        else:
            tests.append(["python", "-m", "unittest", "discover", "-s", "tests", "-v"])
    if "node" in kinds or "javascript" in languages or "typescript" in languages:
        tools.update(("node", "npm"))
        builds.append(["npm", "run", "build", "--if-present"])
        tests.append(["npm", "test", "--if-present"])
    if "flutter" in kinds or "dart" in languages:
        tools.update(("flutter", "dart"))
        builds.append(["flutter", "analyze"])
        tests.append(["flutter", "test"])
    if "rust" in kinds or "rust" in languages:
        tools.update(("rustc", "cargo"))
        builds.append(["cargo", "build", "--locked"])
        tests.append(["cargo", "test", "--locked"])
    if "go" in kinds or "go" in languages:
        tools.add("go")
        builds.append(["go", "build", "./..."])
        tests.append(["go", "test", "./..."])
    if "dotnet" in kinds or "csharp" in languages:
        tools.add("dotnet")
        builds.append(["dotnet", "build", "--no-restore"])
        tests.append(["dotnet", "test", "--no-build"])
    if "java" in kinds or "java" in languages:
        tools.update(("java", "javac"))
        if (workspace / "mvnw").is_file():
            builds.append(["./mvnw", "package"])
            tests.append(["./mvnw", "test"])

    task_lower = task_description.lower()
    topics = [tag for tag in ("runner", "dashboard", "api", "authentication", "security",
                              "mobile", "deployment", "testing", "documentation") if tag in task_lower]
    gaps = []
    if not areas.get("tests"):
        gaps.append({"id": "tests-not-detected", "severity": "warning",
                     "detail": "No recognizable test files or test directories were detected."})
    if not manifests:
        gaps.append({"id": "manifest-not-detected", "severity": "warning",
                     "detail": "No supported project manifest was detected; toolchain selection is incomplete."})
    if truncated:
        gaps.append({"id": "scan-truncated", "severity": "warning",
                     "detail": f"File scan reached max_files={max_files}; inventory is partial."})
    if not builds and not tests:
        gaps.append({"id": "commands-not-inferred", "severity": "warning",
                     "detail": "No safe build/test command templates could be inferred."})

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unknown" if truncated or not manifests else "pass",
        "workspace": str(workspace),
        "inventory": {"file_count": file_count, "truncated": truncated,
                      "languages": dict(sorted(languages.items())),
                      "architecture_areas": dict(sorted(areas.items())),
                      "manifests": manifests, "frameworks": sorted(frameworks),
                      "framework_detection": framework_detection,
                      "sample_paths": samples},
        "task": {"description": task_description, "detected_topics": topics},
        "runner_profile": {"profile_version": 1, "stack": sorted(kinds | set(languages)),
                           "required_tools": sorted(tools), "build_commands": builds,
                           "test_commands": tests, "execution_mode": "dry-run",
                           "network": "disabled-by-default", "workspace_isolation": "required",
                           "secrets": "never-injected-by-discovery",
                           "approval_required_for_execution": True},
        "gaps": gaps,
        "notes": ["Discovery is structural analysis, not proof a framework or command works.",
                  "No project code or build/test command was executed.",
                  "Generated runner commands are proposals and require owner review.",
                  "PASS means bounded inventory completed, not that the project builds or tests pass."],
    }
