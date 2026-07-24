from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Callable


MODE_NORMAL = "normal"
MODE_COUNTDOWN = "countdown"
MODE_CANCELLED = "cancelled"
MODE_WOULD_STOP = "would_stop"
MODE_STOPPING = "stopping"
MODE_STOPPED = "stopped"
MODE_STOP_FAILED = "stop_failed"


class CountdownController:
    """終了ライン到達後のカウントダウン状態を管理する。

    v0.4 の安全仕様:
    - このクラス自体はOBSに触らない。カウントダウン完走時に
      stop_streaming_enabled が True の場合だけ on_stop_intent を呼ぶ。
      実際の停止はアプリ本体が別スレッドで行い、結果を
      report_stop_success / report_stop_failure で返す。
    - stop_streaming_enabled が False なら on_stop_intent は決して
      呼ばれず、would_stop 表示のみで配信は継続する。
    - カウントダウンなしで停止要求が出ることはない
      （stopping へは countdown 完走からしか遷移しない）。
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
        self.stop_result: str | None = None
        self.stop_error: str | None = None
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

        # stopping は停止要求の結果待ち。stopped / stop_failed は配信者が
        # 確認するまで表示を残す（リセットで戻す）。
        if self.mode in (MODE_STOPPING, MODE_STOPPED, MODE_STOP_FAILED):
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
        # stopping以降は要求が出た後なのでキャンセル不可。
        if self.mode not in (MODE_COUNTDOWN, MODE_WOULD_STOP):
            return False
        current = time.time() if now is None else now
        self.mode = MODE_CANCELLED
        self._started_at = None
        self._deadline = None
        self._finished_at = None
        self._cancelled_at = current
        self.stop_result = None
        self.stop_error = None
        return True

    def report_stop_success(self) -> None:
        self.mode = MODE_STOPPED
        self.stop_result = "success"
        self.stop_error = None

    def report_stop_failure(self, error: str) -> None:
        self.mode = MODE_STOP_FAILED
        self.stop_result = "failed"
        self.stop_error = error

    def reset(self) -> None:
        """新しい投票ラウンドを開始できる初期状態へ戻す。"""
        self._to_normal()
        self._armed = True
        self._triggered_live_ids.clear()
        self._triggered_without_live_id = False

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
            "stop_result": self.stop_result,
            "stop_error": self.stop_error,
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
        self._deadline = None
        self._finished_at = now
        # 停止要求はカウントダウン完走時のここからのみ出る。
        # stop_streaming_enabled が False なら表示のみで何も呼ばない。
        if self.stop_streaming_enabled and self._on_stop_intent is not None:
            self.mode = MODE_STOPPING
            self._on_stop_intent()
        else:
            self.mode = MODE_WOULD_STOP

    def _to_normal(self) -> None:
        self.mode = MODE_NORMAL
        self.stop_result = None
        self.stop_error = None
        self._started_at = None
        self._deadline = None
        self._cancelled_at = None
        self._finished_at = None
