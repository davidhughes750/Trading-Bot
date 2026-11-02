"""Small shared helpers."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | Path, text: str) -> None:
    """Write `text` to `path` so readers never see a half-written file.

    The text goes to a temporary file in the same folder, is flushed to disk,
    and then replaces the target in one step. A crash mid-write leaves the old
    file untouched instead of a truncated one.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: str | Path, payload: Any, indent: int | None = 2) -> None:
    atomic_write_text(path, json.dumps(payload, indent=indent, default=str))


def append_jsonl(path: str | Path, record: Any) -> None:
    """Append one JSON record as a line (used for append-only logs)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def read_jsonl(path: str | Path) -> list:
    target = Path(path)
    if not target.exists():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------------------------
# Keeping secrets out of logs
# ---------------------------------------------------------------------------------------------
_SECRET_PATTERNS = [
    # API keys passed in a URL query string (Gemini uses ?key=...)
    (re.compile(r"(?i)([?&](?:key|api_key|apikey|token|access_token)=)[^&\s)\"']+"), r"\1***"),
    # Telegram bot tokens appear in the URL path: /bot123456789:AAE.../sendMessage
    (re.compile(r"(/bot)\d{6,}:[A-Za-z0-9_-]{20,}"), r"\1***"),
]


def redact_secrets(text: str) -> str:
    """Blank out API keys and bot tokens in `text` (log lines, exception messages)."""
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactSecretsFilter(logging.Filter):
    """Logging filter that scrubs secrets from messages and tracebacks before any handler writes them.

    `requests` exceptions often include the full request URL, which would otherwise put the Gemini
    key or Telegram token into log files and the dashboard's recent-log feed.
    """

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            cleaned = redact_secrets(message)
            if cleaned != message:
                record.msg, record.args = cleaned, ()
            if record.exc_info and not record.exc_text:
                record.exc_text = redact_secrets(self._formatter.formatException(record.exc_info))
            elif record.exc_text:
                record.exc_text = redact_secrets(record.exc_text)
        except Exception:  # never let log scrubbing break logging
            pass
        return True
