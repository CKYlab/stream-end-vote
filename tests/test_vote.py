from __future__ import annotations

import sys
import time
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from end_vote.vote import VoteCounter, analyze_record, parse_vote_command, voter_id_for


class VoteCounterTest(unittest.TestCase):
    def test_later_vote_overwrites_same_voter(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("twicas", "kick"),
        )

        base = time.time()
        counter.ingest(
            {
                "service": "kick",
                "data": {
                    "message": "!まだ",
                    "userId": "kick-1",
                    "displayName": "viewer",
                },
            },
            now=base,
        )
        counter.ingest(
            {
                "service": "kick",
                "data": {
                    "message": "!終了",
                    "userId": "kick-1",
                    "displayName": "viewer",
                },
            },
            now=base + 1,
        )

        state = counter.state(now=base + 2)
        self.assertEqual(state["end_votes"], 1)
        self.assertEqual(state["continue_votes"], 0)
        self.assertEqual(state["valid_votes"], 1)

    def test_data_id_alone_is_not_used_as_voter_id(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("kick",),
        )

        accepted = counter.ingest(
            {
                "service": "kick",
                "data": {
                    "message": "!寝ろ",
                    "id": "comment-123",
                },
            }
        )
        state = counter.state()
        self.assertFalse(accepted)
        self.assertEqual(state["valid_votes"], 0)
        self.assertIsNone(
            voter_id_for(
                {
                    "service": "kick",
                    "data": {
                        "id": "comment-123",
                    },
                },
                "kick",
            )
        )

    def test_full_width_exclamation_end_command(self) -> None:
        self.assertEqual(parse_vote_command("！寝ろ"), "end")

    def test_analyze_record_reports_ignored_reason(self) -> None:
        analysis = analyze_record(
            {
                "service": "youtube",
                "data": {
                    "message": "!寝ろ",
                    "userId": "viewer-1",
                    "displayName": "viewer",
                },
            },
            supported_services=("twicas", "kick", "twitch"),
        )
        self.assertEqual(analysis.result, "ignored")
        self.assertEqual(analysis.reason, "unsupported_service")

    def test_twicas_anonymous_uses_live_id_and_number(self) -> None:
        voter_id, _ = voter_id_for(
            {
                "service": "twicas",
                "data": {
                    "liveId": "live-1",
                    "displayName": "匿名コメント#7",
                },
            },
            "twicas",
        )
        self.assertEqual(voter_id, "twicas:anonymous:live-1:匿名コメント#7")

    def test_twicas_anonymous_different_numbers_are_different_votes(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("twicas",),
        )

        base = time.time()
        for index in (1, 2):
            counter.ingest(
                {
                    "service": "twicas",
                    "data": {
                        "comment": "!寝ろ",
                        "liveId": "live-1",
                        "userId": "c:tw1",
                        "displayName": f"匿名コメント#{index}",
                    },
                },
                now=base + index,
            )

        state = counter.state(now=base + 3)
        self.assertEqual(state["end_votes"], 2)
        self.assertEqual(state["valid_votes"], 2)

    def test_twicas_anonymous_same_number_overwrites_vote(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("twicas",),
        )

        base = time.time()
        counter.ingest(
            {
                "service": "twicas",
                "data": {
                    "comment": "!寝ろ",
                    "liveId": "live-1",
                    "userId": "c:tw1",
                    "displayName": "匿名コメント#7",
                },
            },
            now=base,
        )
        counter.ingest(
            {
                "service": "twicas",
                "data": {
                    "comment": "!続行",
                    "liveId": "live-1",
                    "userId": "c:tw1",
                    "displayName": "匿名コメント#7",
                },
            },
            now=base + 1,
        )

        state = counter.state(now=base + 2)
        self.assertEqual(state["end_votes"], 0)
        self.assertEqual(state["continue_votes"], 1)
        self.assertEqual(state["valid_votes"], 1)

    def test_tail_processing_uses_read_time_not_record_timestamp(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("kick",),
        )

        read_at = time.time()
        counter.process(
            {
                "service": "kick",
                "data": {
                    "message": "!寝ろ",
                    "userId": "viewer-1",
                    "displayName": "viewer",
                    "timestamp": read_at - 3600,
                },
            },
            now=read_at,
            use_record_timestamp=False,
        )

        state = counter.state(now=read_at + 1)
        self.assertEqual(state["end_votes"], 1)
        self.assertEqual(state["valid_votes"], 1)

    def test_vote_expires_to_zero_when_time_passes_without_new_comments(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("kick",),
        )

        base = time.time()
        counter.process(
            {
                "service": "kick",
                "data": {
                    "message": "!寝ろ",
                    "userId": "viewer-1",
                    "displayName": "viewer",
                },
            },
            now=base,
            use_record_timestamp=False,
        )

        self.assertEqual(counter.state(now=base + 1)["valid_votes"], 1)
        expired_state = counter.state(now=base + 181)
        self.assertEqual(expired_state["end_votes"], 0)
        self.assertEqual(expired_state["continue_votes"], 0)
        self.assertEqual(expired_state["valid_votes"], 0)

    def test_vote_round_advances_when_old_votes_expire_before_new_vote(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=20,
            end_rate_threshold=0.7,
            supported_services=("kick",),
        )
        base = time.time()
        counter.process(
            {
                "service": "kick",
                "data": {
                    "message": "!寝ろ",
                    "userId": "old-viewer",
                    "displayName": "old viewer",
                },
            },
            now=base,
            use_record_timestamp=False,
        )
        initial_round = counter.round_id

        counter.process(
            {
                "service": "kick",
                "data": {
                    "message": "!寝ろ",
                    "userId": "new-viewer",
                    "displayName": "new viewer",
                },
            },
            now=base + 181,
            use_record_timestamp=False,
        )

        self.assertEqual(counter.round_id, initial_round + 1)
        self.assertEqual(counter.state(now=base + 181)["valid_votes"], 1)

    def test_rolling_window_prunes_old_votes(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("twicas", "kick"),
        )

        base = time.time()
        counter.ingest(
            {
                "service": "twicas",
                "data": {
                    "comment": "!寝ろ",
                    "userId": "old",
                    "displayName": "old",
                },
            },
            now=base,
        )
        state = counter.state(now=base + 181)
        self.assertEqual(state["valid_votes"], 0)

    def test_twitch_can_use_screen_name_identity(self) -> None:
        counter = VoteCounter(
            voting_window_seconds=180,
            minimum_votes=1,
            end_rate_threshold=0.6,
            supported_services=("twitch",),
        )

        accepted = counter.ingest(
            {
                "service": "twitch",
                "data": {
                    "message": "!続行",
                    "screenName": "twitch_viewer",
                    "displayName": "Twitch Viewer",
                },
            }
        )
        state = counter.state()
        self.assertTrue(accepted)
        self.assertEqual(state["continue_votes"], 1)


if __name__ == "__main__":
    unittest.main()
