from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter import ttk
from .display_settings import DISPLAY_DEFAULTS, PANEL_POSITIONS, COUNTDOWN_POSITIONS, validate_display_settings

from .config import DEFAULT_CONFIG, DEFAULT_CONFIG_PATH, load_config, update_config
from .countdown import (
    MODE_CANCELLED,
    MODE_COUNTDOWN,
    MODE_NORMAL,
    MODE_STOP_FAILED,
    MODE_STOPPED,
    MODE_STOPPING,
    MODE_WOULD_STOP,
    CountdownController,
)
from .log_discovery import LogCandidate, find_onecomme_log_candidates
from .log_reader import read_jsonl, tail_jsonl
from .obs_control import ObsControlError, ObsController
from .obs_settings import (
    STOP_STREAMING_CONFIRMATION,
    ObsSettings,
    save_obs_settings,
    test_obs_connection_from_settings,
    validate_obs_port,
)
from .overlay import write_overlay_state
from .vote import VoteAnalysis, VoteCounter, extract_live_id


class VoteSettingsRefreshError(OSError):
    pass


class EndVoteApp:
    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.config_path = config_path
        self.config = load_config(config_path)
        self.counter = self._create_counter()
        self.obs = self._create_obs_controller()
        self.countdown = self._create_countdown()
        self.current_live_id: str | None = None
        self.obs_connected: bool | None = None
        self.event_queue: queue.Queue[dict] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.last_overlay_snapshot: dict | None = None
        self.panel_suppressed_until_next_vote = False
        self.vote_round_id = self.counter.round_id
        self.countdown_cancel_controls_active = False
        self.countdown_shortcuts_bound = False
        self.countdown_topmost_after_id: str | None = None

        self.root.title("配信終了投票くん v1.1.0")
        self.root.geometry("780x780")
        self.root.resizable(False, False)

        self.action_var = tk.StringVar(value="今やること：わんコメログを自動で探してください")
        self.counts_var = tk.StringVar(value="終了 0 / 続行 0 / 有効 0")
        self.rate_var = tk.StringVar(value="終了率 0%")
        self.visible_var = tk.StringVar(value="OBS表示: ON")
        self.countdown_var = tk.StringVar(value="カウントダウン: なし")
        self.obs_link_var = tk.StringVar(value="OBS連携: OFF")
        self.obs_stop_var = tk.StringVar(value="OBS停止: OFF（表示のみ）")
        self.obs_test_var = tk.StringVar(value="接続テスト結果: -")
        initial_log_path = str(self.config.log_file_path)
        self.log_path_var = tk.StringVar(
            value=f"ログ: {initial_log_path}" if initial_log_path not in ("", ".") else "ログ: 未選択"
        )
        self.last_read_var = tk.StringVar(value="最後に読んだ時刻: -")
        self.last_service_var = tk.StringVar(value="service: -")
        self.last_name_var = tk.StringVar(value="displayName: -")
        self.last_comment_var = tk.StringVar(value="comment: -")
        self.last_voter_var = tk.StringVar(value="voter_id: -")
        self.last_result_var = tk.StringVar(value="判定結果: -")
        self.last_reason_var = tk.StringVar(value="ignored理由: -")

        self._build_ui()
        self._write_state()
        self._start_tail()
        self._tick()

    def _create_counter(self) -> VoteCounter:
        return VoteCounter(
            voting_window_seconds=self.config.voting_window_seconds,
            minimum_votes=self.config.minimum_votes,
            end_rate_threshold=self.config.end_rate_threshold,
            supported_services=self.config.supported_services,
        )

    def _create_obs_controller(self) -> ObsController:
        return ObsController(
            enabled=self.config.obs_websocket_enabled,
            host=self.config.obs_host,
            port=self.config.obs_port,
            password=self.config.obs_password,
        )

    def _stop_streaming_effective(self) -> bool:
        # 実際に停止するには両方のフラグをconfig.jsonで明示ONにする必要がある。
        return (
            self.config.obs_websocket_enabled and self.config.stop_streaming_enabled
        )

    def _create_countdown(self) -> CountdownController:
        return CountdownController(
            enabled=self.config.countdown_enabled,
            countdown_seconds=self.config.countdown_seconds,
            trigger_once_per_live=self.config.trigger_once_per_live,
            stop_streaming_enabled=self._stop_streaming_effective(),
            on_stop_intent=self._begin_obs_stop,
        )

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=18, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="配信終了投票", font=("Yu Gothic UI", 18, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            frame,
            textvariable=self.action_var,
            font=("Yu Gothic UI", 15, "bold"),
            fg="#111827",
            wraplength=710,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))

        tk.Label(frame, textvariable=self.counts_var, font=("Yu Gothic UI", 15)).pack(
            anchor="w"
        )
        tk.Label(frame, textvariable=self.rate_var, font=("Yu Gothic UI", 14)).pack(
            anchor="w"
        )
        tk.Label(frame, textvariable=self.visible_var, fg="#4b5563").pack(
            anchor="w", pady=(0, 14)
        )

        countdown_frame = tk.LabelFrame(
            frame, text="配信終了カウントダウン（OBS停止は設定OFF時は実行されません）", padx=12, pady=8
        )
        countdown_frame.pack(fill="x", pady=(0, 6))
        tk.Label(
            countdown_frame,
            textvariable=self.countdown_var,
            font=("Yu Gothic UI", 13, "bold"),
            anchor="w",
            justify="left",
            wraplength=680,
        ).pack(fill="x", anchor="w")
        self.cancel_countdown_button = tk.Button(
            countdown_frame,
            text="カウントダウンをキャンセル",
            width=24,
            state="disabled",
            command=self._cancel_countdown,
        )
        self.cancel_countdown_button.pack(anchor="w", pady=(6, 0))

        self.countdown_cancel_frame = tk.Frame(
            frame,
            padx=12,
            pady=10,
            highlightthickness=2,
            highlightbackground="#dc2626",
            background="#fff1f2",
        )
        tk.Label(
            self.countdown_cancel_frame,
            text="カウントダウン中です。クリック、または何かキーを押すと止まります。",
            font=("Yu Gothic UI", 12, "bold"),
            fg="#7f1d1d",
            bg="#fff1f2",
            wraplength=690,
            justify="left",
        ).pack(anchor="center", pady=(0, 6))
        self.countdown_cancel_canvas = tk.Canvas(
            self.countdown_cancel_frame,
            width=250,
            height=250,
            bg="#fff1f2",
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self.countdown_cancel_canvas.pack(anchor="center")
        self.countdown_cancel_canvas.create_oval(
            10, 10, 240, 240, fill="#dc2626", outline="#991b1b", width=5, tags=("button",)
        )
        self.countdown_cancel_canvas.create_text(
            125, 105, text="まだ起きてる！", fill="white", font=("Yu Gothic UI", 18, "bold"), tags=("button",)
        )
        self.countdown_cancel_canvas.create_text(
            125, 145, text="カウントダウン停止", fill="white", font=("Yu Gothic UI", 17, "bold"), tags=("button",)
        )
        self.countdown_cancel_canvas.tag_bind("button", "<Button-1>", lambda _event: self._cancel_countdown())

        self.obs_frame = tk.LabelFrame(frame, text="OBS連携", padx=12, pady=8)
        obs_frame = self.obs_frame
        obs_frame.pack(fill="x", pady=(0, 6))
        tk.Label(
            obs_frame,
            textvariable=self.obs_link_var,
            anchor="w",
            justify="left",
        ).pack(fill="x", anchor="w")
        tk.Label(
            obs_frame,
            textvariable=self.obs_stop_var,
            font=("Yu Gothic UI", 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=680,
        ).pack(fill="x", anchor="w")
        obs_test_row = tk.Frame(obs_frame)
        obs_test_row.pack(fill="x", anchor="w", pady=(6, 0))
        self.obs_test_button = tk.Button(
            obs_test_row,
            text="OBS接続テスト",
            width=16,
            command=self._test_obs_connection,
        )
        self.obs_test_button.pack(side="left", padx=(0, 10))
        tk.Label(
            obs_test_row,
            textvariable=self.obs_test_var,
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(side="left", fill="x")
        self._refresh_obs_static_labels()

        log_button_row = tk.Frame(frame)
        log_button_row.pack(anchor="w", pady=(6, 0))
        tk.Button(
            log_button_row,
            text="わんコメログを自動で探す",
            width=24,
            command=self._auto_find_log_file,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            log_button_row,
            text="手動でログファイルを選ぶ",
            width=24,
            command=self._select_log_file,
        ).pack(side="left", padx=(0, 8))

        button_row = tk.Frame(frame)
        button_row.pack(anchor="w", pady=(8, 0))
        tk.Button(
            button_row,
            text="OBS表示 ON/OFF",
            width=16,
            command=self._toggle_visible,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            button_row,
            text="OBS設定",
            width=10,
            command=self._open_obs_settings,
        ).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="投票をリセット", width=14, command=self._reset).pack(
            side="left", padx=(0, 8)
        )
        tk.Button(button_row, text="表示設定", width=10, command=self._open_display_settings).pack(side="left", padx=4)
        tk.Button(button_row, text="投票設定", width=10, command=self._open_vote_settings).pack(
            side="left", padx=(0, 8)
        )
        tk.Button(button_row, text="終了する", width=10, command=self._close).pack(
            side="left"
        )

        tk.Label(
            frame,
            textvariable=self.log_path_var,
            fg="#6b7280",
            wraplength=710,
            justify="left",
        ).pack(anchor="w", pady=(16, 10))

        details = tk.LabelFrame(frame, text="最後に読んだコメント", padx=12, pady=10)
        details.pack(fill="x", expand=False, pady=(8, 0))
        for variable in (
            self.last_read_var,
            self.last_service_var,
            self.last_name_var,
            self.last_comment_var,
            self.last_voter_var,
            self.last_result_var,
            self.last_reason_var,
        ):
            tk.Label(
                details,
                textvariable=variable,
                anchor="w",
                justify="left",
                wraplength=690,
            ).pack(fill="x", anchor="w")

        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _start_tail(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        if str(self.config.log_file_path) in ("", ".") or not self.config.log_file_path.is_file():
            self.action_var.set("今やること：わんコメログを自動で探してください")
            return

        self.action_var.set("監視中：コメントを待っています")
        self.stop_event = threading.Event()
        self.worker = threading.Thread(
            target=self._tail_worker,
            args=(self.stop_event,),
            daemon=True,
        )
        self.worker.start()

    def _tail_worker(self, stop_event: threading.Event) -> None:
        def report_parse_error(exc: Exception) -> None:
            self.event_queue.put(
                {
                    "type": "parse_error",
                    "read_at": time.time(),
                    "error": str(exc),
                }
            )

        try:
            for record in tail_jsonl(
                self.config.log_file_path,
                stop_event.is_set,
                poll_interval_seconds=self.config.poll_interval_seconds,
                start_at_end=not self.config.read_existing_log_on_start,
                on_parse_error=report_parse_error,
            ):
                self.event_queue.put(
                    {
                        "type": "record",
                        "record": record,
                        "read_at": time.time(),
                    }
                )
        except Exception as exc:
            self.event_queue.put(
                {
                    "type": "watch_error",
                    "read_at": time.time(),
                    "error": str(exc),
                }
            )

    def _auto_find_log_file(self) -> None:
        candidates = find_onecomme_log_candidates()
        if not candidates:
            self.action_var.set(
                "わんコメのコメント保存ファイル（.log / .jsonl）が見つかりませんでした。\n"
                "まず、わんコメ側で以下を確認してください。\n"
                "1. わんコメを起動しているか\n"
                "2. 設定 → その他 で『コメントログを残す』がONか\n"
                "3. 『ログをファイルとしても書き出し』がONか\n"
                "4. 設定後にコメントが1個以上流れたか"
            )
            return

        if len(candidates) == 1:
            self._use_log_file(candidates[0].path)
            return

        selected = self._choose_log_candidate(candidates)
        if selected is None:
            return
        self._use_log_file(selected)

    def _choose_log_candidate(self, candidates: list[LogCandidate]) -> Path | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("わんコメログ候補")
        dialog.geometry("720x360")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        selected: dict[str, Path | None] = {"path": None}

        tk.Label(
            dialog,
            text="新しい順に並んでいます。使うログを選んでください。",
            font=("Yu Gothic UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 8))

        listbox = tk.Listbox(dialog, height=10, width=105)
        listbox.pack(fill="both", expand=True, padx=14)
        for candidate in candidates:
            modified = datetime.fromtimestamp(candidate.modified_at).strftime(
                "%Y-%m-%d %H:%M"
            )
            listbox.insert(tk.END, f"{modified}  {candidate.path}")
        if candidates:
            listbox.selection_set(0)
            listbox.activate(0)

        def choose() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            selected["path"] = candidates[selection[0]].path
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        button_row = tk.Frame(dialog)
        button_row.pack(anchor="e", padx=14, pady=12)
        tk.Button(button_row, text="このログを使う", width=14, command=choose).pack(
            side="left", padx=(0, 8)
        )
        tk.Button(button_row, text="キャンセル", width=10, command=cancel).pack(
            side="left"
        )
        listbox.bind("<Double-Button-1>", lambda _event: choose())
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        self.root.wait_window(dialog)
        return selected["path"]

    def _select_log_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="手動でわんコメログを選ぶ",
            filetypes=[
                ("わんコメログ", "*.log;*.jsonl"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not selected:
            return
        self._use_log_file(Path(selected).resolve())

    def _use_log_file(self, path: Path) -> None:
        self._stop_worker()
        self._clear_event_queue()
        update_config(self.config_path, {"log_file_path": str(path)})
        self.config = load_config(self.config_path)
        self.log_path_var.set(f"ログ: {self.config.log_file_path}")
        self.counter.reset()
        self.obs = self._create_obs_controller()
        self.countdown = self._create_countdown()
        self.current_live_id = None
        self.vote_round_id = self.counter.round_id
        self._refresh_obs_static_labels()
        self._write_state()
        self._refresh_labels()
        self._start_tail()

    def _stop_worker(self) -> None:
        self.stop_event.set()
        self.worker = None

    def _clear_event_queue(self) -> None:
        while True:
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                return

    def _tick(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            event_type = event.get("type")
            if event_type == "record":
                live_id = extract_live_id(event["record"])
                if live_id is not None:
                    self.current_live_id = live_id
                analysis = self.counter.process(
                    event["record"],
                    now=event["read_at"],
                    use_record_timestamp=False,
                )
                if analysis.result in {"end", "continue"}:
                    self.panel_suppressed_until_next_vote = False
                self._show_last_analysis(event["read_at"], analysis)
                self.action_var.set("監視中：コメントを待っています")
            elif event_type == "parse_error":
                self._show_last_error(event["read_at"], "parse_error", event["error"])
                self.action_var.set("監視中：コメントを待っています")
            elif event_type == "watch_error":
                self._show_last_error(event["read_at"], "watch_error", event["error"])
                self.action_var.set(f"監視エラー: {event['error']}")
            elif event_type == "obs_test_result":
                result = event["result"]
                self.obs_connected = result.ok
                self.obs_test_var.set(f"接続テスト結果: {result.message}")
                self.obs_test_button.config(state="normal")
            elif event_type == "obs_stop_result":
                self._handle_obs_stop_result(event)

        state = self._current_state()
        self._refresh_labels(state)
        self._write_state_if_changed(state)
        self.root.after(500, self._tick)

    def _current_state(self) -> dict:
        state = self.counter.state()
        if self.counter.round_id != self.vote_round_id:
            # ローリング受付時間内の票がすべて失効した投票ラウンド境界は、
            # 次のGUI tickより先に新票が来てもVoteCounter側で検出される。
            self.countdown.reset()
            self.panel_suppressed_until_next_vote = False
            self.vote_round_id = self.counter.round_id
        self.countdown.update(
            threshold_met=state["threshold_met"],
            live_id=self.current_live_id,
        )
        state.update(self.countdown.state())
        state.update({key: getattr(self.config, key, default) for key, default in DISPLAY_DEFAULTS.items()})
        state["obs_connected"] = self.obs_connected
        state["stop_streaming_enabled"] = self._stop_streaming_effective()
        state["display_enabled"] = bool(state["visible"])
        state["visible"] = overlay_should_be_visible(
            display_enabled=state["display_enabled"],
            mode=str(state.get("mode", "normal")),
            valid_votes=int(state["valid_votes"]),
            panel_suppressed=self.panel_suppressed_until_next_vote,
        )
        return self._with_preview(state)

    def _with_preview(self, state: dict) -> dict:
        state = dict(state)
        state["preview_mode"] = getattr(self, "preview_mode", "none")
        if state["preview_mode"] != "none":
            state.update(getattr(self, "preview_settings", {}))
        return state

    def _set_display_preview(self, mode: str, values: dict | None = None) -> None:
        if mode not in ("none", "vote", "countdown"):
            raise ValueError("不明なプレビュー種類です。")
        settings = validate_display_settings(values or {}) if mode != "none" else {}
        self.preview_mode = mode
        self.preview_settings = settings
        # Read-only snapshots: preview controls never update the countdown controller.
        state = self.counter.state()
        state.update(self.countdown.state())
        state.update({key: getattr(self.config, key, default) for key, default in DISPLAY_DEFAULTS.items()})
        state["visible"] = overlay_should_be_visible(
            display_enabled=self.counter.visible, mode=state["mode"],
            valid_votes=state["valid_votes"], panel_suppressed=self.panel_suppressed_until_next_vote,
        )
        state["stop_streaming_enabled"] = self._stop_streaming_effective()
        self._write_state_if_changed(self._with_preview(state))

    def _test_obs_connection(self) -> None:
        if not self.config.obs_websocket_enabled:
            self.obs_test_var.set(
                "接続テスト結果: OBS連携がOFFです（config.jsonのobs_websocket_enabled）"
            )
            return
        self.obs_test_button.config(state="disabled")
        self.obs_test_var.set("接続テスト結果: 接続中…")

        def worker() -> None:
            result = self.obs.test_connection()
            self.event_queue.put({"type": "obs_test_result", "result": result})

        threading.Thread(target=worker, daemon=True).start()

    def _save_display_settings(self, values: dict) -> None:
        updates = validate_display_settings(values)
        update_config(self.config_path, updates)
        self.config = replace(self.config, **updates)
        self.preview_mode = "none"
        self.preview_settings = {}
        try:
            self._write_state()
        except OSError as exc:
            raise VoteSettingsRefreshError("設定は保存しました。OBS表示の更新に失敗しましたが、自動的に再試行します。") from exc

    def _open_display_settings(self) -> None:
        existing = getattr(self, "display_settings_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        dialog = tk.Toplevel(self.root)
        self.display_settings_dialog = dialog
        dialog.title("表示設定")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        frame = tk.Frame(dialog, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        variables = {}
        choices_by_key = {"vote_panel_position": PANEL_POSITIONS, "countdown_position": COUNTDOWN_POSITIONS}
        labels = {"vote_panel_position": "投票パネル位置", "countdown_position": "カウントダウン大表示位置", "vote_panel_x": "投票パネル X (px)", "vote_panel_y": "投票パネル Y (px)", "countdown_x": "カウントダウン X (px)", "countdown_y": "カウントダウン Y (px)"}
        for row, key in enumerate(DISPLAY_DEFAULTS):
            value = getattr(self.config, key)
            choices = choices_by_key.get(key)
            if choices:
                value = next(label for label, preset in choices.items() if preset == value)
            variable = tk.StringVar(master=dialog, value=str(value))
            variables[key] = variable
            tk.Label(frame, text=labels[key]).grid(row=row, column=0, sticky="w", pady=4)
            if choices:
                widget = ttk.Combobox(frame, textvariable=variable, values=list(choices), state="readonly", width=20)
            else:
                widget = tk.Spinbox(frame, textvariable=variable, from_=-500, to=500, width=20)
            widget.grid(row=row, column=1, padx=8, pady=4)
        tk.Label(frame, text="X: 正で右／負で左、Y: 正で下／負で上。各-500〜+500px。").grid(row=6, columnspan=2, pady=8)
        status = tk.Label(frame, text="", wraplength=440, justify="left")
        status.grid(row=7, columnspan=2)

        def collect():
            return {key: choices_by_key[key].get(var.get(), "") if key in choices_by_key else var.get() for key, var in variables.items()}

        def preview(mode):
            try:
                self._set_display_preview(mode, collect())
            except (ValueError, OSError) as exc:
                status.config(text=str(exc), fg="#b91c1c")
                return
            status.config(text="プレビュー中（実際の投票・停止には影響しません）" if mode != "none" else "プレビューを終了しました。", fg="#374151")

        def changed(*_args):
            if getattr(self, "preview_mode", "none") != "none":
                preview(self.preview_mode)

        for variable in variables.values():
            variable.trace_add("write", changed)

        def close():
            try:
                self._set_display_preview("none")
            except OSError as exc:
                status.config(text=f"表示更新に失敗しました。再度閉じてください: {exc}", fg="#b91c1c")
                return
            dialog.destroy()
            self.display_settings_dialog = None

        dialog.protocol("WM_DELETE_WINDOW", close)

        def save():
            values = collect()
            try:
                self._save_display_settings(values)
            except (ValueError, OSError) as exc:
                status.config(text=str(exc), fg="#b91c1c")
                return
            status.config(text="保存しました。OBS表示に反映しました。", fg="#166534")

        def reset():
            for key, value in DISPLAY_DEFAULTS.items():
                choices = choices_by_key.get(key)
                if choices:
                    value = next(label for label, preset in choices.items() if preset == value)
                variables[key].set(str(value))
            status.config(text="初期値に戻しました。「保存」で確定します。", fg="#374151")

        buttons = tk.Frame(frame)
        buttons.grid(row=9, columnspan=2, pady=(12, 0))
        previews = tk.Frame(frame)
        previews.grid(row=8, columnspan=2, pady=(12, 0))
        for text, mode in (("投票パネルをプレビュー", "vote"), ("カウントダウンをプレビュー", "countdown"), ("プレビュー終了", "none")):
            tk.Button(previews, text=text, command=lambda mode=mode: preview(mode)).pack(side="left", padx=4)
        for text, command in (("保存", save), ("初期値に戻す", reset), ("キャンセル", close)):
            tk.Button(buttons, text=text, command=command, width=14).pack(side="left", padx=4)
        if self.countdown.mode == MODE_COUNTDOWN:
            self._bring_window_to_front_for_countdown()

    def _open_vote_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("投票設定")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        frame = tk.Frame(dialog, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        form = tk.Frame(frame)
        form.pack(fill="x")
        tk.Label(form, text="判定に必要な人数:").pack(side="left", padx=(0, 8))
        value_var = tk.StringVar(master=dialog, value=str(self.config.minimum_votes))
        entry = tk.Entry(form, textvariable=value_var, width=8)
        entry.pack(side="left")
        tk.Label(frame, text="1〜999人（初期値20人）。保存するとすぐに反映されます。").pack(
            anchor="w", pady=(10, 0)
        )
        tk.Label(frame, text="現在の票が条件を満たすとカウントダウンが始まります。").pack(anchor="w")
        status = tk.Label(frame, text="", anchor="w", justify="left", wraplength=420)
        status.pack(fill="x", pady=(10, 8))

        def save() -> None:
            try:
                self._save_vote_settings(value_var.get())
            except ValueError as exc:
                status.config(text=str(exc), fg="#b91c1c")
                return
            except VoteSettingsRefreshError as exc:
                status.config(text=str(exc), fg="#92400e")
                return
            except OSError:
                status.config(text="設定または表示ファイルの書き込みに失敗しました。保存先を確認してください。", fg="#b91c1c")
                return
            status.config(text="保存しました。設定を反映しました。", fg="#166534")

        def restore_default() -> None:
            value_var.set(str(DEFAULT_CONFIG["minimum_votes"]))
            status.config(text="初期値20人に戻しました。「保存」で確定します。", fg="#374151")

        buttons = tk.Frame(frame)
        buttons.pack(anchor="e")
        tk.Button(buttons, text="保存", width=10, command=save).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="初期値に戻す", width=14, command=restore_default).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="キャンセル", width=10, command=dialog.destroy).pack(side="left")
        # モーダルなgrabは使わず、カウントダウン中の停止ボタンを操作可能に保つ。
        if self.countdown.mode == MODE_COUNTDOWN:
            self._bring_window_to_front_for_countdown()
        else:
            entry.focus_set()

    def _save_vote_settings(self, value: str) -> None:
        if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 999:
            raise ValueError("判定に必要な人数は1〜999の整数で入力してください。")
        minimum_votes = int(value)
        update_config(self.config_path, {"minimum_votes": minimum_votes})
        self.config = replace(self.config, minimum_votes=minimum_votes)
        self.counter.minimum_votes = minimum_votes
        try:
            self._write_state()
        except OSError as exc:
            raise VoteSettingsRefreshError(
                "設定は保存しました。OBS表示の更新に失敗しましたが、自動的に再試行します。"
            ) from exc
        self._refresh_labels()

    def _open_obs_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("OBS設定")
        dialog.geometry("520x420")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        obs_enabled_var = tk.BooleanVar(value=self.config.obs_websocket_enabled)
        stop_enabled_var = tk.BooleanVar(value=self.config.stop_streaming_enabled)
        host_var = tk.StringVar(value=self.config.obs_host or "127.0.0.1")
        port_var = tk.StringVar(value=str(self.config.obs_port or 4455))
        password_var = tk.StringVar(value=self.config.obs_password)
        status_var = tk.StringVar(value="OBS停止は通常OFFのまま使ってください。")

        frame = tk.Frame(dialog, padx=18, pady=16)
        frame.pack(fill="both", expand=True)

        def on_stop_toggle() -> None:
            if not stop_enabled_var.get():
                return
            confirmed = messagebox.askokcancel(
                "OBS停止を有効にする確認",
                STOP_STREAMING_CONFIRMATION,
                parent=dialog,
            )
            if not confirmed:
                stop_enabled_var.set(False)

        tk.Checkbutton(
            frame,
            text="OBS連携を有効にする",
            variable=obs_enabled_var,
        ).pack(anchor="w")
        tk.Checkbutton(
            frame,
            text="OBS停止を有効にする",
            variable=stop_enabled_var,
            command=on_stop_toggle,
        ).pack(anchor="w", pady=(4, 12))

        form = tk.Frame(frame)
        form.pack(fill="x")
        tk.Label(form, text="OBSホスト", width=14, anchor="w").grid(
            row=0, column=0, sticky="w", pady=4
        )
        tk.Entry(form, textvariable=host_var, width=34).grid(
            row=0, column=1, sticky="we", pady=4
        )
        tk.Label(form, text="OBSポート", width=14, anchor="w").grid(
            row=1, column=0, sticky="w", pady=4
        )
        tk.Entry(form, textvariable=port_var, width=34).grid(
            row=1, column=1, sticky="we", pady=4
        )
        tk.Label(form, text="OBSパスワード", width=14, anchor="w").grid(
            row=2, column=0, sticky="w", pady=4
        )
        tk.Entry(form, textvariable=password_var, width=34, show="*").grid(
            row=2, column=1, sticky="we", pady=4
        )
        tk.Label(
            form,
            text=(
                "OBSの「ツール → WebSocketサーバー設定」にある認証用パスワードです。\n"
                "認証がOFFなら空欄でOK。作者や第三者に送る必要はありません。"
            ),
            fg="#6b7280",
            anchor="w",
            justify="left",
            wraplength=360,
        ).grid(row=3, column=1, sticky="w", pady=(0, 4))
        form.columnconfigure(1, weight=1)

        status_label = tk.Label(
            frame,
            textvariable=status_var,
            fg="#374151",
            anchor="w",
            justify="left",
            wraplength=470,
        )
        status_label.pack(fill="x", pady=(14, 10))

        def collect_settings() -> ObsSettings | None:
            try:
                port = validate_obs_port(port_var.get())
            except ValueError as exc:
                status_var.set(str(exc))
                messagebox.showerror("OBS設定", str(exc), parent=dialog)
                return None
            return ObsSettings(
                obs_websocket_enabled=bool(obs_enabled_var.get()),
                stop_streaming_enabled=bool(stop_enabled_var.get()),
                obs_host=host_var.get().strip() or "127.0.0.1",
                obs_port=port,
                obs_password=password_var.get(),
            )

        def test_connection() -> None:
            settings = collect_settings()
            if settings is None:
                return
            if not settings.obs_websocket_enabled:
                status_var.set("OBS連携がOFFです")
                return
            status_var.set("OBSへ接続テスト中です...")
            test_button.config(state="disabled")

            def worker() -> None:
                result = test_obs_connection_from_settings(settings)

                def finish() -> None:
                    if not status_label.winfo_exists():
                        return
                    status_var.set(result.message)
                    test_button.config(state="normal")

                self.root.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        def save() -> None:
            settings = collect_settings()
            if settings is None:
                return
            save_obs_settings(self.config_path, settings)
            self.config = load_config(self.config_path)
            self.obs = self._create_obs_controller()
            self.countdown = self._create_countdown()
            self.obs_connected = None
            self._refresh_obs_static_labels()
            self._write_state()
            self._refresh_labels()
            status_var.set("保存しました。設定を反映しました。")
            messagebox.showinfo("OBS設定", "保存しました。設定を反映しました。", parent=dialog)

        button_row = tk.Frame(frame)
        button_row.pack(anchor="e", pady=(8, 0))
        test_button = tk.Button(
            button_row,
            text="OBS接続テスト",
            width=16,
            command=test_connection,
        )
        test_button.pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="保存", width=10, command=save).pack(
            side="left", padx=(0, 8)
        )
        tk.Button(button_row, text="キャンセル", width=10, command=dialog.destroy).pack(
            side="left"
        )

    def _begin_obs_stop(self) -> None:
        """カウントダウン完走時にのみCountdownControllerから呼ばれる。"""

        def worker() -> None:
            try:
                message = self.obs.stop_streaming()
                self.event_queue.put(
                    {"type": "obs_stop_result", "ok": True, "message": message}
                )
            except ObsControlError as exc:
                self.event_queue.put(
                    {"type": "obs_stop_result", "ok": False, "error": str(exc)}
                )
            except Exception as exc:
                self.event_queue.put(
                    {"type": "obs_stop_result", "ok": False, "error": str(exc)}
                )

        threading.Thread(target=worker, daemon=True).start()

    def _handle_obs_stop_result(self, event: dict) -> None:
        if event["ok"]:
            self.obs_connected = True
            self.countdown.report_stop_success()
            self.obs_test_var.set(f"接続テスト結果: {event['message']}")
        else:
            self.obs_connected = False
            self.countdown.report_stop_failure(event["error"])
            self.obs_test_var.set(f"接続テスト結果: {event['error']}")
        self._write_state()
        self._refresh_labels()

    def _show_last_analysis(self, read_at: float, analysis: VoteAnalysis) -> None:
        self.last_read_var.set(f"最後に読んだ時刻: {_format_time(read_at)}")
        self.last_service_var.set(f"service: {analysis.service or '-'}")
        self.last_name_var.set(f"displayName: {analysis.display_name or '-'}")
        self.last_comment_var.set(f"comment: {analysis.comment or '-'}")
        self.last_voter_var.set(f"voter_id: {analysis.voter_id or '-'}")
        self.last_result_var.set(f"判定結果: {analysis.result}")
        self.last_reason_var.set(f"ignored理由: {analysis.reason or '-'}")

    def _show_last_error(self, read_at: float, kind: str, message: str) -> None:
        self.last_read_var.set(f"最後に読んだ時刻: {_format_time(read_at)}")
        self.last_service_var.set("service: -")
        self.last_name_var.set("displayName: -")
        self.last_comment_var.set(f"comment: {message}")
        self.last_voter_var.set("voter_id: -")
        self.last_result_var.set("判定結果: ignored")
        self.last_reason_var.set(f"ignored理由: {kind}")

    def _refresh_labels(self, state: dict | None = None) -> None:
        if state is None:
            state = self._current_state()
        end_rate_percent = int(round(state["end_rate"] * 100))
        self.counts_var.set(
            f"終了 {state['end_votes']} / 続行 {state['continue_votes']} / 有効 {state['valid_votes']}"
        )
        self.rate_var.set(f"終了率 {end_rate_percent}%")
        if state.get("display_enabled"):
            self.visible_var.set("OBS表示: ON（必要時のみ表示）")
        else:
            self.visible_var.set("OBS表示: OFF")
        self._refresh_countdown_labels(state)

    def _refresh_countdown_labels(self, state: dict) -> None:
        mode = state.get("mode", "normal")
        if mode == MODE_COUNTDOWN:
            remaining = state.get("countdown_remaining", 0)
            if state.get("stop_streaming_enabled"):
                self.countdown_var.set(
                    f"終了ライン到達：{remaining}秒後にOBSの配信を停止します"
                )
            else:
                self.countdown_var.set(
                    f"終了ライン到達：{remaining}秒後に配信終了予定（停止OFF・表示のみ）"
                )
        elif mode == MODE_CANCELLED:
            self.countdown_var.set("カウントダウン: キャンセルされました")
        elif mode == MODE_WOULD_STOP:
            self.countdown_var.set(
                "ここで停止予定です（OBS停止はOFFのため停止しません）"
            )
        elif mode == MODE_STOPPING:
            self.countdown_var.set("OBSへ停止要求中…")
        elif mode == MODE_STOPPED:
            self.countdown_var.set("配信停止を実行しました")
        elif mode == MODE_STOP_FAILED:
            error = state.get("stop_error") or "原因不明"
            self.countdown_var.set(f"配信停止に失敗しました: {error}")
        else:
            self.countdown_var.set("カウントダウン: なし（終了ライン未到達）")
        self.cancel_countdown_button.config(
            state="normal" if state.get("can_cancel") else "disabled"
        )
        self._sync_countdown_cancel_controls(countdown_cancel_input_enabled(mode))

    def _sync_countdown_cancel_controls(self, active: bool) -> None:
        if active == self.countdown_cancel_controls_active:
            return
        self.countdown_cancel_controls_active = active
        if active:
            self.countdown_cancel_frame.pack(fill="x", pady=(0, 8), before=self.obs_frame)
            self._bind_countdown_shortcuts()
            self._bring_window_to_front_for_countdown()
        else:
            self.countdown_cancel_frame.pack_forget()
            self._unbind_countdown_shortcuts()
            self._release_countdown_topmost()

    def _bind_countdown_shortcuts(self) -> None:
        if self.countdown_shortcuts_bound:
            return
        self.countdown_shortcuts_bound = True
        self.root.bind_all("<KeyPress>", self._on_countdown_cancel_shortcut)

    def _unbind_countdown_shortcuts(self) -> None:
        if not self.countdown_shortcuts_bound:
            return
        self.countdown_shortcuts_bound = False
        self.root.unbind_all("<KeyPress>")

    def _on_countdown_cancel_shortcut(self, _event: tk.Event) -> str | None:
        if self.countdown.mode != MODE_COUNTDOWN:
            return None
        self._cancel_countdown()
        return "break"

    def _bring_window_to_front_for_countdown(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.countdown_cancel_canvas.focus_set()
            self.root.attributes("-topmost", True)
            if self.countdown_topmost_after_id is not None:
                self.root.after_cancel(self.countdown_topmost_after_id)
            self.countdown_topmost_after_id = self.root.after(3000, self._release_countdown_topmost)
        except tk.TclError:
            pass

    def _release_countdown_topmost(self) -> None:
        if self.countdown_topmost_after_id is not None:
            try:
                self.root.after_cancel(self.countdown_topmost_after_id)
            except tk.TclError:
                pass
            self.countdown_topmost_after_id = None
        try:
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _refresh_obs_static_labels(self) -> None:
        if self.config.obs_websocket_enabled:
            self.obs_link_var.set(
                f"OBS連携: ON（{self.config.obs_host}:{self.config.obs_port}）"
            )
        else:
            self.obs_link_var.set("OBS連携: OFF")
        if self._stop_streaming_effective():
            self.obs_stop_var.set("OBS停止: ON（カウントダウン後に停止します）")
        elif self.config.stop_streaming_enabled:
            self.obs_stop_var.set(
                "OBS停止: OFF（obs_websocket_enabledがOFFのため停止しません）"
            )
        else:
            self.obs_stop_var.set("OBS停止: OFF（表示のみ）")

    def _write_state(self) -> None:
        state = self._current_state()
        write_overlay_state(self.config.overlay_state_path, state)
        self.last_overlay_snapshot = _state_snapshot(state)

    def _write_state_if_changed(self, state: dict) -> None:
        snapshot = _state_snapshot(state)
        if snapshot == self.last_overlay_snapshot:
            return
        write_overlay_state(self.config.overlay_state_path, state)
        self.last_overlay_snapshot = snapshot

    def _toggle_visible(self) -> None:
        self.counter.set_visible(not self.counter.visible)
        self._write_state()
        self._refresh_labels()

    def _cancel_countdown(self) -> None:
        if self.countdown.cancel():
            self.panel_suppressed_until_next_vote = True
            self._write_state()
            self._refresh_labels()

    def _reset(self) -> None:
        self.counter.reset()
        self.countdown.reset()
        self.vote_round_id = self.counter.round_id
        self.panel_suppressed_until_next_vote = False
        self._sync_countdown_cancel_controls(False)
        self._write_state()
        self._refresh_labels()

    def _close(self) -> None:
        self._set_display_preview("none")
        self._sync_countdown_cancel_controls(False)
        self._stop_worker()
        self.root.after(50, self.root.destroy)


def overlay_should_be_visible(
    *,
    display_enabled: bool,
    mode: str,
    valid_votes: int,
    panel_suppressed: bool = False,
) -> bool:
    if not display_enabled:
        return False
    if mode != MODE_NORMAL:
        return True
    if panel_suppressed:
        return False
    return valid_votes > 0


def countdown_cancel_input_enabled(mode: str) -> bool:
    return mode == MODE_COUNTDOWN


def replay_sample(config_path: Path) -> None:
    config = load_config(config_path)
    counter = VoteCounter(
        voting_window_seconds=config.voting_window_seconds,
        minimum_votes=config.minimum_votes,
        end_rate_threshold=config.end_rate_threshold,
        supported_services=config.supported_services,
    )
    for record in read_jsonl(config.log_file_path):
        counter.ingest(record)
    state = counter.state()
    # replay時はカウントダウンを発動させず、normal状態の欄だけ埋める。
    state.update(
        {
            "mode": "normal",
            "countdown_remaining": 0,
            "countdown_started_at": None,
            "can_cancel": False,
            "obs_connected": None,
            "stop_streaming_enabled": False,
            "stop_result": None,
            "stop_error": None,
        }
    )
    state["display_enabled"] = bool(state["visible"])
    state["visible"] = overlay_should_be_visible(
        display_enabled=state["display_enabled"],
        mode=str(state.get("mode", "normal")),
        valid_votes=int(state["valid_votes"]),
    )
    write_overlay_state(config.overlay_state_path, state)
    print(
        f"end={state['end_votes']} continue={state['continue_votes']} "
        f"valid={state['valid_votes']} rate={state['end_rate']:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="配信終了投票くん")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--replay-sample",
        action="store_true",
        help="Read the configured JSONL once and write overlay_state.json.",
    )
    args = parser.parse_args()
    config_path = Path(args.config)

    if args.replay_sample:
        replay_sample(config_path)
        return

    root = tk.Tk()
    try:
        EndVoteApp(root, config_path)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror("配信終了投票くん", str(exc))
        raise


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _state_snapshot(state: dict) -> dict:
    return {key: value for key, value in state.items() if key != "updated_at"}


if __name__ == "__main__":
    main()
