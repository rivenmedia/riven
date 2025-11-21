from functools import cached_property
import pyfuse3

from dataclasses import dataclass
from typing import Literal


@dataclass
class VFSNode:
    """
    Represents a node (file or directory) in the VFS tree.

    This is the core data structure for the in-memory VFS tree, providing
    O(1) lookups and eliminating the need for path resolution.

    Attributes:
        name: Name of this node (e.g., "Frozen.mkv" or "movies")
        inode: FUSE inode number assigned to this node
        parent: Reference to parent VFSDirectory (None for root)
    """

    name: str
    inode: pyfuse3.InodeT
    parent: "VFSDirectory | None"

    @cached_property
    def path(self) -> str:
        """Get the full VFS path for this node by walking up to root."""
        if self.parent is None:
            return "/"

        parts = list[str]([])
        current = self

        while current.parent is not None:
            parts.append(current.name)
            current = current.parent

        if not parts:
            return "/"

        return "/" + "/".join(reversed(parts))


@dataclass
class VFSDirectory(VFSNode):
    """
    Represents a directory node in the VFS tree.

    Inherits from VFSNode and adds directory-specific attributes.

    Attributes:
        parent: Reference to parent VFSDirectory
    """

    @property
    def children(self) -> dict[str, VFSNode]:
        """Get children dict."""

        if not hasattr(self, "_children"):
            self._children: dict[str, VFSNode] = {}

        return self._children

    def add_child(self, child: VFSNode) -> None:
        """Add a child node to this directory."""

        child.parent = self
        self.children[child.name] = child

    def remove_child(self, name: str) -> VFSNode | None:
        """Remove and return a child node by name."""
        child = self.children.pop(name, None)

        if child:
            child.parent = None

        return child

    def get_child(self, name: str) -> VFSNode | None:
        """Get a child node by name."""
        return self.children.get(name)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"is_dir=true, "
            f"inode={self.inode}, "
            f"children={len(self.children)})"
        )


@dataclass
class VFSRoot(VFSDirectory):
    """
    Represents the root node of the VFS tree.

    Inherits from VFSNode and initializes as a directory with root inode.

    Attributes:
        parent: None (root has no parent)
    """

    def __init__(self) -> None:
        super().__init__(
            name="",
            inode=pyfuse3.ROOT_INODE,
            parent=None,
        )

    @cached_property
    def path(self) -> Literal["/"]:
        """
        Skips expensive path calculation for root node.

        Root path is always '/'.
        """

        return "/"


@dataclass
class VFSFile(VFSNode):
    """
    Represents a file node in the VFS tree.

    Inherits from VFSNode and adds file-specific attributes.

    Attributes:
        name: Name of this node (e.g., "Frozen.mkv" or "movies")
        original_filename: Original filename from debrid provider (for files only)
                           This is used to look up the MediaEntry in the database.
        parent: Reference to parent VFSDirectory

        # Cached file metadata
        file_size: File size in bytes
        created_at: Creation timestamp as ISO string
        updated_at: Modification timestamp as ISO string
        entry_type: Entry type ("media" or "subtitle")
    """

    original_filename: str

    # Cached metadata for files (eliminates database queries)
    file_size: int
    created_at: str
    updated_at: str
    entry_type: Literal["media", "subtitle"]

    def __init__(
        self,
        *,
        name: str,
        inode: pyfuse3.InodeT,
        parent: VFSDirectory,
        original_filename: str,
        file_size: int,
        created_at: str,
        updated_at: str,
        entry_type: Literal["media", "subtitle"],
    ) -> None:
        super().__init__(
            name=name,
            inode=inode,
            parent=parent,
        )

        self.original_filename = original_filename
        self.file_size = file_size
        self.created_at = created_at
        self.updated_at = updated_at
        self.entry_type = entry_type

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"inode={self.inode}, "
            f"original_filename={self.original_filename!r}, "
            f"file_size={self.file_size}, "
            f"created_at={self.created_at!r}, "
            f"updated_at={self.updated_at!r}, "
            f"entry_type={self.entry_type!r}"
            ")"
        )
