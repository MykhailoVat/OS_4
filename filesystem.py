# filesystem.py
"""Драйвер файлової системи в оперативній пам'яті без бітової карти."""

from dataclasses import dataclass, field

BLOCK_SIZE = 256
MAX_NAME_BYTES = 255

class FileSystemError(Exception):
    """Помилка операції файлової системи."""

def nonnegative(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise FileSystemError(f"{label}: потрібне невід'ємне ціле число")


@dataclass
class Inode:
    number: int
    kind: str = "regular"
    links: int = 0
    size: int = 0
    # Ключ — логічний номер блоку; відсутній ключ означає нульовий блок.
    blocks: dict[int, bytes] = field(default_factory=dict)


class MemoryFileSystem:
    """Дані тут є самим носієм, а не кешем іншого сховища.

    Коренева директорія має inode 0. Її записи зберігаються у словнику;
    видалення запису повністю прибирає відповідне жорстке посилання.
    """

    def __init__(self) -> None:
        self.inodes: dict[int, Inode] = {0: Inode(0, "directory", links=1)}
        self.directory: dict[str, int] = {}
        self._next_inode = 1

    @staticmethod
    def validate_name(name: str) -> None:
        if not isinstance(name, str) or not name or name in {".", ".."}:
            raise FileSystemError("Недопустиме ім'я файлу")
        if any(char in name for char in "/\x00"):
            raise FileSystemError("Ім'я не може містити '/' або NUL")
        try:
            length = len(name.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise FileSystemError("Ім'я повинно кодуватися в UTF-8") from error
        if length > MAX_NAME_BYTES:
            raise FileSystemError(f"Ім'я довше за {MAX_NAME_BYTES} байтів UTF-8")

    def lookup(self, name: str) -> Inode:
        self.validate_name(name)
        if name not in self.directory:
            raise FileSystemError(f"Файл {name!r} не існує")
        return self.inodes[self.directory[name]]

    def _check_new_name(self, name: str) -> None:
        self.validate_name(name)
        if name in self.directory:
            raise FileSystemError(f"Ім'я {name!r} вже існує")

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
            "type": inode.kind,
            "links": inode.links,
            "size": inode.size,
            "block_size": BLOCK_SIZE,
            "allocated_blocks": len(inode.blocks),
            "block_map": sorted(inode.blocks),
            **({"entries": len(self.directory)} if inode.kind == "directory" else {}),
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
        """Ядро викликає це тільки за відсутності відкритих файлів."""
        inode = self.inodes[number]
        if inode.kind == "regular" and inode.links == 0:
            inode.blocks.clear()
            del self.inodes[number]

    @staticmethod
    def _store_block(inode: Inode, index: int, data: bytes) -> None:
        if any(data):
            inode.blocks[index] = data
        else:
            inode.blocks.pop(index, None)

    def read(self, number: int, offset: int, size: int) -> bytes:
        nonnegative(offset, "Зміщення")
        nonnegative(size, "Розмір")
        inode = self.inodes[number]
        end = min(offset + size, inode.size)
        result = bytearray()
        while offset < end:
            index, start = divmod(offset, BLOCK_SIZE)
            count = min(BLOCK_SIZE - start, end - offset)
            block = inode.blocks.get(index, bytes(BLOCK_SIZE))
            result.extend(block[start:start + count])
            offset += count
        return bytes(result)

    def write(self, number: int, offset: int, data: bytes) -> int:
        nonnegative(offset, "Зміщення")
        if not isinstance(data, bytes):
            raise FileSystemError("Дані для запису повинні мати тип bytes")
        inode = self.inodes[number]
        if not data:
            return 0
        position = 0
        while position < len(data):
            index, start = divmod(offset + position, BLOCK_SIZE)
            count = min(BLOCK_SIZE - start, len(data) - position)
            block = bytearray(inode.blocks.get(index, bytes(BLOCK_SIZE)))
            block[start:start + count] = data[position:position + count]
            self._store_block(inode, index, bytes(block))
            position += count
        inode.size = max(inode.size, offset + len(data))
        return len(data)

    def truncate(self, name: str, size: int) -> None:
        nonnegative(size, "Розмір")
        inode = self.lookup(name)
        if size < inode.size:
            last, tail = divmod(size, BLOCK_SIZE)
            for index in list(inode.blocks):
                if index > last or (index == last and tail == 0):
                    del inode.blocks[index]
            if tail and last in inode.blocks:
                block = inode.blocks[last][:tail] + bytes(BLOCK_SIZE - tail)
                self._store_block(inode, last, block)
        # Збільшення розміру не виділяє пам'ять під нульові блоки.
        inode.size = size
