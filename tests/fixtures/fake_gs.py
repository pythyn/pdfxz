#!/usr/bin/env python3
"""A stand-in for the real `gs` binary, used only by the test suite.

Reads FAKE_GS_MODE from the environment to decide how to behave:
  success    (default) write an output file half the size of the input
  unchanged  write an output file the same size as the input
  larger     write an output file bigger than the input
  fail       exit 1 without writing an output file
  no_output  exit 0 but never write an output file (simulates a Ghostscript bug)
  slow       sleep for FAKE_GS_SLEEP seconds (default 5) before behaving like 'success'
             - used to exercise cancellation
"""

import os
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    output = None
    input_path = None
    for arg in args:
        if arg.startswith("-sOutputFile="):
            output = arg.split("=", 1)[1]
        elif not arg.startswith("-"):
            input_path = arg

    mode = os.environ.get("FAKE_GS_MODE", "success")

    if mode == "slow":
        time.sleep(float(os.environ.get("FAKE_GS_SLEEP", "5")))
        mode = "success"

    if mode == "fail":
        sys.stderr.write("fake ghostscript error: simulated failure\n")
        return 1

    if mode == "no_output":
        return 0

    orig_size = os.path.getsize(input_path) if input_path else 0

    if mode == "unchanged":
        new_size = orig_size
    elif mode == "larger":
        new_size = orig_size + 100
    else:  # success (default)
        new_size = max(1, orig_size // 2)

    assert output is not None
    with open(output, "wb") as fh:
        fh.write(b"0" * new_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
