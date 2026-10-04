"""
Build Script for ID Card Generator Executable.
Works on Windows, Linux, and macOS.

Usage:
    python build_exe.py
"""
import os
import sys
import subprocess
import shutil

def check_dependencies():
    print("Checking build tools...")
    try:
        import PyInstaller
        print(f"  PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("  Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    required_packages = ["PyQt6", "Pillow", "requests", "reportlab"]
    for pkg in required_packages:
        try:
            __import__(pkg if pkg != "Pillow" else "PIL")
            print(f"  {pkg}: OK")
        except ImportError:
            print(f"  Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

def build():
    check_dependencies()

    spec_file = "idcard.spec"
    if not os.path.exists(spec_file):
        print(f"Error: {spec_file} not found!")
        sys.exit(1)

    print("\nStarting PyInstaller build...")
    # Clean previous build artifacts
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
            except Exception:
                pass

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        spec_file
    ]

    print("Running command:", " ".join(cmd))
    res = subprocess.call(cmd)
    if res == 0:
        print("\n" + "="*50)
        print("BUILD SUCCESSFUL!")
        exe_ext = ".exe" if sys.platform == "win32" else ""
        out_file = os.path.join("dist", f"IDCardStudio{exe_ext}")
        if os.path.exists(out_file):
            size_mb = os.path.getsize(out_file) / (1024 * 1024)
            print(f"Executable output: {out_file} ({size_mb:.2f} MB)")
        print("="*50)
    else:
        print(f"\nBuild failed with exit code: {res}")
        sys.exit(res)

if __name__ == "__main__":
    build()
