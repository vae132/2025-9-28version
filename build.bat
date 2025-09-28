@echo off
:: build.bat —— 一键生成 dist\yangqi_clinic.exe
chcp 65001 > nul

echo.
echo ================== START BUILD ==================

rem ---------- 可自行修改的 4 个变量 ----------
set "VENV_DIR=.venv"
set "EXE_NAME=yangqi_clinic"
set "MAIN_SCRIPT=display.py"
set "DATA_DIR=data"
rem -----------------------------------------------

rem [1] 检查 python
where python > nul 2>&1 || (
  echo ❌  Python 未安装或未加入 PATH。
  pause & exit /b 1
)

rem [2] 创建 / 复用虚拟环境
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo ---------- Create venv ----------
  python -m venv "%VENV_DIR%" || (
    echo ❌  venv 创建失败。
    pause & exit /b 1
  )
)

rem 将 venv\Scripts 加入 PATH（等同于 activate）
set "PATH=%VENV_DIR%\Scripts;%PATH%"

rem [3] 安装依赖
echo ---------- Install deps ----------
python -m pip install -U pip
python -m pip install PyQt5==5.15.* requests beautifulsoup4 apscheduler pyinstaller

if errorlevel 1 (
  echo ❌  pip 安装失败。
  pause & exit /b 1
)

rem [4] 打包
echo ---------- PyInstaller ----------
python -m PyInstaller ^
  --name "%EXE_NAME%" ^
  --onefile ^
  --add-data "%DATA_DIR%;%DATA_DIR%" ^
  "%MAIN_SCRIPT%"

if errorlevel 1 (
  echo ❌  打包失败。
  pause & exit /b 1
)

echo.
echo ✅  成功生成 dist\%EXE_NAME%.exe
pause
