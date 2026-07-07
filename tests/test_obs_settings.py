from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.config import DEFAULT_CONFIG
from end_vote.obs_settings import (
    ObsSettings,
    save_obs_settings,
    test_obs_connection_from_settings as run_obs_connection_test,
    validate_obs_port,
)


class ObsSettingsTest(unittest.TestCase):
    def test_default_files_keep_obs_stop_disabled(self) -> None:
        self.assertFalse(DEFAULT_CONFIG["obs_websocket_enabled"])
        self.assertFalse(DEFAULT_CONFIG["stop_streaming_enabled"])

        for name in ("config.json", "config.sample.json"):
            config = json.loads((ROOT / name).read_text(encoding="utf-8"))
            self.assertFalse(config["obs_websocket_enabled"], name)
            self.assertFalse(config["stop_streaming_enabled"], name)

    def test_save_obs_settings_updates_config_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False),
                encoding="utf-8",
            )

            save_obs_settings(
                path,
                ObsSettings(
                    obs_websocket_enabled=True,
                    stop_streaming_enabled=False,
                    obs_host="192.0.2.10",
                    obs_port=4456,
                    obs_password="secret",
                ),
            )

            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(updated["obs_websocket_enabled"])
            self.assertFalse(updated["stop_streaming_enabled"])
            self.assertEqual(updated["obs_host"], "192.0.2.10")
            self.assertEqual(updated["obs_port"], 4456)
            self.assertEqual(updated["obs_password"], "secret")

    def test_invalid_port_is_rejected(self) -> None:
        for value in ("", "abc", "0", "65536"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_obs_port(value)

    def test_connection_test_off_does_not_connect(self) -> None:
        settings = ObsSettings(
            obs_websocket_enabled=False,
            stop_streaming_enabled=False,
            obs_host="127.0.0.1",
            obs_port=4455,
            obs_password="",
        )

        result = run_obs_connection_test(
            settings,
            controller_factory=lambda _settings: self.fail("must not connect"),
        )

        self.assertFalse(result.ok)
        self.assertIn("OFF", result.message)

    def test_connection_test_failure_does_not_raise(self) -> None:
        settings = ObsSettings(
            obs_websocket_enabled=True,
            stop_streaming_enabled=False,
            obs_host="127.0.0.1",
            obs_port=4455,
            obs_password="",
        )

        def broken_factory(_settings: ObsSettings):
            raise ConnectionRefusedError("refused")

        result = run_obs_connection_test(
            settings,
            controller_factory=broken_factory,
        )

        self.assertFalse(result.ok)
        self.assertIn("refused", result.message)


if __name__ == "__main__":
    unittest.main()
