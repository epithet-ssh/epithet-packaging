"""Hold the release lock for a child command, including its target processes."""
import fcntl
import os
import subprocess
import sys

with open(sys.argv[1], "a") as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Another release is running; try again after it finishes", file=sys.stderr)
        raise SystemExit(1)
    # Inherit the lock in descendants: interruption must not let another release
    # overwrite working directories while an existing build is still running.
    os.set_inheritable(lock.fileno(), True)
    result = subprocess.run(sys.argv[2:], env=dict(os.environ, EPITHET_RELEASE_LOCKED="1"),
                            pass_fds=(lock.fileno(),))
    raise SystemExit(result.returncode)
