"""
Type stubs for pyfuse3.

This stub file allows pyright/Pylance to type-check code that uses pyfuse3
on platforms where pyfuse3 cannot be installed (macOS, Windows).

Based on pyfuse3 v3.4.0. Update if pyfuse3 adds new APIs used by the codebase.
"""

from typing import Any, NewType, Set

# Type aliases
InodeT = NewType("InodeT", int)
FileHandleT = NewType("FileHandleT", int)
FileNameT = NewType("FileNameT", bytes)
ModeT = NewType("ModeT", int)

# Constants
ROOT_INODE: InodeT
default_options: Set[str]
trio_token: Any

class FUSEError(Exception):
    errno: int
    def __init__(self, errno: int = ...) -> None: ...

class EntryAttributes:
    st_ino: int
    st_mode: int
    st_nlink: int
    st_uid: int
    st_gid: int
    st_size: int
    st_atime_ns: int
    st_mtime_ns: int
    st_ctime_ns: int
    st_blksize: int
    st_blocks: int
    generation: int
    entry_timeout: float
    attr_timeout: float

class FileInfo:
    fh: FileHandleT
    def __init__(self, *, fh: FileHandleT = ...) -> None: ...

class RequestContext:
    uid: int
    gid: int
    pid: int

class ReaddirToken: ...

class Operations:
    async def lookup(
        self, parent_inode: InodeT, name: FileNameT, ctx: RequestContext
    ) -> EntryAttributes: ...
    async def getattr(
        self, inode: InodeT, ctx: RequestContext
    ) -> EntryAttributes: ...
    async def opendir(self, inode: InodeT, ctx: RequestContext) -> FileHandleT: ...
    async def readdir(
        self, fh: FileHandleT, start_id: int, token: ReaddirToken
    ) -> None: ...
    async def releasedir(self, fh: FileHandleT) -> None: ...
    async def open(
        self, inode: InodeT, flags: int, ctx: RequestContext
    ) -> FileInfo: ...
    async def read(self, fh: FileHandleT, off: int, size: int) -> bytes: ...
    async def release(self, fh: FileHandleT) -> None: ...
    async def unlink(
        self, parent_inode: InodeT, name: FileNameT, ctx: RequestContext
    ) -> None: ...
    async def rmdir(
        self, parent_inode: InodeT, name: FileNameT, ctx: RequestContext
    ) -> None: ...
    async def rename(
        self,
        parent_inode_old: InodeT,
        name_old: FileNameT,
        parent_inode_new: InodeT,
        name_new: FileNameT,
        flags: int,
        ctx: RequestContext,
    ) -> None: ...

def init(operations: Operations, mountpoint: str, options: Set[str]) -> None: ...
async def main() -> None: ...
def close(unmount: bool = ...) -> None: ...
def terminate() -> None: ...
def invalidate_inode(inode: InodeT, attr_only: bool = ...) -> None: ...
def invalidate_entry_async(
    parent_inode: InodeT,
    name: FileNameT,
    deleted: InodeT = ...,
    ignore_enoent: bool = ...,
) -> None: ...
def readdir_reply(
    token: ReaddirToken,
    name: FileNameT,
    attr: EntryAttributes,
    next_id: int,
) -> bool: ...
