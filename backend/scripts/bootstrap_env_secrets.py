#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.env_secrets import render_env_with_generated_secrets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace placeholder secrets in an .env file with generated values.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the env file to update in place.",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    original = env_path.read_text(encoding="utf-8")
    updated, replaced = render_env_with_generated_secrets(original)
    env_path.write_text(f"{updated}\n", encoding="utf-8")

    if replaced:
        print("Updated secrets:", ", ".join(replaced))
    else:
        print("No placeholder secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
