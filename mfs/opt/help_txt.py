# help_txt.py
HELP_TEXT = """create name             create a file
stat name               show inode information (stat / for the root directory)
ls                      list names and inode numbers
open name               open a file; print the smallest available fd
close fd                close a file descriptor
seek fd offset          set the absolute offset in bytes
read fd size            read bytes (displayed as Python bytes)
write fd size [text]     write UTF-8 text; without text, write size bytes of 'x'
writehex fd hex          write arbitrary bytes, for example 41004200
link name1 name2         create another name for a file
unlink name             remove a file name
truncate name size      set the file size in bytes
help                    show this help message
exit                    exit (in-memory data will be lost)
Quote names and text containing spaces. Comments start with #.
"""
