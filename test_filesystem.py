# test_filesystem.py
"""Перевірка семантики ФС, розріджених файлів та консольних команд."""

import contextlib
import io
import random
import unittest

from filesystem import BLOCK_SIZE, FileSystemError
from kernel import Kernel
from main import execute


class FileSystemTests(unittest.TestCase):
    def setUp(self):
        self.kernel = Kernel()
        self.number = self.kernel.create("file")
        self.fd = self.kernel.open("file")

    def test_smallest_fd_and_independent_offsets(self):
        k = self.kernel
        second = k.open("file")
        third = k.open("file")
        self.assertEqual((self.fd, second, third), (0, 1, 2))
        k.write(self.fd, b"abc")
        self.assertEqual(k.read(second, 2), b"ab")
        self.assertEqual(k.open_files[self.fd].offset, 3)
        self.assertEqual(k.open_files[third].offset, 0)
        k.close(second)
        self.assertEqual(k.open("file"), 1)

    def test_cross_block_write_and_overwrite(self):
        k = self.kernel
        data = bytes(range(256)) * 3
        k.write(self.fd, data)
        k.seek(self.fd, BLOCK_SIZE - 1)
        k.write(self.fd, b"XYZ")
        k.seek(self.fd, 0)
        self.assertEqual(k.read(self.fd, len(data)), data[:255] + b"XYZ" + data[258:])
        self.assertTrue(all(len(b) == BLOCK_SIZE for b in k.fs.inodes[self.number].blocks.values()))

    def test_huge_sparse_extension_and_gap(self):
        k = self.kernel
        k.truncate("file", 10**12)
        self.assertEqual(k.stat("file")["allocated_blocks"], 0)
        k.seek(self.fd, 10**12 - 2)
        self.assertEqual(k.read(self.fd, 2), b"\0\0")
        k.seek(self.fd, 10**12 + 2)
        k.write(self.fd, b"A")
        self.assertEqual(k.stat("file")["allocated_blocks"], 1)
        k.seek(self.fd, 10**12)
        self.assertEqual(k.read(self.fd, 3), b"\0\0A")

    def test_shrink_clears_tail_before_regrowth(self):
        k = self.kernel
        k.write(self.fd, b"a" * (BLOCK_SIZE * 3))
        k.truncate("file", BLOCK_SIZE + 1)
        self.assertEqual(k.stat("file")["allocated_blocks"], 2)
        k.truncate("file", BLOCK_SIZE * 3)
        k.seek(self.fd, BLOCK_SIZE)
        self.assertEqual(k.read(self.fd, BLOCK_SIZE * 2), b"a" + bytes(BLOCK_SIZE * 2 - 1))
        k.truncate("file", BLOCK_SIZE)
        self.assertEqual(k.stat("file")["block_map"], [0])
        k.truncate("file", 0)
        self.assertEqual(k.stat("file")["allocated_blocks"], 0)

    def test_zero_blocks_are_released(self):
        k = self.kernel
        k.write(self.fd, b"a" * BLOCK_SIZE)
        k.seek(self.fd, 0)
        k.write(self.fd, bytes(BLOCK_SIZE * 2))
        self.assertEqual(k.stat("file")["allocated_blocks"], 0)
        self.assertEqual(k.stat("file")["size"], BLOCK_SIZE * 2)

    def test_hard_links_and_unlinked_open_file(self):
        k = self.kernel
        k.link("file", "alias")
        self.assertEqual(k.stat("alias")["links"], 2)
        self.assertEqual(k.stat("alias")["inode"], self.number)
        second = k.open("alias")
        k.unlink("file")
        k.unlink("alias")
        self.assertEqual(k.ls(), [])
        self.assertEqual(k.fs.inodes[self.number].links, 0)
        k.write(self.fd, b"still alive")
        self.assertEqual(k.read(second, 11), b"still alive")
        new_number = k.create("file")
        self.assertNotEqual(new_number, self.number)
        k.close(self.fd)
        self.assertIn(self.number, k.fs.inodes)
        k.close(second)
        self.assertNotIn(self.number, k.fs.inodes)
        self.assertEqual(k.stat("file")["size"], 0)

    def test_unopened_unlink_reclaims_immediately(self):
        number = self.kernel.create("temporary")
        self.kernel.unlink("temporary")
        self.assertNotIn(number, self.kernel.fs.inodes)

    def test_eof_and_zero_length_io(self):
        k = self.kernel
        k.write(self.fd, b"abc")
        k.seek(self.fd, 1)
        self.assertEqual(k.read(self.fd, 10), b"bc")
        self.assertEqual(k.open_files[self.fd].offset, 11)
        self.assertEqual(k.read(self.fd, 1), b"")
        self.assertEqual(k.write(self.fd, b""), 0)
        self.assertEqual(k.stat("file")["size"], 3)
        self.assertEqual(k.read(self.fd, 0), b"")

    def test_errors_preserve_state(self):
        k = self.kernel
        for name in ["", ".", "..", "a/b", "a\0b", "я" * 128]:
            with self.subTest(name=name), self.assertRaises(FileSystemError):
                k.create(name)
        operations = [lambda: k.create("file"), lambda: k.open("missing"),
                      lambda: k.close(20), lambda: k.seek(self.fd, -1),
                      lambda: k.read(self.fd, -1), lambda: k.truncate("file", -1),
                      lambda: k.link("file", "file"), lambda: k.unlink("missing")]
        for operation in operations:
            with self.assertRaises(FileSystemError):
                operation()
        self.assertEqual(k.stat("file")["links"], 1)
        self.assertEqual(k.stat("file")["size"], 0)
        self.assertEqual(k.open_files[self.fd].offset, 0)

    def test_random_io_against_dense_reference(self):
        rng = random.Random(42)
        k = self.kernel
        reference = bytearray()
        for _ in range(300):
            if rng.randrange(3) == 0:
                size = rng.randrange(1500)
                k.truncate("file", size)
                if size < len(reference):
                    del reference[size:]
                else:
                    reference.extend(bytes(size - len(reference)))
            else:
                offset = rng.randrange(1500)
                data = bytes(rng.randrange(4) for _ in range(rng.randrange(300)))
                k.seek(self.fd, offset)
                k.write(self.fd, data)
                if data:
                    end = offset + len(data)
                    if end > len(reference):
                        reference.extend(bytes(end - len(reference)))
                    reference[offset:end] = data
            k.seek(self.fd, 0)
            self.assertEqual(k.read(self.fd, len(reference) + 1), bytes(reference))
            self.assertEqual(k.stat("file")["size"], len(reference))
            self.assertTrue(all(any(b) for b in k.fs.inodes[self.number].blocks.values()))

    def test_console(self):
        k = Kernel()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for line in ['create "мій файл"', 'open "мій файл"', 'write 0 4 "тест"']:
                if line.startswith("write"):
                    with self.assertRaises(FileSystemError):
                        execute(k, line)
                else:
                    execute(k, line)
            for line in ['write 0 8 "тест"', 'seek 0 0', 'read 0 8',
                         'writehex 0 000041', 'stat "мій файл"', 'ls',
                         'link "мій файл" alias', 'truncate alias 1',
                         'unlink alias', 'close 0', 'help']:
                self.assertTrue(execute(k, line))
            self.assertFalse(execute(k, "exit"))
        self.assertIn("fd=0", output.getvalue())
        self.assertEqual(k.stat("мій файл")["size"], 1)


if __name__ == "__main__":
    unittest.main()
