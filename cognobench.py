#!/usr/bin/env python3
"""Root shim — run the persona routing bench with `python3 cognobench.py`.

Examples:
    python3 cognobench.py --stub                 # deterministic smoke (no network)
    python3 cognobench.py                         # real Ollama embedder
    python3 cognobench.py --threshold 0.30        # calibrate the match threshold
    python3 cognobench.py --stub --min-score 100  # CI gate
"""

import sys

from cognobench.runner import main

if __name__ == "__main__":
    sys.exit(main())
