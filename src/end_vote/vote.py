from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from typing import Any


END_COMMANDS = ("!寝ろ", "!終了")
CONTINUE_COMMANDS = ("!続行", "!まだ")
ANONYMOUS_NAME_RE = re.compile(r"匿名コメント#?\d+")


@dataclass
class Vote:
    voter_id: str
    choice: str
    timestamp: float
    display_name: str
    service: str


@dataclass(frozen=True)
class VoteAnalysis:
    service: str
    display_name: str
    comment: str
    voter_id: str
    result: str
    reason: str


def extract_comment(record: dict[str, Any]) -> str:
    data = _dict_value(record, "data")
    candidates = (
        _string_value(data, "comment"),
        _string_value(data, "message"),
        _string_value(data, "text"),
        _string_value(record, "comment"),
        _string_value(record, "message"),
        _string_value(record, "text"),
    )
    return next((value for value in candidates if value), "")


def extract_display_name(record: dict[str, Any]) -> str:
    data = _dict_value(record, "data")
    return (
        _string_value(data, "displayName")
        or _string_value(data, "name")
        or _string_value(data, "userName")
        or _string_value(record, "displayName")
        or _string_value(record, "name")
        or "unknown"
    )


def extract_service(record: dict[str, Any]) -> str:
    data = _dict_value(record, "data")
    raw = (
        _string_value(data, "service")
        or _string_value(data, "platform")
        or _string_value(record, "service")
        or _string_value(record, "platform")
    )
    return normalize_service(raw)


def normalize_service(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "twitcasting": "twicas",
        "twitcasting.tv": "twicas",
        "twicas": "twicas",
        "kick": "kick",
        "twitch": "twitch",
    }
    return aliases.get(normalized, normalized)


def extract_live_id(record: dict[str, Any]) -> str | None:
    data = _dict_value(record, "data")
    live_id = (
        _string_value(data, "liveId")
        or _string_value(data, "live_id")
        or _string_value(record, "liveId")
        or _string_value(record, "live_id")
    )
    return live_id or None


def extract_timestamp(record: dict[str, Any], now: float | None = None) -> float:
    data = _dict_value(record, "data")
    for source in (data, record):
        for key in ("timestamp", "time", "createdAt", "created_at", "date"):
            value = source.get(key)
            parsed = _parse_timestamp(value)
            if parsed is not None:
                return parsed
    return time.time() if now is None else now


def parse_vote_command(comment: str) -> str | None:
    normalized = comment.strip().replace("！", "!")
    if any(normalized.startswith(command) for command in END_COMMANDS):
        return "end"
    if any(normalized.startswith(command) for command in CONTINUE_COMMANDS):
        return "continue"
    return None


def voter_id_for(record: dict[str, Any], service: str) -> tuple[str, str] | None:
    data = _dict_value(record, "data")
    display_name = extract_display_name(record)

    if service == "twicas" and ANONYMOUS_NAME_RE.fullmatch(display_name):
        live_id = _string_value(data, "liveId") or _string_value(record, "liveId")
        if live_id:
            return f"twicas:anonymous:{live_id}:{display_name}", display_name

    user_id = (
        _string_value(data, "userId")
        or _string_value(data, "user_id")
        or _string_value(record, "userId")
        or _string_value(record, "user_id")
    )
    screen_name = (
        _string_value(data, "screenName")
        or _string_value(data, "screen_name")
        or _string_value(data, "username")
        or _string_value(data, "userName")
        or _string_value(record, "screenName")
        or _string_value(record, "username")
    )
    identity = user_id or screen_name or display_name
    if not identity or identity == "unknown":
        return None
    return f"{service}:user:{identity}", display_name


def analyze_record(
    record: dict[str, Any],
    *,
    supported_services: set[str] | tuple[str, ...],
) -> VoteAnalysis:
    service = extract_service(record)
    display_name = extract_display_name(record)
    comment = extract_comment(record)

    if service not in supported_services:
        return VoteAnalysis(
            service=service or "unknown",
            display_name=display_name,
            comment=comment,
            voter_id="",
            result="ignored",
            reason="unsupported_service",
        )

    choice = parse_vote_command(comment)
    if choice is None:
        return VoteAnalysis(
            service=service,
            display_name=display_name,
            comment=comment,
            voter_id="",
            result="ignored",
            reason="no_command",
        )

    voter = voter_id_for(record, service)
    if voter is None:
        return VoteAnalysis(
            service=service,
            display_name=display_name,
            comment=comment,
            voter_id="",
            result="ignored",
            reason="no_voter",
        )

    voter_id, display_name = voter
    return VoteAnalysis(
        service=service,
        display_name=display_name,
        comment=comment,
        voter_id=voter_id,
        result=choice,
        reason="",
    )


class VoteCounter:
    def __init__(
        self,
        *,
        voting_window_seconds: int,
        minimum_votes: int,
        end_rate_threshold: float,
        supported_services: tuple[str, ...],
    ) -> None:
        self.voting_window_seconds = voting_window_seconds
        self.minimum_votes = minimum_votes
        self.end_rate_threshold = end_rate_threshold
        self.supported_services = set(supported_services)
        self._votes: dict[str, Vote] = {}
        self.visible = True

    def reset(self) -> None:
        self._votes.clear()

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def process(
        self,
        record: dict[str, Any],
        *,
        now: float | None = None,
        use_record_timestamp: bool = True,
    ) -> VoteAnalysis:
        analysis = analyze_record(record, supported_services=self.supported_services)
        if analysis.result not in {"end", "continue"}:
            return analysis

        if use_record_timestamp:
            timestamp = extract_timestamp(record, now)
        else:
            timestamp = time.time() if now is None else now

        self._votes[analysis.voter_id] = Vote(
            analysis.voter_id,
            analysis.result,
            timestamp,
            analysis.display_name,
            analysis.service,
        )
        self.prune(now=timestamp)
        return analysis

    def ingest(self, record: dict[str, Any], *, now: float | None = None) -> bool:
        analysis = self.process(record, now=now, use_record_timestamp=True)
        return analysis.result in {"end", "continue"}

    def prune(self, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        min_timestamp = current - self.voting_window_seconds
        expired = [
            voter_id
            for voter_id, vote in self._votes.items()
            if vote.timestamp < min_timestamp
        ]
        for voter_id in expired:
            del self._votes[voter_id]

    def state(self, *, now: float | None = None) -> dict[str, Any]:
        current = time.time() if now is None else now
        self.prune(now=current)
        end_votes = sum(1 for vote in self._votes.values() if vote.choice == "end")
        continue_votes = sum(
            1 for vote in self._votes.values() if vote.choice == "continue"
        )
        total_votes = end_votes + continue_votes
        end_rate = end_votes / total_votes if total_votes else 0.0
        threshold_met = (
            total_votes >= self.minimum_votes and end_rate >= self.end_rate_threshold
        )
        return {
            "visible": self.visible,
            "end_votes": end_votes,
            "continue_votes": continue_votes,
            "end_rate": round(end_rate, 4),
            "valid_votes": total_votes,
            "minimum_votes": self.minimum_votes,
            "end_rate_threshold": self.end_rate_threshold,
            "threshold_met": threshold_met,
            "window_seconds": self.voting_window_seconds,
            "updated_at": datetime.fromtimestamp(current, timezone.utc).isoformat(),
        }


def _dict_value(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def _string_value(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _normalize_epoch(float(value))
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    try:
        return _normalize_epoch(float(text))
    except ValueError:
        pass

    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _normalize_epoch(value: float) -> float:
    if value > 10_000_000_000:
        return value / 1000
    return value

