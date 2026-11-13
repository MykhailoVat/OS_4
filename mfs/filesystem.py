# filesystem.py

from dataclasses import dataclass, field
from mfs.opt.errors import FileSystemError

BLOCK_SIZE = 8
MAX_NAME_BYTES = 15


def nonnegative(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise FileSystemError(f"{label}: a nonnegative integer is required")


@dataclass
class Inode:
    number: int
    type: str = "regular"
    links: int = 0
    size: int = 0
    # The key is a logical block number; a missing key represents a zero block.
    blocks: dict[int, bytes] = field(default_factory=dict)
    # Directory contents map names to inode numbers; unused for regular files.
    entries: dict[str, int] = field(default_factory=dict)


class MemoryFileSystem:
    """
    In-memory filesystem
    The root directory has inode 0.
    """

    def __init__(self) -> None:
        self.inodes: dict[int, Inode] = {}

        root_inode = Inode(
            number=0,
            type="directory",
            links=1
        )
        self.inodes[0] = root_inode

        self.directory: dict[str, int] = root_inode.entries
        self._next_inode = 1

    @staticmethod
    def validate_name(name: str) -> None:
        if not isinstance(name, str) or not name or name in {".", ".."}:
            raise FileSystemError("Invalid file name")
        if any(char in name for char in "/\x00"):
            raise FileSystemError("A name cannot contain '/' or NUL")
        try:
            length = len(name.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise FileSystemError("A name must be encodable as UTF-8") from error
        if length > MAX_NAME_BYTES:
            raise FileSystemError(f"Name exceeds {MAX_NAME_BYTES} UTF-8 bytes")

    def lookup(self, name: str) -> Inode:
        self.validate_name(name)
        if name not in self.directory:
            raise FileSystemError(f"File {name!r} does not exist")
        return self.inodes[self.directory[name]]

    def _check_new_name(self, name: str) -> None:
        self.validate_name(name)
        if name in self.directory:
            raise FileSystemError(f"Name {name!r} already exists")

    def create(self, name: str) -> int:
        self._check_new_name(name)
        number = self._next_inode
        self._next_inode += 1
        self.inodes[number] = Inode(number, links=1)
        self.directory[name] = number
        return number

    def ls(self) -> list[tuple[str, int]]:
        return sorted(self.directory.items())

    def stat(self, name: str) -> dict:
        inode = self.inodes[0] if name == "/" else self.lookup(name)
        return {
            "inode": inode.number,
            "type": inode.type,
            "links": inode.links,
            "size": inode.size,
            "block_size": BLOCK_SIZE,
            "allocated_blocks": len(inode.blocks),
            "block_map": sorted(inode.blocks),
            **({"entries": len(inode.entries)} if inode.type == "directory" else {}),
        }

    def link(self, source: str, target: str) -> None:
        inode = self.lookup(source)
        self._check_new_name(target)
        self.directory[target] = inode.number
        inode.links += 1

    def unlink(self, name: str) -> int:
        inode = self.lookup(name)
        del self.directory[name]
        inode.links -= 1
        return inode.number

    def reclaim(self, number: int) -> None:
        """The kernel calls this only when the inode has no open file descriptors."""
        inode = self.inodes[number]
        if inode.type == "regular" and inode.links == 0:
            inode.blocks.clear()
            del self.inodes[number]

    @staticmethod
    def _store_block(inode: Inode, index: int, data: bytes) -> None:
        if any(data):
            inode.blocks[index] = data
        else:
            inode.blocks.pop(index, None)

    def read(self, number: int, offset: int, size: int) -> bytes:
        nonnegative(offset, "Offset")
        nonnegative(size, "Size")
        inode = self.inodes[number]
        end = min(offset + size, inode.size)
        result = bytearray()
        while offset < end:
            index = offset // BLOCK_SIZE
            start = offset % BLOCK_SIZE
            count = min(BLOCK_SIZE - start, end - offset)
            block = inode.blocks.get(index, bytes(BLOCK_SIZE))
            result.extend(block[start:start + count])
            offset += count
        return bytes(result)

    def write(self, number: int, offset: int, data: bytes) -> int:
        nonnegative(offset, "Offset")
        if not isinstance(data, bytes):
            raise FileSystemError("Write data must be of type bytes")
        inode = self.inodes[number]
        if not data:
            return 0
        position = 0
        while position < len(data):
            index = (offset + position) // BLOCK_SIZE
            start = (offset + position) % BLOCK_SIZE
            count = min(BLOCK_SIZE - start, len(data) - position)
            block = bytearray(inode.blocks.get(index, bytes(BLOCK_SIZE)))
            block[start:start + count] = data[position:position + count]
            self._store_block(inode, index, bytes(block))
            position += count
        inode.size = max(inode.size, offset + len(data))
        return len(data)

    def truncate(self, name: str, size: int) -> None:
        nonnegative(size, "Size")
        inode = self.lookup(name)
        if size < inode.size:
            last = size // BLOCK_SIZE
            tail = size % BLOCK_SIZE
            for index in list(inode.blocks):
                if index > last or (index == last and tail == 0):
                    del inode.blocks[index]
            if tail and last in inode.blocks:
                block = inode.blocks[last][:tail] + bytes(BLOCK_SIZE - tail)
                self._store_block(inode, last, block)
        # Extending the file does not allocate memory for zero blocks.
        inode.size = size
