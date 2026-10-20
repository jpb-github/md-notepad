"""Build MDViewer with PyInstaller.

Run from anywhere:  .venv\\Scripts\\python scripts\\build_exe.py [--onefile] [--console] [--icon other.ico]
Default output:     dist\\MDViewer\\MDViewer.exe (one folder: fast launch, input for the installer)
--onefile output:   dist\\MDViewer.exe (slow launch: unpacks ~200 MiB to %TEMP% on every run)
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "MDViewer"
ICON = ROOT / "assets" / "mdviewer.ico"  # regenerate with scripts/make_icon.py


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--onefile", action="store_true", help="build one self-extracting exe (slow to start)")
    parser.add_argument("--console", action="store_true", help="keep a console window (for debugging)")
    parser.add_argument("--icon", type=Path, default=ICON, help="path to a .ico file for the executable (default: assets\\mdviewer.ico)")
    parser.add_argument("--keep-build", action="store_true", help="keep the build/ work directory")
    args = parser.parse_args()

    if importlib.util.find_spec("PyInstaller") is None:
        print('PyInstaller is not installed. Run: python -m pip install -e ".[build]"', file=sys.stderr)
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile" if args.onefile else "--onedir",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        # Pygments resolves lexers/styles by name at runtime, so static analysis misses them.
        "--collect-submodules", "pygments",
        "--console" if args.console else "--windowed",
    ]
    if ICON.is_file():
        # Runtime window icon (mdviewer.app.icon_path); --icon below only brands the exe file.
        cmd += ["--add-data", f"{ICON}{os.pathsep}assets"]
    if args.icon.is_file():
        cmd += ["--icon", str(args.icon.resolve())]
    else:
        print(f"Warning: icon {args.icon} not found; building without an icon.", file=sys.stderr)
    cmd.append(str(ROOT / "main.py"))

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    if not args.keep_build:
        shutil.rmtree(ROOT / "build", ignore_errors=True)

    if not args.onefile:
        # Chromium DevTools front-end (~80 MiB); the preview has JS disabled and never opens it.
        for pak in (ROOT / "dist" / NAME / "_internal" / "PySide6" / "resources").glob("qtwebengine_devtools_resources*.pak"):
            pak.unlink()

    exe = ROOT / "dist" / f"{NAME}.exe" if args.onefile else ROOT / "dist" / NAME / f"{NAME}.exe"
    if not exe.is_file():
        print(f"Build finished but {exe} was not produced.", file=sys.stderr)
        return 1
    print(f"\nBuilt {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
