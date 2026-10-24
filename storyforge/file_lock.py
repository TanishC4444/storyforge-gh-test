"""Exclusive advisory locks for shared provider ledgers on Unix and Windows."""
import errno
import os
import time

LOCK_EX = 2


def flock(stream, operation):
    if operation != LOCK_EX:
        raise ValueError('Only exclusive ledger locks are supported')
    if os.name != 'nt':
        import fcntl
        return fcntl.flock(stream, fcntl.LOCK_EX)
    import msvcrt
    # Windows byte locks need a byte to lock. Closing the handle releases it,
    # matching the existing with-open lifetime of all ledger callers.
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(' ')
        stream.flush()
    deadline = time.monotonic() + 60
    while True:
        stream.seek(0)
        try:
            return msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or time.monotonic() >= deadline:
                raise
            time.sleep(.05)
