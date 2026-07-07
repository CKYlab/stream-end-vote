@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo Build amemiya-end-vote v0.3.5
echo ========================================
echo.

echo [1/4] Cleaning old build files...
if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"
if exist "release" rmdir /S /Q "release"
if exist "amemiya-end-vote.spec" del /Q "amemiya-end-vote.spec"

echo.
echo [2/4] Installing requirements...
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto error

echo.
echo [3/4] Building exe...
python -m PyInstaller --clean --noconfirm --onefile --windowed --name amemiya-end-vote --paths "%CD%\src" --collect-submodules end_vote run.py
if errorlevel 1 goto error

echo.
echo [4/4] Creating release zip...
python make_release.py
if errorlevel 1 goto error

echo.
echo ========================================
echo Build completed.
echo ========================================
echo.
echo Output:
echo release
echo release zip created
echo.
exit /b 0

:error
echo.
echo ========================================
echo Build failed.
echo ========================================
echo.
exit /b 1

