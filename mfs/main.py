# main.py

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
               "link": (2,), "unlink": (1,), "truncate": (2,),
               "help": (0,), "exit": (0,)}
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
        print(json.dumps(kernel.stat(args[0]), ensure_ascii=False, indent=4))
    elif command == "ls":
        entries = kernel.ls()
        print("\n".join(f"{number}\t{name!r}" for name, number in entries) or "(empty)")
    elif command == "open":
        print(f"fd={kernel.open(args[0])}")
    elif command == "close":
            kernel.close(int(args[0]))
            print("OK")
    elif command == "seek":
        kernel.seek(int(args[0]), int(args[1]))
        print("OK")
    elif command == "read":
        print(kernel.read(int(args[0]), int(args[1])))
    elif command == "write":
        fd = int(args[0])
        size = int(args[1])
        nonnegative(size, "Size")
        data = args[2].encode("utf-8") if len(args) == 3 else b"x" * size
        if len(data) != size:
            raise FileSystemError(f"Expected {size} bytes, got {len(data)}")
        print(f"written={kernel.write(fd, data)}")
    elif command == "link":
        kernel.link(args[0], args[1])
        print("OK")
    elif command == "unlink":
        kernel.unlink(args[0])
        print("OK")
    elif command == "truncate":
        kernel.truncate(args[0], int(args[1]))
        print("OK")

    return True


def main() -> None:
    kernel = Kernel()
    print("In-memory single-directory filesystem. Type help for available commands.")
    try:
        while True:
            line = input("mike_fs> ")
            try:
                if not execute(kernel, line):
                    break
            except (FileSystemError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    raise SystemExit(main())
