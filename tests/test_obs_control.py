from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.obs_control import (
    KIND_AUTH_FAILED,
    KIND_CONNECT_FAILED,
    KIND_DISABLED,
    ObsControlError,
    ObsController,
)


class FakeObsClient:
    def __init__(self, *, streaming: bool = True, stop_error: Exception | None = None):
        self.streaming = streaming
        self.stop_error = stop_error
        self.stop_calls = 0
        self.disconnected = False

    def get_stream_status(self):
        return SimpleNamespace(output_active=self.streaming)

    def stop_stream(self):
        if self.stop_error is not None:
            raise self.stop_error
        self.stop_calls += 1

    def disconnect(self):
        self.disconnected = True


def make_controller(client=None, *, enabled=True, factory=None) -> ObsController:
    if factory is None:
        factory = lambda: client
    return ObsController(
        enabled=enabled,
        host="127.0.0.1",
        port=4455,
        password="",
        client_factory=factory,
    )


class ObsControllerTest(unittest.TestCase):
    def test_disabled_never_connects(self) -> None:
        def factory():
            raise AssertionError("must not connect while disabled")

        controller = make_controller(enabled=False, factory=factory)

        result = controller.test_connection()
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, KIND_DISABLED)

        with self.assertRaises(ObsControlError) as ctx:
            controller.stop_streaming()
        self.assertEqual(ctx.exception.kind, KIND_DISABLED)

    def test_stop_streaming_success(self) -> None:
        client = FakeObsClient(streaming=True)
        controller = make_controller(client)

        message = controller.stop_streaming()

        self.assertEqual(client.stop_calls, 1)
        self.assertIn("停止", message)
        self.assertTrue(client.disconnected)

    def test_stop_skipped_when_not_streaming(self) -> None:
        client = FakeObsClient(streaming=False)
        controller = make_controller(client)

        message = controller.stop_streaming()

        self.assertEqual(client.stop_calls, 0)
        self.assertIn("停止不要", message)

    def test_connect_failure_is_classified(self) -> None:
        def factory():
            raise ConnectionRefusedError("[WinError 10061] refused")

        controller = make_controller(factory=factory)

        result = controller.test_connection()
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, KIND_CONNECT_FAILED)

        with self.assertRaises(ObsControlError) as ctx:
            controller.stop_streaming()
        self.assertEqual(ctx.exception.kind, KIND_CONNECT_FAILED)

    def test_auth_failure_is_classified(self) -> None:
        def factory():
            # obsws-python がパスワード違いのときに投げるメッセージ
            raise Exception(
                "failed to identify client with the server, "
                "please check connection settings"
            )

        controller = make_controller(factory=factory)

        result = controller.test_connection()
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, KIND_AUTH_FAILED)

        with self.assertRaises(ObsControlError) as ctx:
            controller.stop_streaming()
        self.assertEqual(ctx.exception.kind, KIND_AUTH_FAILED)

    def test_stop_request_failure_raises_with_message(self) -> None:
        client = FakeObsClient(streaming=True, stop_error=Exception("boom"))
        controller = make_controller(client)

        with self.assertRaises(ObsControlError) as ctx:
            controller.stop_streaming()
        self.assertIn("boom", str(ctx.exception))
        self.assertTrue(client.disconnected)

    def test_connection_test_reports_streaming_state(self) -> None:
        controller = make_controller(FakeObsClient(streaming=True))
        result = controller.test_connection()
        self.assertTrue(result.ok)
        self.assertTrue(result.streaming)
        self.assertIn("接続成功", result.message)


class ConfigSafetyTest(unittest.TestCase):
    def test_default_config_is_safe(self) -> None:
        import json
        import tempfile

        from end_vote.config import DEFAULT_CONFIG, load_config

        self.assertFalse(DEFAULT_CONFIG["stop_streaming_enabled"])
        self.assertFalse(DEFAULT_CONFIG["obs_websocket_enabled"])
        self.assertEqual(DEFAULT_CONFIG["obs_password"], "")

        # 旧バージョンのconfig（OBSキーなし）を読んでも安全側になる。
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"minimum_votes": 5}), encoding="utf-8"
            )
            config = load_config(path)
        self.assertFalse(config.stop_streaming_enabled)
        self.assertFalse(config.obs_websocket_enabled)
        self.assertEqual(config.obs_host, "127.0.0.1")
        self.assertEqual(config.obs_port, 4455)


if __name__ == "__main__":
    unittest.main()
