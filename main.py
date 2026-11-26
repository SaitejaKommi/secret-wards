#!/usr/bin/env python3
"""Entry point required by the organisers' contract: python main.py --input {input} --output {output}
The secret comes from the environment variable RAKSHA_SECRET (never printed or written)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))  # works without installing the package

from secretwards.contract.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
