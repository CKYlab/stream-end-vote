from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import make_release


class ReleaseDefaultsTest(unittest.TestCase):
    def test_public_release_name_and_internal_executable_name(self) -> None:
        self.assertEqual(make_release.ZIP_PATH.name, "配信終了投票くん_v1.0.0.zip")
        self.assertEqual(make_release.BUILT_EXE_NAME, "stream-end-vote.exe")
        self.assertIn("LICENSE", make_release.EXPECTED_RELEASE_NAMES)

    def test_every_forbidden_public_identifier_is_rejected(self) -> None:
        cases = (
            "AMEMIYA", "雨宮", "chobitsuki", "CHiKA",
            "ちか", "CodexTest", "C:\\Users", "D:\\",
        )
        for forbidden in cases:
            with self.subTest(forbidden=forbidden), tempfile.TemporaryDirectory() as directory:
                release = Path(directory)
                (release / "overlay.html").write_text(forbidden, encoding="utf-8")
                with patch.object(make_release, "RELEASE", release):
                    with self.assertRaises(RuntimeError):
                        make_release.verify_no_private_text()

    def test_release_starts_with_twenty_even_when_development_setting_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "config.json"
            source.write_text(json.dumps({"minimum_votes": 5}), encoding="utf-8")
            config_path = root / "release-config.json"
            overlay_path = root / "overlay_state.json"
            with patch.object(make_release, "ROOT", root):
                make_release.write_release_config(config_path)
                make_release.write_release_overlay_state(overlay_path)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            self.assertEqual(config["minimum_votes"], 20)
            self.assertEqual(overlay["minimum_votes"], 20)
            self.assertFalse(overlay["visible"])
            self.assertEqual(config["log_file_path"], "")
            self.assertFalse(config["stop_streaming_enabled"])
            self.assertFalse(config["obs_websocket_enabled"])
            self.assertEqual(config["obs_password"], "")
            self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["minimum_votes"], 5)


if __name__ == "__main__":
    unittest.main()
