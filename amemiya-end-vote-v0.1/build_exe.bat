@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"
if exist "amemiya-end-vote.spec" del /Q "amemiya-end-vote.spec"
if exist "release" rmdir /S /Q "release"

python -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b %errorlevel%

python -m PyInstaller --clean --onefile --windowed --name amemiya-end-vote --paths "%CD%\src" --collect-submodules end_vote run.py
if errorlevel 1 exit /b %errorlevel%

mkdir release
python -c "from pathlib import Path; import shutil, zipfile; r=Path('release'); files=[('01_最初に読む_使い方.txt', r / '01_最初に読む_使い方.txt'), ('dist/amemiya-end-vote.exe', r / '02_起動する_配信終了投票くん.exe'), ('overlay.html', r / '03_OBSに入れる_overlay.html'), ('config.json', r / 'config.json'), ('overlay_state.json', r / 'overlay_state.json')]; [shutil.copy2(src, dst) for src, dst in files]; expected=[dst.name for _, dst in files]; extras=[p for p in r.iterdir() if p.name not in expected]; [p.unlink() for p in extras if p.is_file()]; z=zipfile.ZipFile('配信終了投票くん_v0.1.zip', 'w', zipfile.ZIP_DEFLATED); [z.write(r / name, name) for name in expected]; z.close()"
if errorlevel 1 exit /b %errorlevel%

echo release folder and 配信終了投票くん_v0.1.zip created.
endlocal
