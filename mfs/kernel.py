# kernel.py

from dataclasses import dataclass

from mfs.opt.errors import KernelError
from mfs.filesystem import MemoryFileSystem, nonnegative

@dataclass
class OpenFile:
    inode: int
    offset: int = 0


class Kernel:
    def __init__(self) -> None:
        self.fs = MemoryFileSystem()
        self.open_files: dict[int, OpenFile] = {}

    def _find_opened(self, fd: int) -> OpenFile:
        nonnegative(fd, "fd")
        if fd not in self.open_files:
            raise KernelError(f"File descriptor fd={fd} is not open")
        return self.open_files[fd]

    def _reclaim(self, number: int) -> None:
        for item in self.open_files.values():
            if item.inode == number:
                return

        self.fs.reclaim(number)

    def create(self, name: str) -> int:
        return self.fs.create(name)

    def stat(self, name: str) -> dict:
        return self.fs.stat(name)

    def ls(self) -> list[tuple[str, int]]:
        return self.fs.ls()

    def open(self, name: str) -> int:
        inode = self.fs.lookup(name)
        fd = 0
        while fd in self.open_files:
            fd += 1
        self.open_files[fd] = OpenFile(inode.number)
        return fd

    def close(self, fd: int) -> None:
        opened = self._find_opened(fd)
        del self.open_files[fd]
        self._reclaim(opened.inode)

    def seek(self, fd: int, offset: int) -> None:
        opened = self._find_opened(fd)
        nonnegative(offset, "Offset")
        opened.offset = offset

    def read(self, fd: int, size: int) -> bytes:
        opened = self._find_opened(fd)
        data = self.fs.read(opened.inode, opened.offset, size)
        # The assignment requires advancing the offset by the requested size.
        opened.offset += size
        return data

    def write(self, fd: int, data: bytes) -> int:
        opened = self._find_opened(fd)
        count = self.fs.write(opened.inode, opened.offset, data)
        opened.offset += count
        return count

    def link(self, source: str, target: str) -> None:
        self.fs.link(source, target)

    def unlink(self, name: str) -> None:
        number = self.fs.unlink(name)
        self._reclaim(number)

    def truncate(self, name: str, size: int) -> None:
        self.fs.truncate(name, size)
