from __future__ import annotations

import json
from pathlib import Path
from ludiglot.core.schema_analyzer import summarize_keys


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    args = parser.parse_args()

    obj = json.loads(args.json_path.read_text(encoding="utf-8"))
    summary = summarize_keys(obj)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
