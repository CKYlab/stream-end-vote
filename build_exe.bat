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
python -c "from pathlib import Path; import shutil; r=Path('release'); readme=next(Path('.').glob('README_*.txt')); shutil.copy2(readme, r / '01_\u6700\u521d\u306b\u8aad\u3080_\u4f7f\u3044\u65b9.txt'); shutil.copy2('dist/amemiya-end-vote.exe', r / '02_\u8d77\u52d5\u3059\u308b_\u914d\u4fe1\u7d42\u4e86\u6295\u7968\u304f\u3093.exe'); shutil.copy2('overlay.html', r / '03_OBS\u306b\u5165\u308c\u308b_overlay.html'); shutil.copy2('config.json', r / 'config.json'); shutil.copy2('overlay_state.json', r / 'overlay_state.json')"
if errorlevel 1 exit /b %errorlevel%

echo release folder created.
endlocal
