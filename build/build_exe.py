"""
PyInstaller packaging script for CadetCal standalone .exe.

Usage (from repo root):
    python build/build_exe.py

Requires pyinstaller to be installed (included in requirements.txt).

NOTE: Test the resulting executable on an actual cadet computer before
releasing — DoD endpoint protection may flag unsigned binaries. If rejected,
direct cadets to the Streamlit Community Cloud hosted version instead.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def build():
    entry = ROOT / "app.py"
    data_dir = ROOT / "data"
    assets_dir = ROOT / "assets"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "cadetcal",
        "--add-data", f"{data_dir}{':' if sys.platform != 'win32' else ';'}data",
        "--add-data", f"{assets_dir}{':' if sys.platform != 'win32' else ';'}assets",
        "--hidden-import", "streamlit",
        "--hidden-import", "pydantic",
        str(entry),
    ]

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    print("\nBuild complete. Executable in dist/")


if __name__ == "__main__":
    build()
