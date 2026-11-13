# errors.py

class CommandError(Exception):
    """Invalid command or command arguments."""

class FileSystemError(Exception):
    """A filesystem operation error."""