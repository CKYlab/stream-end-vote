from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.app import EndVoteApp
from end_vote.countdown import MODE_CANCELLED, MODE_COUNTDOWN, CountdownController
from end_vote.vote import VoteCounter


def make_app(state_path: Path) -> EndVoteApp:
    app = EndVoteApp.__new__(EndVoteApp)
    app.config = SimpleNamespace(
        overlay_state_path=state_path,
        obs_websocket_enabled=False,
        stop_streaming_enabled=False,
    )
    app.counter = VoteCounter(
        voting_window_seconds=180,
        minimum_votes=20,
        end_rate_threshold=0.7,
        supported_services=("kick",),
    )
    app.countdown = CountdownController(
        enabled=True,
        countdown_seconds=30,
        trigger_once_per_live=True,
        stop_streaming_enabled=False,
    )
    app.current_live_id = "live-1"
    app.obs_connected = None
    app.panel_suppressed_until_next_vote = False
    app.vote_round_id = app.counter.round_id
    app.last_overlay_snapshot = None
    app._refresh_labels = lambda state=None: None
    app._sync_countdown_cancel_controls = lambda active: None
    return app


def cast_twenty_votes(app: EndVoteApp, *, round_number: int) -> None:
    base = time.time()
    for index in range(20):
        choice = "!寝ろ" if index < 15 else "!続行"
        app.counter.process(
            {
                "service": "kick",
                "data": {
                    "message": choice,
                    "userId": f"round-{round_number}-viewer-{index}",
                    "displayName": f"viewer {index}",
                },
            },
            now=base + index / 100,
            use_record_timestamp=False,
        )


class AppCountdownRoundTest(unittest.TestCase):
    def test_countdown_can_restart_after_cancel_and_vote_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = make_app(Path(directory) / "overlay_state.json")
            cast_twenty_votes(app, round_number=1)
            self.assertEqual(app._current_state()["end_rate"], 0.75)
            self.assertEqual(app.countdown.mode, MODE_COUNTDOWN)

            app._cancel_countdown()
            app._reset()
            cast_twenty_votes(app, round_number=2)
            state = app._current_state()

            self.assertEqual(app.countdown.mode, MODE_COUNTDOWN)
            self.assertEqual(state["valid_votes"], 20)
            self.assertEqual(state["end_rate"], 0.75)
            self.assertTrue(state["can_cancel"])

    def test_cancel_does_not_immediately_restart_same_vote_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "overlay_state.json"
            app = make_app(state_path)
            cast_twenty_votes(app, round_number=1)
            app._current_state()

            app._cancel_countdown()
            state = app._current_state()
            overlay = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(app.countdown.mode, MODE_CANCELLED)
            self.assertEqual(state["countdown_remaining"], 0)
            self.assertIsNone(state["countdown_started_at"])
            self.assertFalse(state["can_cancel"])
            self.assertEqual(overlay["mode"], MODE_CANCELLED)

    def test_vote_reset_clears_cancel_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "overlay_state.json"
            app = make_app(state_path)
            cast_twenty_votes(app, round_number=1)
            app._current_state()
            app._cancel_countdown()

            app._reset()
            reset_overlay = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertFalse(app.panel_suppressed_until_next_vote)
            self.assertEqual(reset_overlay["mode"], "normal")
            self.assertEqual(reset_overlay["countdown_remaining"], 0)
            self.assertIsNone(reset_overlay["countdown_started_at"])
            self.assertFalse(reset_overlay["can_cancel"])
            self.assertIsNone(reset_overlay["stop_result"])
            self.assertIsNone(reset_overlay["stop_error"])


if __name__ == "__main__":
    unittest.main()
