from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


LOG_PATTERNS = ("*.log", "*.jsonl")


@dataclass(frozen=True)
class LogCandidate:
    path: Path
    modified_at: float


def onecomme_comments_dirs() -> list[Path]:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "onecomme" / "comments")
    candidates.append(Path.home() / "AppData" / "Roaming" / "onecomme" / "comments")
    return _dedupe_paths(candidates)


def find_onecomme_log_candidates(
    *,
    search_dirs: list[Path] | None = None,
    limit: int = 30,
) -> list[LogCandidate]:
    roots = search_dirs if search_dirs is not None else onecomme_comments_dirs()
    candidates: list[LogCandidate] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            for pattern in LOG_PATTERNS:
                for path in root.rglob(pattern):
                    if path.is_file():
                        candidates.append(
                            LogCandidate(path.resolve(), path.stat().st_mtime)
                        )
        except OSError:
            continue

    candidates.sort(key=lambda item: item.modified_at, reverse=True)
    return candidates[:limit]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
