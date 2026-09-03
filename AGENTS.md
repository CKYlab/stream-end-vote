# AGENTS.md

## Project Goal

Build a Windows tool that reads OneComme JSONL comment logs and displays a stream-ending vote meter in an OBS browser source.

## Product Guardrails

- OBS stop-streaming must remain opt-in and disabled in release defaults.
- Do not add chat-based admin commands such as `!投票開始`, `!リセット`, or forced end commands.
- Do not assume moderators are present.
- Listener chat commands are vote commands only.
- Admin operations must stay local to the Windows GUI.

## Vote Commands

- End: `!寝ろ`, `!終了`, `！寝ろ`, `！終了`
- Continue: `!続行`, `!まだ`, `！続行`, `！まだ`

## Identity Rules

- Do not use `data.id` as a voter ID because it may be the comment ID.
- For TwitCasting anonymous comments, use `data.liveId` plus the anonymous number in `data.displayName`.
- For normal users, prefer `data.userId`, then stable screen-name fields.
- One voter has one vote; later votes overwrite earlier votes.
