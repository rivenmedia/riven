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
        is_directory: True if this is a directory, False if it's a file
        original_filename: Original filename from debrid provider (for files only)
                          This is used to look up the MediaEntry in the database.
                          For directories, this is None.
        inode: FUSE inode number assigned to this node
        children: Dict of child name -> VFSNode (only for directories)
        parent: Reference to parent VFSNode (None for root)

        # Cached file metadata (for files only, eliminates DB queries in getattr)
        file_size: File size in bytes (None for directories)
        created_at: Creation timestamp as ISO string (None for directories)
        updated_at: Modification timestamp as ISO string (None for directories)
        entry_type: Entry type ("media" or "subtitle", None for directories)
        bitrate: Bitrate in kbps (None for directories, or when media analysis is absent)
        duration: Duration in seconds (None for directories, or when media analysis is absent)
    """

    name: str
    inode: pyfuse3.InodeT
    parent: "VFSNode"

    @property
    def path(self) -> str:
        """Get the full VFS path for this node by walking up to root."""
        if self.parent is None:
            return "/"

        parts = []
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
    """

    parent: "VFSDirectory"

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
            del child.parent

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
    """

    def __init__(self) -> None:
        super().__init__(
            name="",
            inode=pyfuse3.ROOT_INODE,
            parent=self,
        )

    @property
    def path(self) -> Literal["/"]:
        """
        Skips expensive path calculation for root node.

        Root path is always '/'.
        """

        return "/"

    @property
    def parent(self) -> None:
        """Root has no parent"""
        return None

    @parent.setter
    def parent(self, _) -> None:
        """Root has no parent, ignore setting"""
        pass


@dataclass
class VFSFile(VFSNode):
    """
    Represents a file node in the VFS tree.

    Inherits from VFSNode and adds file-specific attributes.
    """

    name: str
    original_filename: str

    # Cached metadata for files (eliminates database queries)
    file_size: int
    created_at: str
    updated_at: str
    entry_type: Literal["media", "subtitle"]
    bitrate: int | None
    duration: int | None
    parent: VFSDirectory

    def __init__(
        self,
        *,
        name: str,
        inode: pyfuse3.InodeT,
        parent: VFSDirectory,
        original_filename: str,
    ) -> None:
        super().__init__(
            name=name,
            inode=inode,
            parent=parent,
        )

        self.original_filename = original_filename

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"inode={self.inode}, "
            f"original_filename={self.original_filename!r}, "
            f"file_size={self.file_size}, "
            f"created_at={self.created_at!r}, "
            f"updated_at={self.updated_at!r}, "
            f"entry_type={self.entry_type!r}, "
            f"bitrate={self.bitrate}, "
            f"duration={self.duration}, "
            ")"
        )
