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
            self.assertFalse(config["stop_streaming_enabled"])
            self.assertFalse(config["obs_websocket_enabled"])
            self.assertEqual(config["obs_password"], "")
            self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["minimum_votes"], 5)


if __name__ == "__main__":
    unittest.main()
