# SPEC.md

## Product name

stream-end-vote

## Purpose

Display a vote meter for ending a stream based on OneComme comments.

## Initial target

Display-only OBS overlay.

## Non-goals

- Native OBS plugin
- Automatic stream shutdown
- Moderator-only chat commands
- Twitch/Kick official API integration

## Input

OneComme JSONL comment logs.

## Output

- overlay_state.json
- overlay.html for OBS browser source

## Vote window

Default: recent 3 minutes

## Thresholds

Default values:

- Minimum valid votes: 20
- End vote threshold: 70%

These values should be configurable later.

## TwitCasting anonymous handling

TwitCasting anonymous users are stable within a liveId.
The anonymous number changes when the stream frame changes.
Therefore voter identity must include liveId.

Example:

twicas:anon:834384777:2142
