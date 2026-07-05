from __future__ import annotations

from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "release"
ZIP_PATH = ROOT / "配信終了投票くん_v0.1.zip"

EXPECTED_RELEASE_NAMES = [
    "01_最初に読む_使い方.txt",
    "02_起動する_配信終了投票くん.exe",
    "03_OBSに入れる_overlay.html",
    "config.json",
    "overlay_state.json",
]


def main() -> None:
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir()

    files = [
        (ROOT / "01_最初に読む_使い方.txt", RELEASE / EXPECTED_RELEASE_NAMES[0]),
        (ROOT / "dist" / "amemiya-end-vote.exe", RELEASE / EXPECTED_RELEASE_NAMES[1]),
        (ROOT / "overlay.html", RELEASE / EXPECTED_RELEASE_NAMES[2]),
        (ROOT / "config.json", RELEASE / EXPECTED_RELEASE_NAMES[3]),
        (ROOT / "overlay_state.json", RELEASE / EXPECTED_RELEASE_NAMES[4]),
    ]

    for src, dst in files:
        if not src.exists():
            raise FileNotFoundError(f"Missing file: {src}")
        shutil.copy2(src, dst)

    release_names = sorted(path.name for path in RELEASE.iterdir() if path.is_file())
    expected_names = sorted(EXPECTED_RELEASE_NAMES)
    if release_names != expected_names:
        raise RuntimeError(f"Unexpected release contents: {release_names}")

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in EXPECTED_RELEASE_NAMES:
            archive.write(RELEASE / name, arcname=name)

    print("release folder created:")
    print(RELEASE)
    print("zip created:")
    print(ZIP_PATH)


if __name__ == "__main__":
    main()
