#!/usr/bin/env python3
"""Store the Anthropic API key for fill_meanings.py in a private file, without shell quoting.

Run it, paste the key at the prompt (nothing is echoed), press Enter. The key is written to
~/.config/bubble-word-tools/anthropic_api_key with owner-only permissions. fill_meanings.py reads
that file when ANTHROPIC_API_KEY is not exported.
"""
import getpass
import os
import stat
import sys

KEY_DIR = os.path.expanduser("~/.config/bubble-word-tools")
KEY_PATH = os.path.join(KEY_DIR, "anthropic_api_key")


def main():
    key = getpass.getpass("Paste your Anthropic API key and press Enter (input is hidden): ").strip()
    if not key.startswith("sk-ant-") or len(key) < 60:
        sys.exit(f"That does not look like an Anthropic key (got {len(key)} chars, expected 'sk-ant-...' of 90+). Nothing saved.")
    os.makedirs(KEY_DIR, mode=0o700, exist_ok=True)
    with open(KEY_PATH, "w", encoding="utf-8") as f:
        f.write(key + "\n")
    os.chmod(KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)
    print(f"saved ({len(key)} chars) to {KEY_PATH}")


if __name__ == "__main__":
    main()
