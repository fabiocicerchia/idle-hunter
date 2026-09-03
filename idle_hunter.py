#!/usr/bin/env python3
"""idle-hunter entrypoint. The tool itself lives in idle_hunter_lib/."""

import sys

from idle_hunter_lib.cli import main

if __name__ == "__main__":
    sys.exit(main())
