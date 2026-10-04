@echo off
title Build ID Card Generator Executable
color 0A

echo ========================================================
echo   Building ID Card Studio (.exe) with PyInstaller
echo ========================================================
echo.

echo [1/3] Memeriksa dan menginstal dependensi Python...
python -m pip install --upgrade pip
python -m pip install pyinstaller PyQt6 Pillow requests reportlab pyyaml

echo.
echo [2/3] Membangun file Executable Windows (IDCardStudio.exe)...
python -m PyInstaller --clean --noconfirm idcard.spec

echo.
echo [3/3] Selesai!
if exist dist\IDCardStudio.exe (
    echo ========================================================
    echo   BERHASIL! File executable siap digunakan di:
    echo   dist\IDCardStudio.exe
    echo ========================================================
) else (
    echo ========================================================
    echo   Build gagal. Silakan periksa pesan error di atas.
    echo ========================================================
)

pause
