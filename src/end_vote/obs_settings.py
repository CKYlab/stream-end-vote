from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import update_config
from .obs_control import ObsController, ObsTestResult


STOP_STREAMING_CONFIRMATION = (
    "この設定をONにすると、終了ライン到達後のカウントダウン完了時に"
    "OBSへ配信停止要求を送ります。必ず配信外でテストしてください。"
)


@dataclass(frozen=True)
class ObsSettings:
    obs_websocket_enabled: bool
    stop_streaming_enabled: bool
    obs_host: str
    obs_port: int
    obs_password: str

    def to_config_updates(self) -> dict[str, object]:
        return {
            "obs_websocket_enabled": self.obs_websocket_enabled,
            "stop_streaming_enabled": self.stop_streaming_enabled,
            "obs_host": self.obs_host,
            "obs_port": self.obs_port,
            "obs_password": self.obs_password,
        }


def validate_obs_port(value: object) -> int:
    text = str(value).strip()
    try:
        port = int(text)
    except ValueError as exc:
        raise ValueError("OBSポートは1〜65535の数字で入力してください") from exc
    if not 1 <= port <= 65535:
        raise ValueError("OBSポートは1〜65535の数字で入力してください")
    return port


def save_obs_settings(config_path: Path, settings: ObsSettings) -> None:
    update_config(config_path, settings.to_config_updates())


def test_obs_connection_from_settings(
    settings: ObsSettings,
    *,
    controller_factory: Callable[[ObsSettings], ObsController] | None = None,
) -> ObsTestResult:
    if not settings.obs_websocket_enabled:
        controller = ObsController(
            enabled=False,
            host=settings.obs_host,
            port=settings.obs_port,
            password=settings.obs_password,
        )
        return controller.test_connection()

    factory = controller_factory or _default_controller_factory
    try:
        controller = factory(settings)
        return controller.test_connection()
    except Exception as exc:
        disabled_controller = ObsController(
            enabled=True,
            host=settings.obs_host,
            port=settings.obs_port,
            password=settings.obs_password,
            client_factory=lambda: (_raise(exc)),
        )
        return disabled_controller.test_connection()


def _default_controller_factory(settings: ObsSettings) -> ObsController:
    return ObsController(
        enabled=settings.obs_websocket_enabled,
        host=settings.obs_host,
        port=settings.obs_port,
        password=settings.obs_password,
    )


def _raise(exc: Exception) -> None:
    raise exc
