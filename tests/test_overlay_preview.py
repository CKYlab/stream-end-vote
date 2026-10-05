import pathlib
import subprocess
import unittest


class OverlayPreviewTest(unittest.TestCase):
    def test_preview_render_and_return_to_hidden_normal_state(self):
        script = pathlib.Path(__file__).with_name("overlay_preview.cjs")
        result = subprocess.run(["node", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
