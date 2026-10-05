from __future__ import annotations

import json
from pathlib import Path
import shutil
import zipfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from end_vote.display_settings import DISPLAY_DEFAULTS


ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "release"
ZIP_PATH = ROOT / "配信終了投票くん_v1.1.0.zip"
BUILT_EXE_NAME = "stream-end-vote.exe"

EXPECTED_RELEASE_NAMES = [
    "01_最初に読む_使い方.txt",
    "02_起動する_配信終了投票くん.exe",
    "03_OBSに入れる_overlay.html",
    "config.json",
    "overlay_state.json",
    "LICENSE",
]

FORBIDDEN_RELEASE_TEXT = [
    "CHiKA",
    "ちか",
    "CodexTest",
    "Amemiya",
    "雨宮",
    "chobitsuki",
    "C:\\Users",
    "D:\\",
]


def main() -> None:
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir()

    copied_files = [
        (ROOT / "01_最初に読む_使い方.txt", RELEASE / EXPECTED_RELEASE_NAMES[0]),
        (ROOT / "dist" / BUILT_EXE_NAME, RELEASE / EXPECTED_RELEASE_NAMES[1]),
        (ROOT / "overlay.html", RELEASE / EXPECTED_RELEASE_NAMES[2]),
        (ROOT / "LICENSE", RELEASE / "LICENSE"),
    ]

    for src, dst in copied_files:
        if not src.exists():
            raise FileNotFoundError(f"Missing file: {src}")
        shutil.copy2(src, dst)

    write_release_config(RELEASE / "config.json")
    write_release_overlay_state(RELEASE / "overlay_state.json")
    verify_release_contents()
    verify_no_private_text()
    write_release_zip()

    print("release folder created:")
    print(RELEASE)
    print("zip created:")
    print(ZIP_PATH)


def write_release_config(path: Path) -> None:
    source_path = ROOT / "config.json"
    if not source_path.exists():
        raise FileNotFoundError(f"Missing file: {source_path}")

    config = json.loads(source_path.read_text(encoding="utf-8"))
    config["log_file_path"] = ""
    config["overlay_state_path"] = "overlay_state.json"
    config["minimum_votes"] = 20
    config.update(DISPLAY_DEFAULTS)
    # 配布物は必ず安全側: 停止OFF・OBS連携OFF・パスワード空で作り直す。
    config["stop_streaming_enabled"] = False
    config["obs_websocket_enabled"] = False
    config["obs_host"] = "127.0.0.1"
    config["obs_port"] = 4455
    config["obs_password"] = ""
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_release_overlay_state(path: Path) -> None:
    state = {
        "preview_mode": "none",
        **DISPLAY_DEFAULTS,
        "visible": False,
        "display_enabled": True,
        "end_votes": 0,
        "continue_votes": 0,
        "end_rate": 0,
        "valid_votes": 0,
        "minimum_votes": 20,
        "end_rate_threshold": 0.7,
        "threshold_met": False,
        "window_seconds": 180,
        "updated_at": "",
        "mode": "normal",
        "countdown_remaining": 0,
        "countdown_started_at": None,
        "can_cancel": False,
        "obs_connected": None,
        "stop_streaming_enabled": False,
        "stop_result": None,
        "stop_error": None,
    }
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_release_contents() -> None:
    release_names = sorted(path.name for path in RELEASE.iterdir() if path.is_file())
    expected_names = sorted(EXPECTED_RELEASE_NAMES)
    if release_names != expected_names:
        raise RuntimeError(f"Unexpected release contents: {release_names}")


def verify_no_private_text() -> None:
    text_suffixes = {".json", ".txt", ".html", ".md"}

    for path in RELEASE.iterdir():
        if not path.is_file():
            continue

        # PyInstaller製exeにはビルド時のパス断片が混ざることがあるので、
        # 配布者が直接読むテキスト系ファイルだけ検査する。
        if path.suffix.lower() not in text_suffixes and path.name != "LICENSE":
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        folded_text = text.casefold()

        for forbidden in FORBIDDEN_RELEASE_TEXT:
            if forbidden.casefold() in folded_text:
                raise RuntimeError(
                    f"Private text found in {path.name}: {forbidden}"
                )


def write_release_zip() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in EXPECTED_RELEASE_NAMES:
            archive.write(RELEASE / name, arcname=name)


if __name__ == "__main__":
    main()
