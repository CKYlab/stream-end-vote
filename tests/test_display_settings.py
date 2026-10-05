from test_vote_settings import VoteSettingsFixture
from end_vote.display_settings import DISPLAY_DEFAULTS
from end_vote.config import load_config
from test_vote_settings import find_widget
import tkinter as tk
from unittest.mock import Mock, patch


class DisplaySettingsTest(VoteSettingsFixture):
    def test_preview_is_read_only_and_unsaved(self):
        self.vote(1)
        original = self.config_path.read_bytes()
        before = self.app.countdown.state()
        self.app.obs = Mock()
        with patch.object(self.app.countdown, "update", side_effect=AssertionError("preview must not update countdown")):
            for mode in ("vote", "countdown"):
                self.app._set_display_preview(mode, dict(DISPLAY_DEFAULTS, vote_panel_x=120))
                self.assertEqual(self.overlay()["preview_mode"], mode)
                self.assertEqual(self.overlay()["vote_panel_x"], 120)
                self.assertEqual(self.overlay()["valid_votes"], 1)
                self.assertEqual(self.overlay()["mode"], "normal")
        self.assertEqual(self.app.countdown.state(), before)
        self.assertEqual(self.app.obs.mock_calls, [])
        self.assertEqual(self.config_path.read_bytes(), original)
        self.app._set_display_preview("none")
        self.assertEqual(self.overlay()["preview_mode"], "none")
        self.assertEqual(self.overlay()["vote_panel_x"], 0)

    def test_save_ends_preview(self):
        self.app._set_display_preview("countdown", DISPLAY_DEFAULTS)
        self.app._save_display_settings(dict(DISPLAY_DEFAULTS, countdown_y=50))
        self.assertEqual(self.overlay()["preview_mode"], "none")
        self.assertEqual(self.overlay()["countdown_y"], 50)

    def test_app_close_ends_preview(self):
        self.app._set_display_preview("vote", DISPLAY_DEFAULTS)
        self.app.root = Mock()
        self.app._stop_worker = Mock()
        self.app._close()
        self.assertEqual(self.overlay()["preview_mode"], "none")

    def test_old_config_uses_current_layout(self):
        for key, value in DISPLAY_DEFAULTS.items():
            self.assertEqual(getattr(self.app.config, key), value)

    def test_save_updates_config_and_overlay(self):
        values = dict(DISPLAY_DEFAULTS, vote_panel_position="top-left", countdown_position="bottom", vote_panel_x="-500", countdown_y="+500")
        self.app._save_display_settings(values)
        for key, value in dict(values, vote_panel_x=-500, countdown_y=500).items():
            self.assertEqual(getattr(load_config(self.config_path), key), value)
            self.assertEqual(self.overlay()[key], value)

    def test_invalid_input_does_not_write(self):
        original = self.config_path.read_bytes()
        for value in ("", "1.5", "abc", "501", "-501", " 1", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.app._save_display_settings(dict(DISPLAY_DEFAULTS, vote_panel_x=value))
            self.assertEqual(self.config_path.read_bytes(), original)

    def test_restore_defaults(self):
        self.app._save_display_settings(dict(DISPLAY_DEFAULTS, countdown_x=200))
        self.app._save_display_settings(DISPLAY_DEFAULTS)
        self.assertEqual(self.overlay()["countdown_x"], 0)

    def test_save_keeps_countdown_and_votes(self):
        for index in range(20):
            self.vote(index)
        before = self.app._current_state()
        self.app._save_display_settings(dict(DISPLAY_DEFAULTS, vote_panel_x=50))
        after = self.overlay()
        self.assertEqual(after["mode"], "countdown")
        self.assertEqual(after["countdown_started_at"], before["countdown_started_at"])
        self.assertEqual(after["valid_votes"], 20)


class DisplayDialogTest(VoteSettingsFixture):
    def test_preview_updates_before_save_and_cancel_restores(self):
        dialog = self.open_dialog()
        find_widget(dialog, tk.Button, "投票パネルをプレビュー").invoke()
        entry = find_widget(dialog, tk.Spinbox)
        entry.delete(0, "end")
        entry.insert(0, "123")
        self.assertEqual(self.overlay()["vote_panel_x"], 123)
        self.assertEqual(load_config(self.config_path).vote_panel_x, 0)
        find_widget(dialog, tk.Button, "キャンセル").invoke()
        self.assertEqual(self.overlay()["preview_mode"], "none")
        self.assertEqual(self.overlay()["vote_panel_x"], 0)

    def test_window_close_ends_preview(self):
        dialog = self.open_dialog()
        find_widget(dialog, tk.Button, "カウントダウンをプレビュー").invoke()
        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.overlay()["preview_mode"], "none")

    def setUp(self):
        super().setUp()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app.root = self.root

    def open_dialog(self):
        self.app._open_display_settings()
        return next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))

    def test_dialog_save_shows_confirmation_and_updates_overlay(self):
        dialog = self.open_dialog()
        find_widget(dialog, tk.Button, "保存").invoke()
        self.assertEqual(self.overlay()["vote_panel_position"], "bottom-right")

    def test_restore_default_requires_save(self):
        self.app._save_display_settings(dict(DISPLAY_DEFAULTS, countdown_x=100))
        dialog = self.open_dialog()
        find_widget(dialog, tk.Button, "初期値に戻す").invoke()
        self.assertEqual(load_config(self.config_path).countdown_x, 100)
        find_widget(dialog, tk.Button, "保存").invoke()
        self.assertEqual(self.overlay()["countdown_x"], 0)

    def test_cancel_discards_input(self):
        dialog = self.open_dialog()
        find_widget(dialog, tk.Button, "キャンセル").invoke()
        self.assertFalse(dialog.winfo_exists())

    def test_invalid_input_does_not_save_and_shows_error(self):
        dialog = self.open_dialog()
        entry = find_widget(dialog, tk.Spinbox)
        entry.delete(0, "end")
        entry.insert(0, "501")
        find_widget(dialog, tk.Button, "保存").invoke()
        self.assertEqual(load_config(self.config_path).vote_panel_x, 0)
