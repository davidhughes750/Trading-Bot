#!/usr/bin/env python3
"""Regenerate web/static/js/mobile-meta.js (phone page logos) from STOCK_METADATA in dashboard.js.

Run after adding or changing a stock in the desktop metadata table.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = re.compile(
    r"'([A-Z0-9_]+)':\s*\{\s*name:\s*'((?:[^'\\]|\\.)*)',\s*sector:\s*'((?:[^'\\]|\\.)*)',\s*domain:\s*'([^']*)'[^}]*\}"
)


def desktop_metadata() -> dict:
    src = (ROOT / "web/static/js/dashboard.js").read_text(encoding="utf-8")
    block = src[src.index("const STOCK_METADATA = {"):]
    block = block[: block.index("\n    };")]
    return {k: [n.replace("\\'", "'"), s.replace("\\'", "'"), d] for k, n, s, d in ENTRY.findall(block)}


def main() -> int:
    meta = desktop_metadata()
    out = (
        "// Generated from STOCK_METADATA in dashboard.js (symbol -> [name, sector, website]). Used for logos on the phone page.\n"
        "// tests/test_long_term_and_heartbeat.py fails if this drifts from dashboard.js; regenerate by running\n"
        "// `python tools/sync_mobile_meta.py`.\n"
        f"const STOCK_META = {json.dumps(meta, indent=1, ensure_ascii=False)};\n"
    )
    (ROOT / "web/static/js/mobile-meta.js").write_text(out, encoding="utf-8")
    print(f"Wrote {len(meta)} entries to web/static/js/mobile-meta.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
