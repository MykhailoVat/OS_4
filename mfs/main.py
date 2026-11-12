# main.py
"""Interactive shell and command script execution."""

import argparse
import json
import shlex
import sys

from mfs.filesystem import FileSystemError, nonnegative
from mfs.kernel import Kernel
from mfs.opt.help_txt import HELP_TEXT

# ugly but effective
def execute(kernel: Kernel, line: str) -> bool:
    parts = shlex.split(line, comments=True)
    if not parts:
        return True
    command, *args = parts
    arities = {"create": (1,), "stat": (1,), "ls": (0,), "open": (1,),
               "close": (1,), "seek": (2,), "read": (2,), "write": (2, 3),
               "writehex": (2,), "link": (2,), "unlink": (1,),
               "truncate": (2,), "help": (0,), "exit": (0,)}
    if command not in arities:
        raise FileSystemError(f"Unknown command {command!r}; type help")
    if len(args) not in arities[command]:
        raise FileSystemError(f"Invalid number of arguments for {command}; type help")
    if command == "exit":
        return False
    if command == "help":
        print(HELP_TEXT)
    elif command == "create":
        print(f"inode={kernel.create(args[0])}")
    elif command == "stat":
        print(json.dumps(kernel.stat(args[0]), ensure_ascii=False))
    elif command == "ls":
        entries = kernel.ls()
        print("\n".join(f"{number}\t{name!r}" for name, number in entries) or "(empty)")
    elif command == "open":
        print(f"fd={kernel.open(args[0])}")
    elif command == "read":
        print(repr(kernel.read(int(args[0]), int(args[1]))))
    elif command in {"write", "writehex"}:
        fd = int(args[0])
        if command == "writehex":
            data = bytes.fromhex(args[1])
        else:
            size = int(args[1])
            nonnegative(size, "Size")
            data = args[2].encode("utf-8") if len(args) == 3 else b"x" * size
            if len(data) != size:
                raise FileSystemError(f"Expected {size} bytes, got {len(data)}")
        print(f"written={kernel.write(fd, data)}")
    else:
        if command == "close":
            kernel.close(int(args[0]))
        elif command == "seek":
            kernel.seek(int(args[0]), int(args[1]))
        elif command == "link":
            kernel.link(*args)
        elif command == "unlink":
            kernel.unlink(args[0])
        elif command == "truncate":
            kernel.truncate(args[0], int(args[1]))
        print("OK")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="In-memory filesystem")
    parser.add_argument("script", nargs="?", help="UTF-8 command script")
    options = parser.parse_args()
    kernel = Kernel()
    stream = sys.stdin
    if options.script:
        try:
            stream = open(options.script, encoding="utf-8")
        except OSError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    interactive = not options.script and sys.stdin.isatty()
    status = 0
    if interactive:
        print("In-memory filesystem. Type help for available commands.")
    try:
        while True:
            if interactive:
                print("mike_fs> ", end="", flush=True)
            line = stream.readline()
            if not line:
                break
            if options.script and line.strip() and not line.lstrip().startswith("#"):
                print(f"fs> {line.rstrip()}")
            try:
                if not execute(kernel, line):
                    break
            except (FileSystemError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)
                status = 1
    except KeyboardInterrupt:
        print()
    finally:
        if options.script:
            stream.close()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
