from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.log_discovery import find_onecomme_log_candidates


class LogDiscoveryTest(unittest.TestCase):
    def test_candidates_are_sorted_by_modified_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_log = root / "old.jsonl"
            new_log = root / "nested" / "new.jsonl"
            ignored = root / "memo.txt"
            new_log.parent.mkdir()
            old_log.write_text("{}", encoding="utf-8")
            new_log.write_text("{}", encoding="utf-8")
            ignored.write_text("{}", encoding="utf-8")
            old_time = 1_700_000_000
            new_time = old_time + 60
            old_log.touch()
            new_log.touch()
            ignored.touch()
            import os

            os.utime(old_log, (old_time, old_time))
            os.utime(new_log, (new_time, new_time))
            os.utime(ignored, (new_time + 60, new_time + 60))

            candidates = find_onecomme_log_candidates(search_dirs=[root])

        self.assertEqual([item.path.name for item in candidates], ["new.jsonl", "old.jsonl"])

    def test_missing_comments_dir_returns_empty_list(self) -> None:
        missing = Path(tempfile.gettempdir()) / "amemiya-missing-onecomme-comments"
        self.assertEqual(find_onecomme_log_candidates(search_dirs=[missing]), [])


if __name__ == "__main__":
    unittest.main()

