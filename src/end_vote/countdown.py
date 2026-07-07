from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Callable


MODE_NORMAL = "normal"
MODE_COUNTDOWN = "countdown"
MODE_CANCELLED = "cancelled"
MODE_WOULD_STOP = "would_stop"


class CountdownController:
    """終了ライン到達後のカウントダウン状態を管理する。

    v0.3.5 の安全仕様:
    - OBS停止処理はこのクラスにもアプリ本体にも存在しない。
    - obs-websocket には接続しない。Stop Streaming は呼ばない。
    - stop_streaming_enabled が True でも on_stop_intent (将来のv0.4用
      フック) を呼ぶだけで、アプリ本体は on_stop_intent を渡さない。
    - カウントダウン完了時は would_stop 表示のみで配信は継続する。
    """

    def __init__(
        self,
        *,
        enabled: bool,
        countdown_seconds: int,
        trigger_once_per_live: bool,
        stop_streaming_enabled: bool,
        cancelled_display_seconds: float = 5.0,
        would_stop_display_seconds: float = 15.0,
        on_stop_intent: Callable[[], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.countdown_seconds = countdown_seconds
        self.trigger_once_per_live = trigger_once_per_live
        self.stop_streaming_enabled = stop_streaming_enabled
        self.cancelled_display_seconds = cancelled_display_seconds
        self.would_stop_display_seconds = would_stop_display_seconds
        self._on_stop_intent = on_stop_intent

        self.mode = MODE_NORMAL
        self._started_at: float | None = None
        self._deadline: float | None = None
        self._cancelled_at: float | None = None
        self._finished_at: float | None = None
        self._triggered_live_ids: set[str] = set()
        self._triggered_without_live_id = False
        # 終了ラインを一度割ってから再到達するまで再発動しないための腕木。
        self._armed = True

    def update(
        self,
        *,
        threshold_met: bool,
        live_id: str | None = None,
        now: float | None = None,
    ) -> None:
        current = time.time() if now is None else now

        if self.mode == MODE_CANCELLED:
            if (
                self._cancelled_at is not None
                and current - self._cancelled_at >= self.cancelled_display_seconds
            ):
                self._to_normal()
            else:
                return

        if self.mode == MODE_WOULD_STOP:
            if (
                self._finished_at is not None
                and current - self._finished_at >= self.would_stop_display_seconds
            ):
                self._to_normal()
            else:
                return

        if self.mode == MODE_COUNTDOWN:
            if self._deadline is not None and current >= self._deadline:
                self._finish(current)
            return

        if not threshold_met:
            self._armed = True
            return
        if not self.enabled or not self._armed:
            return
        if self.trigger_once_per_live and self._already_triggered(live_id):
            return
        self._start(current, live_id)

    def cancel(self, *, now: float | None = None) -> bool:
        if self.mode not in (MODE_COUNTDOWN, MODE_WOULD_STOP):
            return False
        current = time.time() if now is None else now
        self.mode = MODE_CANCELLED
        self._started_at = None
        self._deadline = None
        self._finished_at = None
        self._cancelled_at = current
        return True

    def reset(self) -> None:
        """表示状態だけをnormalへ戻す。同一配信の発動履歴は保持する。"""
        self._to_normal()

    def state(self, *, now: float | None = None) -> dict[str, Any]:
        current = time.time() if now is None else now
        remaining = 0
        if self.mode == MODE_COUNTDOWN and self._deadline is not None:
            remaining = max(0, math.ceil(self._deadline - current))
        started_at = None
        if self._started_at is not None:
            started_at = datetime.fromtimestamp(
                self._started_at, timezone.utc
            ).isoformat()
        return {
            "mode": self.mode,
            "countdown_remaining": remaining,
            "countdown_started_at": started_at,
            "can_cancel": self.mode == MODE_COUNTDOWN,
        }

    def _already_triggered(self, live_id: str | None) -> bool:
        if live_id is not None:
            return live_id in self._triggered_live_ids
        return self._triggered_without_live_id

    def _start(self, now: float, live_id: str | None) -> None:
        self.mode = MODE_COUNTDOWN
        self._started_at = now
        self._deadline = now + self.countdown_seconds
        self._cancelled_at = None
        self._finished_at = None
        self._armed = False
        if live_id is not None:
            self._triggered_live_ids.add(live_id)
        else:
            self._triggered_without_live_id = True

    def _finish(self, now: float) -> None:
        self.mode = MODE_WOULD_STOP
        self._deadline = None
        self._finished_at = now
        # v0.3.5: ここにOBS停止処理は実装しない。stop_streaming_enabled が
        # True の場合のみ将来用フックを通知する(本体は何も渡していない)。
        if self.stop_streaming_enabled and self._on_stop_intent is not None:
            self._on_stop_intent()

    def _to_normal(self) -> None:
        self.mode = MODE_NORMAL
        self._started_at = None
        self._deadline = None
        self._cancelled_at = None
        self._finished_at = None
