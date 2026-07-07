from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


KIND_SUCCESS = "success"
KIND_DISABLED = "disabled"
KIND_AUTH_FAILED = "auth_failed"
KIND_CONNECT_FAILED = "connect_failed"
KIND_REQUEST_FAILED = "request_failed"

KIND_LABELS = {
    KIND_SUCCESS: "成功",
    KIND_DISABLED: "OBS連携がOFFです",
    KIND_AUTH_FAILED: "パスワードが違います",
    KIND_CONNECT_FAILED: "接続できません",
    KIND_REQUEST_FAILED: "OBSへの要求に失敗しました",
}


class ObsControlError(Exception):
    """OBS操作の失敗。kindで種類を区別する。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind

    def short_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass(frozen=True)
class ObsTestResult:
    ok: bool
    kind: str
    message: str
    streaming: bool | None = None


class ObsController:
    """obs-websocket (v5) でOBSを操作する。

    - enabled=False の間は接続もStopStreamも一切行わない。
    - 失敗は握りつぶさず、ObsControlError として呼び出し元へ返す。
    - client_factory はテスト用の差し替え口。既定は obsws_python.ReqClient。
    """

    def __init__(
        self,
        *,
        enabled: bool,
        host: str,
        port: int,
        password: str,
        timeout: float = 3.0,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._client_factory = client_factory or self._default_client_factory

    def _default_client_factory(self) -> Any:
        import obsws_python

        return obsws_python.ReqClient(
            host=self.host,
            port=self.port,
            password=self.password,
            timeout=self.timeout,
        )

    def test_connection(self) -> ObsTestResult:
        """接続確認。例外は投げず、分類済みの結果を返す。"""
        if not self.enabled:
            return ObsTestResult(
                ok=False, kind=KIND_DISABLED, message=KIND_LABELS[KIND_DISABLED]
            )
        try:
            client = self._client_factory()
        except Exception as exc:
            kind = _classify_error(exc)
            return ObsTestResult(ok=False, kind=kind, message=_describe(kind, exc))
        try:
            status = client.get_stream_status()
            streaming = bool(getattr(status, "output_active", False))
            state = "配信中" if streaming else "配信していません"
            return ObsTestResult(
                ok=True,
                kind=KIND_SUCCESS,
                message=f"接続成功（{state}）",
                streaming=streaming,
            )
        except Exception as exc:
            kind = _classify_error(exc)
            return ObsTestResult(ok=False, kind=kind, message=_describe(kind, exc))
        finally:
            _disconnect_quietly(client)

    def stop_streaming(self) -> str:
        """StopStreamを送る。失敗時は ObsControlError を送出する。"""
        if not self.enabled:
            raise ObsControlError(KIND_DISABLED, KIND_LABELS[KIND_DISABLED])
        try:
            client = self._client_factory()
        except Exception as exc:
            kind = _classify_error(exc)
            raise ObsControlError(kind, _describe(kind, exc)) from exc
        try:
            streaming = None
            try:
                status = client.get_stream_status()
                streaming = bool(getattr(status, "output_active", False))
            except Exception:
                # 状態確認に失敗しても停止要求自体は試みる。
                streaming = None
            if streaming is False:
                return "OBSは配信していませんでした（停止不要）"
            client.stop_stream()
            return "配信停止を実行しました"
        except Exception as exc:
            kind = _classify_error(exc)
            raise ObsControlError(kind, _describe(kind, exc)) from exc
        finally:
            _disconnect_quietly(client)


def _disconnect_quietly(client: Any) -> None:
    try:
        client.disconnect()
    except Exception:
        pass


def _classify_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "password" in message or "auth" in message or "identify" in message:
        return KIND_AUTH_FAILED
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return KIND_CONNECT_FAILED
    if "timeout" in message or "refused" in message or "connection" in message:
        return KIND_CONNECT_FAILED
    return KIND_REQUEST_FAILED


def _describe(kind: str, exc: Exception) -> str:
    label = KIND_LABELS.get(kind, kind)
    detail = str(exc).strip()
    if not detail:
        return label
    return f"{label}: {detail}"
