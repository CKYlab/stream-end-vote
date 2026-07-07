from __future__ import annotations

import sys
import time
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.countdown import (
    MODE_CANCELLED,
    MODE_COUNTDOWN,
    MODE_NORMAL,
    MODE_WOULD_STOP,
    CountdownController,
)


def make_controller(**overrides) -> CountdownController:
    params = {
        "enabled": True,
        "countdown_seconds": 30,
        "trigger_once_per_live": True,
        "stop_streaming_enabled": False,
    }
    params.update(overrides)
    return CountdownController(**params)


class CountdownControllerTest(unittest.TestCase):
    def test_below_threshold_does_not_start_countdown(self) -> None:
        controller = make_controller()
        base = time.time()

        controller.update(threshold_met=False, live_id="live-1", now=base)

        self.assertEqual(controller.mode, MODE_NORMAL)
        state = controller.state(now=base)
        self.assertEqual(state["mode"], "normal")
        self.assertEqual(state["countdown_remaining"], 0)
        self.assertIsNone(state["countdown_started_at"])
        self.assertFalse(state["can_cancel"])

    def test_threshold_reached_starts_countdown(self) -> None:
        controller = make_controller()
        base = time.time()

        controller.update(threshold_met=True, live_id="live-1", now=base)

        self.assertEqual(controller.mode, MODE_COUNTDOWN)
        state = controller.state(now=base)
        self.assertEqual(state["mode"], "countdown")
        self.assertEqual(state["countdown_remaining"], 30)
        self.assertIsNotNone(state["countdown_started_at"])
        self.assertTrue(state["can_cancel"])

    def test_countdown_disabled_never_starts(self) -> None:
        controller = make_controller(enabled=False)
        base = time.time()

        controller.update(threshold_met=True, live_id="live-1", now=base)

        self.assertEqual(controller.mode, MODE_NORMAL)

    def test_cancel_moves_to_cancelled_then_back_to_normal(self) -> None:
        controller = make_controller(cancelled_display_seconds=5.0)
        base = time.time()
        controller.update(threshold_met=True, live_id="live-1", now=base)

        self.assertTrue(controller.cancel(now=base + 10))
        self.assertEqual(controller.mode, MODE_CANCELLED)
        state = controller.state(now=base + 10)
        self.assertEqual(state["mode"], "cancelled")
        self.assertFalse(state["can_cancel"])
        self.assertEqual(state["countdown_remaining"], 0)

        # 表示秒数の間はcancelledのまま。
        controller.update(threshold_met=True, live_id="live-1", now=base + 12)
        self.assertEqual(controller.mode, MODE_CANCELLED)

        # 表示秒数を過ぎるとnormalへ戻る。
        controller.update(threshold_met=True, live_id="live-1", now=base + 16)
        self.assertEqual(controller.mode, MODE_NORMAL)

    def test_stop_hook_not_called_when_stop_streaming_disabled(self) -> None:
        calls: list[str] = []
        controller = make_controller(
            stop_streaming_enabled=False,
            on_stop_intent=lambda: calls.append("stop"),
        )
        base = time.time()
        controller.update(threshold_met=True, live_id="live-1", now=base)

        controller.update(threshold_met=True, live_id="live-1", now=base + 31)

        self.assertEqual(controller.mode, MODE_WOULD_STOP)
        self.assertEqual(calls, [])
        state = controller.state(now=base + 31)
        self.assertEqual(state["mode"], "would_stop")
        self.assertFalse(state["can_cancel"])

    def test_trigger_once_per_live_does_not_retrigger_same_live(self) -> None:
        controller = make_controller(trigger_once_per_live=True)
        base = time.time()
        controller.update(threshold_met=True, live_id="live-1", now=base)
        controller.cancel(now=base + 5)

        # cancelled表示が終わり、終了ラインを一度割ってから再到達しても、
        # 同じliveIdでは再発動しない。
        controller.update(threshold_met=False, live_id="live-1", now=base + 20)
        self.assertEqual(controller.mode, MODE_NORMAL)
        controller.update(threshold_met=True, live_id="live-1", now=base + 30)
        self.assertEqual(controller.mode, MODE_NORMAL)

        # 別のliveIdなら発動する。
        controller.update(threshold_met=False, live_id="live-2", now=base + 40)
        controller.update(threshold_met=True, live_id="live-2", now=base + 41)
        self.assertEqual(controller.mode, MODE_COUNTDOWN)

    def test_trigger_once_per_live_false_can_retrigger_after_rearm(self) -> None:
        controller = make_controller(trigger_once_per_live=False)
        base = time.time()
        controller.update(threshold_met=True, live_id="live-1", now=base)
        controller.cancel(now=base + 5)

        # 終了ラインを割らない限りは再発動しない。
        controller.update(threshold_met=True, live_id="live-1", now=base + 20)
        self.assertEqual(controller.mode, MODE_NORMAL)

        # 一度割ってから再到達すると再発動する。
        controller.update(threshold_met=False, live_id="live-1", now=base + 30)
        controller.update(threshold_met=True, live_id="live-1", now=base + 31)
        self.assertEqual(controller.mode, MODE_COUNTDOWN)

    def test_trigger_once_without_live_id_uses_session_flag(self) -> None:
        controller = make_controller(trigger_once_per_live=True)
        base = time.time()
        controller.update(threshold_met=True, live_id=None, now=base)
        controller.cancel(now=base + 5)

        controller.update(threshold_met=False, live_id=None, now=base + 20)
        controller.update(threshold_met=True, live_id=None, now=base + 30)
        self.assertEqual(controller.mode, MODE_NORMAL)

    def test_countdown_remaining_counts_down(self) -> None:
        controller = make_controller()
        base = time.time()
        controller.update(threshold_met=True, live_id="live-1", now=base)

        controller.update(threshold_met=True, live_id="live-1", now=base + 12)
        state = controller.state(now=base + 12)
        self.assertEqual(state["mode"], "countdown")
        self.assertEqual(state["countdown_remaining"], 18)


if __name__ == "__main__":
    unittest.main()
