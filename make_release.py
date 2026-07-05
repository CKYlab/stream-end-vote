from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "release"

if RELEASE.exists():
    shutil.rmtree(RELEASE)
RELEASE.mkdir()

readme_candidates = [
    "01_最初に読む_使い方.txt",
    "README_使い方.txt",
]

readme_src = None
for name in readme_candidates:
    path = ROOT / name
    if path.exists():
        readme_src = path
        break

if readme_src is None:
    raise FileNotFoundError("Missing README file: 01_最初に読む_使い方.txt or README_使い方.txt")

files = [
    (readme_src, RELEASE / "01_最初に読む_使い方.txt"),
    (ROOT / "dist" / "amemiya-end-vote.exe", RELEASE / "02_起動する_配信終了投票くん.exe"),
    (ROOT / "overlay.html", RELEASE / "03_OBSに入れる_overlay.html"),
    (ROOT / "config.json", RELEASE / "config.json"),
    (ROOT / "overlay_state.json", RELEASE / "overlay_state.json"),
]

for src, dst in files:
    if not src.exists():
        raise FileNotFoundError(f"Missing file: {src}")
    shutil.copy2(src, dst)

zip_path = ROOT / "配信終了投票くん_v0.1.zip"
if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for _, dst in files:
        z.write(dst, arcname=dst.name)

print("release folder created:")
print(RELEASE)
print("zip created:")
print(zip_path)
