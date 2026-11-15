"""Race-aware regular-file checks shared by Local Runner copy paths."""
from __future__ import annotations

import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


def _same_file_identity(left, right) -> bool:
    return left.st_dev == right.st_dev and (
        not left.st_ino or not right.st_ino or left.st_ino == right.st_ino
    )


@contextmanager
def open_verified_regular_file(path, error_type, label: str):
    """Open a single-link regular file and verify its identity/link count after reading."""
    path = Path(path)
    descriptor = None
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise error_type(f"{label} must be a single-link regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or not _same_file_identity(before, opened)):
            raise error_type(f"{label} changed or became hardlinked while opening")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        try:
            yield stream
            after = os.fstat(stream.fileno())
            path_after = os.lstat(path)
            if (not stat.S_ISREG(after.st_mode) or after.st_nlink != 1
                    or not stat.S_ISREG(path_after.st_mode)
                    or not _same_file_identity(opened, after)
                    or not _same_file_identity(opened, path_after)
                    or path_after.st_nlink != 1
                    or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise error_type(f"{label} changed or became hardlinked while reading")
        finally:
            stream.close()
    except error_type:
        raise
    except OSError:
        raise error_type(f"{label} cannot be opened or verified safely") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def copy_verified_regular_file(source, destination, error_type, label: str) -> int:
    """Copy to a private temporary file and publish only after source verification."""
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise error_type("copy destination already exists or is unsafe")
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".dcp-copy-", dir=str(destination.parent)
        )
        temporary = Path(temporary_name)
        copied = 0
        with os.fdopen(descriptor, "wb") as output:
            with open_verified_regular_file(source, error_type, label) as input_file:
                while True:
                    chunk = input_file.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    copied += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        if destination.exists() or destination.is_symlink():
            raise error_type("copy destination appeared during operation")
        os.replace(temporary, destination)
        temporary = None
        return copied
    except error_type:
        raise
    except OSError:
        raise error_type(f"{label} could not be copied safely") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
