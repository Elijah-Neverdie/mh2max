@echo off
setlocal EnableExtensions
rem UTF-8 console (paths with CJK still work via Python unicode APIs)
chcp 65001 >nul 2>&1

rem Always anchor to this script's directory (supports spaces & non-ASCII paths)
set "MH2MAX_ROOT=%~dp0"
if "%MH2MAX_ROOT:~-1%"=="\" set "MH2MAX_ROOT=%MH2MAX_ROOT:~0,-1%"
cd /d "%MH2MAX_ROOT%"
if errorlevel 1 (
    echo [error] 无法进入目录：%MH2MAX_ROOT%
    pause
    exit /b 1
)

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY where python3 >nul 2>&1 && set "PY=python3"

if not defined PY (
    echo [error] 未找到 Python。请安装 Python 3 或将 py/python 加入 PATH。
    echo        也可手动运行：python tools\mh2max_install.py
    pause
    exit /b 1
)

echo Using: %PY%
"%PY%" "%MH2MAX_ROOT%\tools\mh2max_install.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
