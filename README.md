<!-- README.md -->
# Laboratory assignment 4: filesystem

A Python implementation of the **in-memory storage** variant allowed by
`task-4_ukr.pdf`. This variant requires no bitmap, fixed block or inode limits,
or `mkfs` command. The filesystem is initialized at startup; its data is lost
when the program exits. It uses no FUSE, backing files, or third-party runtime
libraries. Requires Python 3.10 or later; tests require pytest.

## Running

```bash
python -m mfs
python -m mfs mfs/opt/demo.txt
pytest -v
```

Type `help` in the shell to see the syntax. Commands can also be supplied through
stdin. All operations are available as `Kernel` methods for direct Python calls.
Errors are displayed in English. The shell continues after an error, and the
process returns exit code 1 if any error occurred. Normal completion returns 0.

## Program structure and data formats

- `mfs/filesystem.py` — driver: inodes, directory, block reads and writes,
  hard links, resizing, and data reclamation.
- `mfs/kernel.py` — kernel subsystem: open file table, smallest available fd
  selection, independent offsets, and inode reclamation after the last close.
- `mfs/main.py` — command-line interface.
- `mfs/opt/help_txt.py` — command help text.
- `tests/test_filesystem.py` — automated tests.
- `mfs/opt/demo.txt` — examples of every required command for this variant.

A filesystem descriptor (`Inode`) contains its number, type (`regular` or
`directory`), hard link count, size in bytes, and a block dictionary. Regular
files consist of **256-byte blocks**. Dictionary keys are logical block numbers
within the file; each value contains exactly 256 bytes. A missing key represents
a zero block. Thus, `truncate` can extend a file to a large size without
allocating blocks. Writing an entirely zero block does not consume block storage
either. The last block is padded with zeros, but reads stop at the logical EOF.

The dictionary replaces direct and indirect pointers, as permitted by the
assignment for in-memory storage. There are no global physical block numbers;
`stat` reports the logical numbers of allocated blocks in `block_map`.

The single root directory has inode 0 and a dictionary mapping names to inode
numbers. Removing a dictionary entry invalidates its hard link without a
separate flag. Names are nonempty UTF-8 strings of up to **255 bytes**, excluding
`.` and `..`, and cannot contain `/` or NUL. Quote names containing spaces.
`stat /` shows the root directory: its `size` is 0 because it is not serialized
into blocks, while `entries` contains the entry count. Inodes are stored in a
dictionary; their numbers increase and are never reused. There is no fixed limit
on their count.

A numeric **fd** belongs to the kernel table and differs from an **inode** number.
Each `open` creates a separate record `{inode, offset=0}`. Removing the last name
does not prevent reads and writes through open descriptors. Data is reclaimed
when neither hard links nor open descriptors remain. Perform all file lifetime
operations through `Kernel`.

## Commands and conventions

| Command | Action |
| --- | --- |
| `create name` | Create an empty file and its name |
| `stat name` | Show inode information and allocated block map |
| `ls` | List hard links with inode numbers |
| `open name` | Open a file and print `fd=N` |
| `close fd` | Close a descriptor and release its number |
| `seek fd offset` | Set an absolute nonnegative offset |
| `read fd size` | Read up to size bytes, stopping at EOF |
| `write fd size [text]` | Write size bytes; without text, write bytes of `x` |
| `link name1 name2` | Create another name for the same inode |
| `unlink name` | Remove a hard link |
| `truncate name size` | Resize a file; the new region reads as zeros |

`open name` prints the number to use in subsequent commands. The PDF's
`fd = open name` notation is not assignment syntax supported by the shell.

For text writes, the **UTF-8 byte count** must equal `size`. For example,
`write 0 4 "test"`. The additional command `writehex 0 410042` writes arbitrary
bytes, including NUL. In Python, use `kernel.write(fd, b"A\x00B")`.
`read` displays a `bytes` representation, so zeros appear as `\x00`.

Following the literal wording of the PDF, `read fd size` advances the offset by
the requested `size`, even for a short read at EOF. Reading beyond EOF returns
`b''`. Writing advances the offset by the number of bytes written. Seeking past
EOF is allowed; a subsequent write creates a zero-filled gap. A zero-length
write does not extend the file. `truncate` does not change open file offsets.

## Examples and verification

Running `python -m mfs mfs/opt/demo.txt` prints each command and its result,
covering all required operations. For example, after writing `hello`, creating
the `copy` link, and extending the file to 1024 bytes, `stat notes` reports
`links=2`, `size=1024`, and `allocated_blocks=1`. Reading after shrinking to
3 bytes and extending to 8 returns `b'hel\x00\x00\x00\x00\x00'`. After both
names are removed, `ls` shows an empty directory, while the same file remains
readable through its fd.

Tests cover block boundaries, sparse regions and zero blocks, truncated tails,
independent offsets, fd reuse, hard links, unlinked open file lifetime, invalid
arguments, and shell commands. An additional 300 write and resize operations are
compared against a dense reference array. The program listing is in the `.py`
files included in this directory.
