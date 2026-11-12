# test_filesystem.py
"""Tests for kernel and filesystem semantics, including sparse files."""

import random

import pytest

from mfs.filesystem import BLOCK_SIZE, FileSystemError
from mfs.kernel import Kernel


@pytest.fixture
def opened_file():
    kernel = Kernel()
    number = kernel.create("file")
    fd = kernel.open("file")
    return kernel, number, fd


def test_smallest_fd_and_independent_offsets(opened_file):
    k, number, fd = opened_file
    second = k.open('file')
    third = k.open('file')
    assert (fd, second, third) == (0, 1, 2)
    k.write(fd, b'abc')
    assert k.read(second, 2) == b'ab'
    assert k.open_files[fd].offset == 3
    assert k.open_files[third].offset == 0
    k.close(second)
    assert k.open('file') == 1


def test_cross_block_write_and_overwrite(opened_file):
    k, number, fd = opened_file
    data = bytes(range(256)) * 3
    k.write(fd, data)
    k.seek(fd, BLOCK_SIZE - 1)
    k.write(fd, b'XYZ')
    k.seek(fd, 0)
    assert k.read(fd, len(data)) == data[:255] + b'XYZ' + data[258:]
    assert all(len(b) == BLOCK_SIZE for b in k.fs.inodes[number].blocks.values())


def test_huge_sparse_extension_and_gap(opened_file):
    k, number, fd = opened_file
    k.truncate('file', 10 ** 12)
    assert k.stat('file')['allocated_blocks'] == 0
    k.seek(fd, 10 ** 12 - 2)
    assert k.read(fd, 2) == b'\x00\x00'
    k.seek(fd, 10 ** 12 + 2)
    k.write(fd, b'A')
    assert k.stat('file')['allocated_blocks'] == 1
    k.seek(fd, 10 ** 12)
    assert k.read(fd, 3) == b'\x00\x00A'


def test_shrink_clears_tail_before_regrowth(opened_file):
    k, number, fd = opened_file
    k.write(fd, b'a' * (BLOCK_SIZE * 3))
    k.truncate('file', BLOCK_SIZE + 1)
    assert k.stat('file')['allocated_blocks'] == 2
    k.truncate('file', BLOCK_SIZE * 3)
    k.seek(fd, BLOCK_SIZE)
    assert k.read(fd, BLOCK_SIZE * 2) == b'a' + bytes(BLOCK_SIZE * 2 - 1)
    k.truncate('file', BLOCK_SIZE)
    assert k.stat('file')['block_map'] == [0]
    k.truncate('file', 0)
    assert k.stat('file')['allocated_blocks'] == 0


def test_zero_blocks_are_released(opened_file):
    k, number, fd = opened_file
    k.write(fd, b'a' * BLOCK_SIZE)
    k.seek(fd, 0)
    k.write(fd, bytes(BLOCK_SIZE * 2))
    assert k.stat('file')['allocated_blocks'] == 0
    assert k.stat('file')['size'] == BLOCK_SIZE * 2


def test_hard_links_and_unlinked_open_file(opened_file):
    k, number, fd = opened_file
    k.link('file', 'alias')
    assert k.stat('alias')['links'] == 2
    assert k.stat('alias')['inode'] == number
    second = k.open('alias')
    k.unlink('file')
    k.unlink('alias')
    assert k.ls() == []
    assert k.fs.inodes[number].links == 0
    k.write(fd, b'still alive')
    assert k.read(second, 11) == b'still alive'
    new_number = k.create('file')
    assert new_number != number
    k.close(fd)
    assert number in k.fs.inodes
    k.close(second)
    assert number not in k.fs.inodes
    assert k.stat('file')['size'] == 0


def test_unopened_unlink_reclaims_immediately(opened_file):
    k, number, fd = opened_file
    number = k.create('temporary')
    k.unlink('temporary')
    assert number not in k.fs.inodes


def test_eof_and_zero_length_io(opened_file):
    k, number, fd = opened_file
    k.write(fd, b'abc')
    k.seek(fd, 1)
    assert k.read(fd, 10) == b'bc'
    assert k.open_files[fd].offset == 11
    assert k.read(fd, 1) == b''
    assert k.write(fd, b'') == 0
    assert k.stat('file')['size'] == 3
    assert k.read(fd, 0) == b''


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\0b", "я" * 128])
def test_invalid_names_preserve_state(opened_file, name):
    k, number, fd = opened_file
    with pytest.raises(FileSystemError):
        k.create(name)
    assert k.ls() == [("file", number)]
    assert k.stat("file")["size"] == 0
    assert k.open_files[fd].offset == 0


@pytest.mark.parametrize(
    "method, args",
    [
        ("create", ("file",)),
        ("open", ("missing",)),
        ("close", (20,)),
        ("seek", (0, -1)),
        ("read", (0, -1)),
        ("truncate", ("file", -1)),
        ("link", ("file", "file")),
        ("unlink", ("missing",)),
    ],
)
def test_errors_preserve_state(opened_file, method, args):
    k, number, fd = opened_file
    with pytest.raises(FileSystemError):
        getattr(k, method)(*args)
    assert k.ls() == [("file", number)]
    assert k.stat("file")["links"] == 1
    assert k.stat("file")["size"] == 0
    assert k.open_files[fd].offset == 0



def test_random_io_against_dense_reference(opened_file):
    k, number, fd = opened_file
    rng = random.Random(42)
    reference = bytearray()
    for _ in range(300):
        if rng.randrange(3) == 0:
            size = rng.randrange(1500)
            k.truncate('file', size)
            if size < len(reference):
                del reference[size:]
            else:
                reference.extend(bytes(size - len(reference)))
        else:
            offset = rng.randrange(1500)
            data = bytes((rng.randrange(4) for _ in range(rng.randrange(300))))
            k.seek(fd, offset)
            k.write(fd, data)
            if data:
                end = offset + len(data)
                if end > len(reference):
                    reference.extend(bytes(end - len(reference)))
                reference[offset:end] = data
        k.seek(fd, 0)
        assert k.read(fd, len(reference) + 1) == bytes(reference)
        assert k.stat('file')['size'] == len(reference)
        assert all(any(b) for b in k.fs.inodes[number].blocks.values())
