# errors.py

class CommandError(Exception):
    """Invalid command or command arguments."""

class KernelError(Exception):
    """Kernel operational error."""

class FileSystemError(Exception):
    """A filesystem operation error."""