from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass(frozen=True)
class AppConfig:
    log_file_path: Path
    overlay_state_path: Path
    voting_window_seconds: int
    minimum_votes: int
    end_rate_threshold: float
    poll_interval_seconds: float
    supported_services: tuple[str, ...]
    read_existing_log_on_start: bool


DEFAULT_CONFIG: dict[str, Any] = {
    "log_file_path": "onecomme_log.jsonl",
    "overlay_state_path": "overlay_state.json",
    "voting_window_seconds": 180,
    "minimum_votes": 20,
    "end_rate_threshold": 0.7,
    "poll_interval_seconds": 0.5,
    "supported_services": ["twicas", "kick", "twitch"],
    "read_existing_log_on_start": False,
}


def ensure_config(path: Path = DEFAULT_CONFIG_PATH) -> None:
    if path.exists():
        return
    path.write_text(
        json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_config(path: Path, updates: dict[str, Any]) -> None:
    ensure_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update(updates)
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    ensure_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    merged = {**DEFAULT_CONFIG, **raw}
    base_dir = path.resolve().parent

    def resolve(value: str) -> Path:
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return (base_dir / candidate).resolve()

    return AppConfig(
        log_file_path=resolve(str(merged["log_file_path"])),
        overlay_state_path=resolve(str(merged["overlay_state_path"])),
        voting_window_seconds=int(merged["voting_window_seconds"]),
        minimum_votes=int(merged["minimum_votes"]),
        end_rate_threshold=float(merged["end_rate_threshold"]),
        poll_interval_seconds=float(merged["poll_interval_seconds"]),
        supported_services=tuple(str(item).lower() for item in merged["supported_services"]),
        read_existing_log_on_start=bool(merged["read_existing_log_on_start"]),
    )
