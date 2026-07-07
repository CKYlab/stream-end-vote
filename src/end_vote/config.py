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
    countdown_enabled: bool
    countdown_seconds: int
    trigger_once_per_live: bool
    stop_streaming_enabled: bool
    obs_websocket_enabled: bool
    obs_host: str
    obs_port: int
    obs_password: str


DEFAULT_CONFIG: dict[str, Any] = {
    "log_file_path": "onecomme_log.jsonl",
    "overlay_state_path": "overlay_state.json",
    "voting_window_seconds": 180,
    "minimum_votes": 20,
    "end_rate_threshold": 0.7,
    "poll_interval_seconds": 0.5,
    "supported_services": ["twicas", "kick", "twitch"],
    "read_existing_log_on_start": False,
    "countdown_enabled": True,
    "countdown_seconds": 30,
    "trigger_once_per_live": True,
    # 安全側の初期値。実際に停止するには config.json で
    # obs_websocket_enabled と stop_streaming_enabled の両方を
    # 手で true にする必要がある（GUIからはONにできない）。
    "stop_streaming_enabled": False,
    "obs_websocket_enabled": False,
    "obs_host": "127.0.0.1",
    "obs_port": 4455,
    "obs_password": "",
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
        countdown_enabled=bool(merged["countdown_enabled"]),
        countdown_seconds=int(merged["countdown_seconds"]),
        trigger_once_per_live=bool(merged["trigger_once_per_live"]),
        stop_streaming_enabled=bool(merged["stop_streaming_enabled"]),
        obs_websocket_enabled=bool(merged["obs_websocket_enabled"]),
        obs_host=str(merged["obs_host"]),
        obs_port=int(merged["obs_port"]),
        obs_password=str(merged["obs_password"]),
    )
