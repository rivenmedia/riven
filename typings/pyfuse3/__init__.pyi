"""Stub for optional pyfuse3; install `riven[fuse]` for the real extension module."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

class InodeT(int): ...
class FileNameT(bytes): ...
class FileHandleT(int): ...
class ModeT(int): ...
class ReaddirToken: ...

ROOT_INODE: InodeT = ...

class RequestContext: ...

class EntryAttributes:
    st_ino: InodeT
    generation: int
    entry_timeout: float
    attr_timeout: float
    st_uid: int
    st_gid: int
    st_blksize: int
    st_blocks: int
    st_mode: ModeT
    st_nlink: int
    st_size: int
    st_atime_ns: int
    st_mtime_ns: int
    st_ctime_ns: int

    def __init__(self) -> None: ...

class FileInfo:
    fh: FileHandleT

    def __init__(self, *, fh: FileHandleT) -> None: ...

class FUSEError(OSError): ...

class Operations: ...

default_options: frozenset[str]

def init(operations: Operations, mountpoint: str, options: set[str]) -> None: ...
async def main() -> None: ...
def close(*, unmount: bool = False) -> None: ...
def terminate() -> None: ...

trio_token: Any

def invalidate_inode(inode: InodeT, *, attr_only: bool) -> None: ...

def readdir_reply(
    token: ReaddirToken,
    name: FileNameT,
    attrs: EntryAttributes,
    offset: int,
) -> bool: ...

def invalidate_entry_async(
    inode_p: InodeT,
    name: FileNameT,
    *,
    deleted: InodeT = ...,
    ignore_enoent: bool = ...,
) -> Awaitable[None]: ...
