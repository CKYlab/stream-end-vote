from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterator


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def tail_jsonl(
    path: Path,
    stop_requested: Callable[[], bool],
    *,
    poll_interval_seconds: float = 0.5,
    start_at_end: bool = True,
    on_parse_error: Callable[[Exception], None] | None = None,
) -> Iterator[dict]:
    position = 0
    current_size = path.stat().st_size if path.exists() else 0
    if start_at_end:
        position = current_size

    while not stop_requested():
        if not path.exists():
            time.sleep(poll_interval_seconds)
            continue

        size = path.stat().st_size
        if size < position:
            position = 0

        with path.open("r", encoding="utf-8-sig") as handle:
            handle.seek(position)
            while not stop_requested():
                line = handle.readline()
                if not line:
                    position = handle.tell()
                    break
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    if on_parse_error is not None:
                        on_parse_error(exc)
                    continue
                if isinstance(value, dict):
                    yield value

        time.sleep(poll_interval_seconds)
