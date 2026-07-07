from __future__ import annotations

import argparse
from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .config import DEFAULT_CONFIG_PATH, load_config, update_config
from .log_discovery import LogCandidate, find_onecomme_log_candidates
from .log_reader import read_jsonl, tail_jsonl
from .overlay import write_overlay_state
from .vote import VoteAnalysis, VoteCounter


class EndVoteApp:
    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.config_path = config_path
        self.config = load_config(config_path)
        self.counter = self._create_counter()
        self.event_queue: queue.Queue[dict] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.last_overlay_snapshot: dict | None = None

        self.root.title("Amemiya End Vote v0.1")
        self.root.geometry("780x560")
        self.root.resizable(False, False)

        self.action_var = tk.StringVar(value="今やること：わんコメログを自動で探してください")
        self.counts_var = tk.StringVar(value="終了 0 / 続行 0 / 有効 0")
        self.rate_var = tk.StringVar(value="終了率 0%")
        self.visible_var = tk.StringVar(value="OBS表示: ON")
        self.log_path_var = tk.StringVar(value=f"ログ: {self.config.log_file_path}")
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
        tk.Button(button_row, text="投票をリセット", width=14, command=self._reset).pack(
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

        if not self.config.log_file_path.exists():
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
                analysis = self.counter.process(
                    event["record"],
                    now=event["read_at"],
                    use_record_timestamp=False,
                )
                self._show_last_analysis(event["read_at"], analysis)
                self.action_var.set("監視中：コメントを待っています")
            elif event_type == "parse_error":
                self._show_last_error(event["read_at"], "parse_error", event["error"])
                self.action_var.set("監視中：コメントを待っています")
            elif event_type == "watch_error":
                self._show_last_error(event["read_at"], "watch_error", event["error"])
                self.action_var.set(f"監視エラー: {event['error']}")

        state = self.counter.state()
        self._refresh_labels(state)
        self._write_state_if_changed(state)
        self.root.after(500, self._tick)

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
            state = self.counter.state()
        end_rate_percent = int(round(state["end_rate"] * 100))
        self.counts_var.set(
            f"終了 {state['end_votes']} / 続行 {state['continue_votes']} / 有効 {state['valid_votes']}"
        )
        self.rate_var.set(f"終了率 {end_rate_percent}%")
        self.visible_var.set(f"OBS表示: {'ON' if state['visible'] else 'OFF'}")

    def _write_state(self) -> None:
        state = self.counter.state()
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

    def _reset(self) -> None:
        self.counter.reset()
        self._write_state()
        self._refresh_labels()

    def _close(self) -> None:
        self._stop_worker()
        self.root.after(50, self.root.destroy)


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
    write_overlay_state(config.overlay_state_path, counter.state())
    state = counter.state()
    print(
        f"end={state['end_votes']} continue={state['continue_votes']} "
        f"valid={state['valid_votes']} rate={state['end_rate']:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Amemiya end-vote counter")
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
        messagebox.showerror("Amemiya End Vote", str(exc))
        raise


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _state_snapshot(state: dict) -> dict:
    return {key: value for key, value in state.items() if key != "updated_at"}


if __name__ == "__main__":
    main()
