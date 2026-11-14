"""Linux bubblewrap command builder for fail-closed Terminal jobs.

The builder creates a constrained launch command; it does not mark a host VERIFIED.
Production execution remains blocked until host-level adversarial acceptance passes.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class LinuxSandboxError(RuntimeError):
    """A safe Linux sandbox launch command could not be constructed."""


# Linux syscall numbers for supported 64-bit architectures. Unknown architectures
# are rejected rather than silently receiving a weaker network policy.
_NETWORK_SYSCALLS = {
    "x86_64": (41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 288, 299, 307),
    "amd64": (41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 288),
    "aarch64": (198, 203, 202, 206, 207, 211, 212, 210, 200, 201, 204, 205, 199, 242, 243, 269),
    "arm64": (198, 203, 202, 206, 207, 211, 212, 210, 200, 201, 204, 205, 199, 242),
}


@dataclass
class LinuxSandboxCommand:
    argv: tuple[str, ...]
    seccomp_file: BinaryIO

    @property
    def seccomp_fd(self) -> int:
        return self.seccomp_file.fileno()

    def close(self) -> None:
        self.seccomp_file.close()


def _seccomp_program(machine: str | None = None) -> bytes:
    """Build classic BPF that returns EPERM for all socket/network syscalls."""
    arch = (machine or platform.machine()).lower()
    numbers = _NETWORK_SYSCALLS.get(arch)
    if not numbers:
        raise LinuxSandboxError("unsupported CPU architecture for the network-deny seccomp policy")
    # struct sock_filter: u16 code, u8 jt, u8 jf, u32 k (native endian).
    import struct
    audit_arch = {"x86_64": 0xC000003E, "amd64": 0xC000003E,
                  "aarch64": 0xC00000B7, "arm64": 0xC00000B7}[arch]
    instructions = [
        struct.pack("=HBBI", 0x20, 0, 0, 4),  # load seccomp_data.arch
        struct.pack("=HBBI", 0x15, 1, 0, audit_arch),  # reject foreign syscall ABI
        struct.pack("=HBBI", 0x06, 0, 0, 0x80000000),  # RET_KILL_PROCESS
    ]
    if arch in {"x86_64", "amd64"}:
        instructions.extend([
            struct.pack("=HBBI", 0x20, 0, 0, 0),  # load seccomp_data.nr
            struct.pack("=HBBI", 0x45, 0, 1, 0x40000000),  # reject x32 ABI
            struct.pack("=HBBI", 0x06, 0, 0, 0x80000000),
        ])
    else:
        instructions.append(struct.pack("=HBBI", 0x20, 0, 0, 0))
    for number in numbers:
        instructions.append(struct.pack("=HBBI", 0x15, 0, 1, number))  # JEQ -> deny
        instructions.append(struct.pack("=HBBI", 0x06, 0, 0, 0x00050001))  # RET_ERRNO(EPERM)
    instructions.extend([
        struct.pack("=HBBI", 0x15, 0, 1, 425),  # deny io_uring_setup (network bypass)
        struct.pack("=HBBI", 0x06, 0, 0, 0x00050001),
        struct.pack("=HBBI", 0x06, 0, 0, 0x7FFF0000),  # RET_ALLOW
    ])
    return b"".join(instructions)


def _trusted_directory(path: str | os.PathLike, label: str) -> Path:
    raw = Path(path)
    if not raw.is_absolute():
        raise LinuxSandboxError(f"{label} must be an absolute path")
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise LinuxSandboxError(f"{label} path contains a symlink")
    try:
        resolved = raw.resolve(strict=True)
        info = resolved.stat()
    except OSError:
        raise LinuxSandboxError(f"{label} is unavailable") from None
    if not stat.S_ISDIR(info.st_mode):
        raise LinuxSandboxError(f"{label} must be a real directory")
    return resolved


class LinuxBubblewrapLauncher:
    """Construct a private-network, read-only-workspace bubblewrap command."""

    def __init__(self, *, executable_lookup=shutil.which):
        if not sys_platform_linux():
            raise LinuxSandboxError("bubblewrap launcher is supported only on Linux")
        candidate = executable_lookup("bwrap")
        if not candidate:
            raise LinuxSandboxError("bubblewrap executable is unavailable")
        try:
            resolved = Path(candidate).resolve(strict=True)
        except OSError:
            raise LinuxSandboxError("bubblewrap executable is unavailable") from None
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise LinuxSandboxError("bubblewrap executable is not an executable regular file")
        self.bwrap = str(resolved)

    def build(
        self,
        *,
        executable: str,
        argv: list[str] | tuple[str, ...],
        workspace: str | os.PathLike,
        scratch: str | os.PathLike,
    ) -> LinuxSandboxCommand:
        work = _trusted_directory(workspace, "assigned workspace")
        temp = _trusted_directory(scratch, "per-job scratch")
        if temp == work or work in temp.parents or temp in work.parents:
            raise LinuxSandboxError("scratch and workspace must be separate directory trees")
        if not isinstance(executable, str) or not os.path.isabs(executable):
            raise LinuxSandboxError("sandbox executable must be an absolute trusted path")
        binary = Path(executable).resolve(strict=True)
        if not binary.is_file() or not any(binary == root or root in binary.parents for root in (Path("/usr"), Path("/bin"))):
            raise LinuxSandboxError("sandbox executable must reside in the approved system runtime")
        if not isinstance(argv, (list, tuple)) or len(argv) > 32:
            raise LinuxSandboxError("sandbox argv is invalid")
        if any(not isinstance(item, str) or "\x00" in item for item in argv):
            raise LinuxSandboxError("sandbox argv contains an invalid argument")

        seccomp_file = tempfile.TemporaryFile(mode="w+b")
        try:
            seccomp_file.write(_seccomp_program())
            seccomp_file.flush()
            os.fsync(seccomp_file.fileno())
            os.lseek(seccomp_file.fileno(), 0, os.SEEK_SET)
            fd = seccomp_file.fileno()
            command = [
                self.bwrap,
                "--die-with-parent",
                "--new-session",
                "--unshare-user", "--uid", "0", "--gid", "0", "--cap-drop", "ALL", "--disable-userns", "--assert-userns-disabled",
                "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
                "--ro-bind", "/usr", "/usr",
            ]
            for runtime_dir in ("/lib", "/lib64"):
                if os.path.exists(runtime_dir):
                    command.extend(["--ro-bind", runtime_dir, runtime_dir])
            command.extend([
                "--dir", "/etc",
                "--dir", "/workspace",
                "--dir", "/tmp",
                "--proc", "/proc",
                "--dev", "/dev",
                "--ro-bind", str(work), "/workspace",
                "--bind", str(temp), "/tmp",
                "--chdir", "/workspace",
                "--clearenv",
                "--setenv", "PATH", "/usr/bin:/bin",
                "--setenv", "HOME", "/tmp",
                "--setenv", "LANG", "C.UTF-8",
                "--seccomp", str(fd),
                "--",
                str(binary),
                *argv,
            ])
            return LinuxSandboxCommand(tuple(command), seccomp_file)
        except Exception:
            seccomp_file.close()
            raise


def sys_platform_linux() -> bool:
    import sys
    return sys.platform.startswith("linux")
