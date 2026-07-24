from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.app import countdown_cancel_input_enabled, overlay_should_be_visible


class OverlayVisibilityTest(unittest.TestCase):
    def test_initial_normal_state_is_hidden(self) -> None:
        self.assertFalse(
            overlay_should_be_visible(
                display_enabled=True,
                mode="normal",
                valid_votes=0,
            )
        )

    def test_valid_vote_shows_panel(self) -> None:
        self.assertTrue(
            overlay_should_be_visible(
                display_enabled=True,
                mode="normal",
                valid_votes=1,
            )
        )

    def test_expired_votes_hide_panel(self) -> None:
        self.assertFalse(
            overlay_should_be_visible(
                display_enabled=True,
                mode="normal",
                valid_votes=0,
            )
        )

    def test_countdown_modes_show_even_without_valid_votes(self) -> None:
        for mode in ("countdown", "cancelled", "would_stop", "stopping"):
            with self.subTest(mode=mode):
                self.assertTrue(
                    overlay_should_be_visible(
                        display_enabled=True,
                        mode=mode,
                        valid_votes=0,
                    )
                )

    def test_manual_obs_display_off_hides_everything(self) -> None:
        self.assertFalse(
            overlay_should_be_visible(
                display_enabled=False,
                mode="countdown",
                valid_votes=20,
            )
        )

    def test_cancel_suppression_hides_normal_vote_panel(self) -> None:
        self.assertFalse(
            overlay_should_be_visible(
                display_enabled=True,
                mode="normal",
                valid_votes=20,
                panel_suppressed=True,
            )
        )

    def test_countdown_cancel_input_only_enabled_during_countdown(self) -> None:
        self.assertTrue(countdown_cancel_input_enabled("countdown"))
        for mode in ("normal", "cancelled", "would_stop", "stopping", "stopped", "stop_failed"):
            with self.subTest(mode=mode):
                self.assertFalse(countdown_cancel_input_enabled(mode))


if __name__ == "__main__":
    unittest.main()
