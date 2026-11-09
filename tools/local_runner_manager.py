"""Local, isolated GitHub Actions ephemeral-runner supervisor for Windows.

Only runner directories and processes created by this manager are controlled.
Existing self-hosted runners, services, registrations, and workspaces are untouched.
"""
from __future__ import annotations
import argparse, json, os, platform, shutil, subprocess, sys, time, urllib.error, urllib.request, uuid, zipfile
from pathlib import Path
from typing import Any

GITHUB = "https://github.com"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
DEFAULT_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "DCP" / "local-runners"

class RunnerError(RuntimeError):
    """Safe-to-display local runner error."""

def run_command(args: list[str], *, timeout: int = 30) -> str:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"Command failed: {Path(args[0]).name} ({type(exc).__name__})") from exc
    if result.returncode:
        raise RunnerError(f"{Path(args[0]).name} returned exit code {result.returncode}")
    return result.stdout.strip()

def gh_json(args: list[str], *, timeout: int = 30) -> Any:
    try:
        return json.loads(run_command(["gh", "api", *args], timeout=timeout))
    except json.JSONDecodeError as exc:
        raise RunnerError("GitHub CLI returned invalid JSON") from exc

def validate_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if len(parts) != 2 or any(not part or part in (".", "..") for part in parts):
        raise RunnerError("Repository must be an exact owner/repository value")
    if any(any(char not in allowed for char in part) for part in parts):
        raise RunnerError("Repository contains unsupported characters")
    return parts[0], parts[1]

def check_prerequisites(repository: str) -> dict[str, Any]:
    owner, name = validate_repository(repository)
    if platform.system() != "Windows":
        raise RunnerError("The first local runner implementation supports Windows only")
    gh = shutil.which("gh")
    if not gh:
        raise RunnerError("GitHub CLI (gh) is required; install it and sign in first")
    run_command([gh, "auth", "status"])
    repo = gh_json([f"repos/{owner}/{name}"])
    if repo.get("full_name", "").lower() != repository.lower():
        raise RunnerError("GitHub returned a different repository identity")
    if repo.get("private") is not True:
        raise RunnerError("Self-hosted execution is blocked for public repositories")
    if (repo.get("permissions") or {}).get("admin") is not True:
        raise RunnerError("The authenticated GitHub account needs repository admin permission")
    return {"repository": repo["full_name"], "private": True, "authenticated": True}

def get_registration_token(repository: str) -> str:
    token = gh_json([f"repos/{repository}/actions/runners/registration-token", "--method", "POST"]).get("token")
    if not isinstance(token, str) or not token:
        raise RunnerError("GitHub did not issue a runner registration token")
    return token

def latest_runner_asset() -> str:
    release = gh_json(["repos/actions/runner/releases/latest"])
    for asset in release.get("assets", []):
        name, url = asset.get("name", ""), asset.get("browser_download_url", "")
        if "win-x64" in name and name.endswith(".zip") and url.startswith("https://github.com/actions/runner/releases/download/"):
            return url
    raise RunnerError("No official Windows x64 GitHub Actions runner release asset was found")

def download_runner(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "DCP-Local-Runner-Manager/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES: raise RunnerError("Runner archive exceeded the 512 MiB safety limit")
                output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise RunnerError(f"Runner download failed: {type(exc).__name__}") from exc

def safe_extract(archive: Path, target: Path) -> None:
    root = target.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            resolved = (target / item.filename).resolve()
            if resolved != root and root not in resolved.parents:
                raise RunnerError("Runner archive contains an unsafe path")
        bundle.extractall(target)

def prepare_instance(repository: str, root: Path) -> tuple[Path, str]:
    instance_id = uuid.uuid4().hex[:12]
    owner, name = validate_repository(repository)
    instance = root / f"{owner}-{name}" / instance_id
    instance.mkdir(parents=True, exist_ok=False)
    archive = instance / "runner.zip"
    try:
        download_runner(latest_runner_asset(), archive)
        safe_extract(archive, instance)
    except Exception:
        shutil.rmtree(instance, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    return instance, f"DCP-{platform.node()[:16]}-{instance_id}"

def configure_instance(instance: Path, repository: str, runner_name: str) -> None:
    config = instance / "config.cmd"
    if not config.is_file(): raise RunnerError("Downloaded runner is missing config.cmd")
    token = get_registration_token(repository)
    args = ["cmd.exe", "/d", "/c", "call", str(config), "--unattended", "--ephemeral", "--disableupdate",
            "--url", f"{GITHUB}/{repository}", "--token", token, "--name", runner_name,
            "--labels", "dcp-managed,windows,x64", "--work", "_work"]
    try:
        run_command(args, timeout=120)
    finally:
        token = ""

def runner_status(repository: str, runner_name: str) -> tuple[str, bool] | None:
    payload = gh_json([f"repos/{repository}/actions/runners", "--paginate"])
    for runner in payload.get("runners", []):
        if runner.get("name") == runner_name:
            return str(runner.get("status", "offline")), bool(runner.get("busy", False))
    return None

def stop_owned_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # PID-scoped tree termination: never target a process by a shared name.
        try:
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)


def cleanup_instance(instance: Path, root: Path) -> None:
    resolved_root = root.resolve()
    resolved_instance = instance.resolve()
    if resolved_root not in resolved_instance.parents:
        raise RunnerError("Refusing to clean a runner directory outside the managed root")
    if len(instance.name) != 12 or any(ch not in "0123456789abcdef" for ch in instance.name):
        raise RunnerError("Refusing to clean a directory without a managed instance ID")
    shutil.rmtree(resolved_instance)


def supervise_instance(instance: Path, repository: str, runner_name: str, log_dir: Path) -> int:
    runner_script = instance / "run.cmd"
    if not runner_script.is_file(): raise RunnerError("Configured runner is missing run.cmd")
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{runner_name}.log").open("a", encoding="utf-8") as log:
        log.write(f"\nDCP supervisor starting {runner_name} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
        process = subprocess.Popen(["cmd.exe", "/d", "/c", "call", str(runner_script)], cwd=instance,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        offline_samples = 0
        try:
            while process.poll() is None:
                time.sleep(30)
                if process.poll() is not None: break
                try:
                    status = runner_status(repository, runner_name)
                except RunnerError:
                    offline_samples = 0
                    continue
                if status is None or (status[0] == "offline" and not status[1]): offline_samples += 1
                else: offline_samples = 0
                if offline_samples >= 3:
                    stop_owned_process_tree(process)
                    return int(process.returncode or 1)
        except KeyboardInterrupt:
            stop_owned_process_tree(process)
            raise
        return int(process.wait())

def run_supervisor(repository: str, root: Path, max_restarts: int, backoff: int) -> int:
    check_prerequisites(repository)
    if isinstance(max_restarts, bool) or not 0 <= max_restarts <= 20: raise RunnerError("max-restarts must be between 0 and 20")
    if isinstance(backoff, bool) or not 1 <= backoff <= 300: raise RunnerError("backoff-seconds must be between 1 and 300")
    root.mkdir(parents=True, exist_ok=True)
    log_dir = root / "logs"
    attempts = 0
    while True:
        instance = None
        try:
            instance, runner_name = prepare_instance(repository, root)
            configure_instance(instance, repository, runner_name)
            exit_code = supervise_instance(instance, repository, runner_name, log_dir)
            attempts = 0 if exit_code == 0 else attempts + 1
        except KeyboardInterrupt:
            raise
        except RunnerError:
            attempts += 1
        finally:
            if instance is not None and instance.exists():
                cleanup_instance(instance, root)
        if attempts > max_restarts: raise RunnerError("Runner restart limit reached; inspect the local instance logs")
        time.sleep(min(backoff * (2 ** max(0, attempts - 1)), 300))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DCP isolated local GitHub Actions runner manager")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Check local host and GitHub authentication")
    doctor.add_argument("--repository", required=True)
    start = sub.add_parser("start", help="Create and supervise a new ephemeral runner")
    start.add_argument("--repository", required=True)
    start.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    start.add_argument("--max-restarts", type=int, default=5)
    start.add_argument("--backoff-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(check_prerequisites(args.repository), indent=2))
            return 0
        return run_supervisor(args.repository, args.root, args.max_restarts, args.backoff_seconds)
    except KeyboardInterrupt:
        print("DCP local runner supervisor stopped by operator.")
        return 130
    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
