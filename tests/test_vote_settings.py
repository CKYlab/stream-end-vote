from __future__ import annotations

import json
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.app import EndVoteApp
from end_vote.app import VoteSettingsRefreshError
from end_vote.config import load_config
from end_vote.countdown import CountdownController


class VoteSettingsFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / "config.json"
        self.app = EndVoteApp.__new__(EndVoteApp)
        self.app.config_path = self.config_path
        self.app.config = load_config(self.config_path)
        self.app.counter = self.app._create_counter()
        self.app.countdown = CountdownController(
            enabled=True, countdown_seconds=30,
            trigger_once_per_live=True, stop_streaming_enabled=False,
        )
        self.app.current_live_id = "live-1"
        self.app.obs_connected = None
        self.app.panel_suppressed_until_next_vote = False
        self.app.vote_round_id = self.app.counter.round_id
        self.app.last_overlay_snapshot = None
        # Only the widget rendering is omitted; config, counter and JSON are real.
        self.app._refresh_labels = lambda state=None: None
        self.app._sync_countdown_cancel_controls = lambda active: None

    def vote(self, index: int, choice: str = "!寝ろ") -> None:
        self.app.counter.process(
            {"service": "kick", "data": {"userId": str(index), "comment": choice}},
            use_record_timestamp=False,
        )

    def overlay(self) -> dict:
        return json.loads(self.app.config.overlay_state_path.read_text(encoding="utf-8"))


class VoteSettingsTest(VoteSettingsFixture):
    def test_minimum_votes_defaults_to_twenty(self) -> None:
        self.app._write_state()
        self.assertEqual(load_config(self.config_path).minimum_votes, 20)
        self.assertEqual(self.overlay()["minimum_votes"], 20)

    def test_save_updates_config_and_overlay_without_clearing_votes(self) -> None:
        for index in range(5):
            self.vote(index, "!寝ろ" if index < 4 else "!まだ")
        self.assertFalse(self.app._current_state()["threshold_met"])

        self.app._save_vote_settings("5")

        self.assertEqual(load_config(self.config_path).minimum_votes, 5)
        self.assertEqual(self.app.config.minimum_votes, 5)
        state = self.overlay()
        self.assertEqual(state["minimum_votes"], 5)
        self.assertEqual(state["valid_votes"], 5)
        self.assertEqual(state["end_rate"], 0.8)
        self.assertTrue(state["threshold_met"])
        self.assertEqual(state["mode"], "countdown")

    def test_invalid_values_cannot_be_saved(self) -> None:
        self.app._write_state()
        original_config = self.config_path.read_bytes()
        original_overlay = self.app.config.overlay_state_path.read_bytes()
        for value in ("0", "-1", "", " ", "1.5", "5.0", "abc", "1000", "+5", "1e2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.app._save_vote_settings(value)
                self.assertEqual(self.config_path.read_bytes(), original_config)
                self.assertEqual(self.app.config.overlay_state_path.read_bytes(), original_overlay)
                self.assertEqual(self.app.counter.minimum_votes, 20)

    def test_boundaries_can_be_saved(self) -> None:
        for value in ("1", "999"):
            with self.subTest(value=value):
                self.app._save_vote_settings(value)
                self.assertEqual(load_config(self.config_path).minimum_votes, int(value))

    def test_five_votes_required_and_seventy_percent_rule_unchanged(self) -> None:
        self.app._save_vote_settings("5")
        for index in range(4):
            self.vote(index, "!寝ろ" if index < 3 else "!まだ")
        self.assertFalse(self.app._current_state()["threshold_met"])
        self.vote(4, "!まだ")
        self.assertFalse(self.app._current_state()["threshold_met"])
        self.vote(4, "!寝ろ")
        state = self.app._current_state()
        self.assertEqual(state["valid_votes"], 5)
        self.assertTrue(state["threshold_met"])
        self.assertEqual(state["mode"], "countdown")

    def test_save_preserves_cancel_suppression(self) -> None:
        self.app._save_vote_settings("5")
        for index in range(5):
            self.vote(index)
        self.app._current_state()
        self.app._cancel_countdown()
        self.app.countdown.cancelled_display_seconds = 0

        self.app._save_vote_settings("1")

        self.assertEqual(self.overlay()["mode"], "normal")
        self.assertFalse(self.overlay()["can_cancel"])
        self.assertEqual(self.overlay()["valid_votes"], 5)
        self.assertTrue(self.app.panel_suppressed_until_next_vote)

    def test_save_preserves_active_countdown(self) -> None:
        self.app._save_vote_settings("1")
        self.vote(1)
        started_at = self.app._current_state()["countdown_started_at"]

        self.app._save_vote_settings("999")

        self.assertEqual(self.overlay()["mode"], "countdown")
        self.assertEqual(self.overlay()["countdown_started_at"], started_at)

    def test_failed_config_write_does_not_apply_setting(self) -> None:
        self.app.config_path = Path(self.directory.name) / "missing" / "config.json"
        with self.assertRaises(OSError):
            self.app._save_vote_settings("5")
        self.assertEqual(self.app.config.minimum_votes, 20)
        self.assertEqual(self.app.counter.minimum_votes, 20)

    def test_overlay_write_failure_reports_setting_was_saved(self) -> None:
        blocker = Path(self.directory.name) / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        self.app.config = self.app.config.__class__(
            **{**self.app.config.__dict__, "overlay_state_path": blocker / "state.json"}
        )
        with self.assertRaisesRegex(VoteSettingsRefreshError, "設定は保存しました"):
            self.app._save_vote_settings("5")
        self.assertEqual(load_config(self.config_path).minimum_votes, 5)
        self.assertEqual(self.app.config.minimum_votes, 5)
        self.assertEqual(self.app.counter.minimum_votes, 5)


def find_widget(parent: tk.Misc, widget_type: type, text: str | None = None):
    for widget in parent.winfo_children():
        if isinstance(widget, widget_type) and (text is None or widget.cget("text") == text):
            return widget
        found = find_widget(widget, widget_type, text)
        if found is not None:
            return found
    return None


class VoteSettingsDialogTest(VoteSettingsFixture):
    def setUp(self) -> None:
        super().setUp()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app.root = self.root

    def open_dialog(self):
        self.app._open_vote_settings()
        return next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))

    def test_dialog_save_shows_confirmation_and_updates_overlay(self) -> None:
        dialog = self.open_dialog()
        entry = find_widget(dialog, tk.Entry)
        self.assertEqual(entry.get(), "20")
        entry.delete(0, "end")
        entry.insert(0, "5")
        find_widget(dialog, tk.Button, "保存").invoke()
        self.assertEqual(load_config(self.config_path).minimum_votes, 5)
        self.assertEqual(self.overlay()["minimum_votes"], 5)
        labels = [w for w in dialog.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
        self.assertTrue(any("保存しました" in str(w.cget("text")) for w in labels))

    def test_restore_default_requires_save_and_sets_twenty(self) -> None:
        self.app._save_vote_settings("5")
        dialog = self.open_dialog()
        self.assertEqual(find_widget(dialog, tk.Entry).get(), "5")
        find_widget(dialog, tk.Button, "初期値に戻す").invoke()
        self.assertEqual(find_widget(dialog, tk.Entry).get(), "20")
        self.assertEqual(load_config(self.config_path).minimum_votes, 5)
        find_widget(dialog, tk.Button, "保存").invoke()
        self.assertEqual(load_config(self.config_path).minimum_votes, 20)
        self.assertEqual(self.overlay()["minimum_votes"], 20)

    def test_cancel_discards_input(self) -> None:
        dialog = self.open_dialog()
        entry = find_widget(dialog, tk.Entry)
        entry.delete(0, "end")
        entry.insert(0, "5")
        find_widget(dialog, tk.Button, "キャンセル").invoke()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(load_config(self.config_path).minimum_votes, 20)

    def test_invalid_input_does_not_save_and_shows_error(self) -> None:
        dialog = self.open_dialog()
        entry = find_widget(dialog, tk.Entry)
        for value in ("0", "-1", "", "1.5", "abc", "1000"):
            with self.subTest(value=value):
                entry.delete(0, "end")
                entry.insert(0, value)
                find_widget(dialog, tk.Button, "保存").invoke()
                self.assertEqual(load_config(self.config_path).minimum_votes, 20)
                labels = [w for w in dialog.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
                self.assertTrue(any("1〜999" in str(w.cget("text")) for w in labels))


if __name__ == "__main__":
    unittest.main()
