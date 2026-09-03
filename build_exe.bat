@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo Build stream-end-vote v1.0.0
echo ========================================
echo.

echo [1/4] Cleaning old build files...
if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"
if exist "release" rmdir /S /Q "release"
if exist "stream-end-vote.spec" del /Q "stream-end-vote.spec"

echo.
echo [2/4] Installing requirements...
python -m pip install -r requirements.txt
if errorlevel 1 goto error

python -m pip install -r requirements-dev.txt
if errorlevel 1 goto error

echo.
echo [3/4] Checking imports...
set PYTHONPATH=%~dp0src
python -c "import end_vote.app; import end_vote.obs_control; print('import ok')"
if errorlevel 1 goto error

echo.
echo [4/4] Building exe...
python -m PyInstaller --clean --noconfirm --onefile --windowed --name stream-end-vote --paths "%~dp0src" --collect-submodules end_vote --hidden-import end_vote.app --hidden-import end_vote.config --hidden-import end_vote.vote --hidden-import end_vote.log_reader --hidden-import end_vote.log_discovery --hidden-import end_vote.overlay --hidden-import end_vote.countdown --hidden-import end_vote.obs_control --hidden-import end_vote.obs_settings run.py
if errorlevel 1 goto error

echo.
echo Creating release zip...
python make_release.py
if errorlevel 1 goto error

echo.
echo ========================================
echo Build completed.
echo ========================================
echo.
echo Output:
echo release
echo 配信終了投票くん_v1.0.0.zip
echo.
if not "%CI%"=="1" pause
exit /b 0

:error
echo.
echo ========================================
echo Build failed.
echo ========================================
echo.
if not "%CI%"=="1" pause
exit /b 1
