"""Fill placeholders such as <ACCOUNT_A_ID> with real values from local/accounts.env.

Files in Git keep placeholders so account IDs and user names are never published.
This script copies every JSON file under policies/ and src/ that contains a
placeholder into build/ (ignored by Git) with the real values filled in, ready to
paste into the AWS console or pass to the CLI with file://build/...

    python scripts/render.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_VALUES = ROOT / "local" / "accounts.env"
OUT = ROOT / "build"
PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")


def load_values():
    if not LOCAL_VALUES.exists():
        sys.exit(f"missing {LOCAL_VALUES}; copy local/accounts.env.example and fill it in")
    values = {}
    for line in LOCAL_VALUES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def main():
    values = load_values()
    rendered = 0
    for path in sorted(list((ROOT / "policies").rglob("*.json")) + list((ROOT / "src").rglob("*.json"))):
        text = path.read_text(encoding="utf-8")
        missing = {m for m in PLACEHOLDER.findall(text) if m not in values}
        if missing:
            sys.exit(f"{path.relative_to(ROOT)}: no value for {', '.join(sorted(missing))} in {LOCAL_VALUES.name}")
        if not PLACEHOLDER.search(text):
            continue
        target = OUT / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(PLACEHOLDER.sub(lambda m: values[m.group(1)], text), encoding="utf-8")
        print(f"rendered {target.relative_to(ROOT).as_posix()}")
        rendered += 1
    print(f"{rendered} file(s) written to build/")


if __name__ == "__main__":
    main()
