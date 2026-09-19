#!/usr/bin/env python3
"""Entry point for the nightlight-schedule command (see nightlight/cli.py).

Run it directly, through a symlink on PATH, or as `python3 <path>`: Python
puts this file's real directory on sys.path, so the `nightlight` package next
to it is importable either way.
"""

import sys

# The Omarchy shell hot-reloads a plugin whenever a file in its folder
# changes, so don't let Python drop __pycache__ directories in there.
sys.dont_write_bytecode = True

from nightlight.cli import main  # noqa: E402

sys.exit(main())
