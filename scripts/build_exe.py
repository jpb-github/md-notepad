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
WEB_DIR = ROOT / "mdviewer" / "web"  # committed output of scripts/build_web.py
# What richview.RUNTIME_FILES copies next to the page, plus the shell render.editor_page reads.
WEB_FILES = ("editor.html", "editor.js", "editor.css", "qwebchannel.js")


def missing_web_files() -> list[str]:
    return [name for name in WEB_FILES if not (WEB_DIR / name).is_file()]


def missing_bundle_files(app_dir: Path) -> list[str]:
    """Paths (relative to a one-folder build) the Rendered editor needs that the build lacks."""
    needed = [f"_internal/mdviewer/web/{name}" for name in WEB_FILES] + ["_internal/PySide6/QtWebChannel.pyd"]
    return [path for path in needed if not (app_dir / path).is_file()]


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
    missing = missing_web_files()
    if missing:
        print(f"Missing from mdviewer\\web: {', '.join(missing)}. Run: python scripts\\build_web.py", file=sys.stderr)
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
    # The editor page: render.WEB_DIR resolves to <bundle>/mdviewer/web when frozen.
    cmd += ["--add-data", f"{WEB_DIR}{os.pathsep}mdviewer/web"]
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
        # Chromium DevTools front-end (~80 MiB); the app never opens it.
        for pak in (ROOT / "dist" / NAME / "_internal" / "PySide6" / "resources").glob("qtwebengine_devtools_resources*.pak"):
            pak.unlink()
        lacking = missing_bundle_files(ROOT / "dist" / NAME)
        if lacking:
            print(f"Build finished but the bundle lacks: {', '.join(lacking)}", file=sys.stderr)
            return 1

    exe = ROOT / "dist" / f"{NAME}.exe" if args.onefile else ROOT / "dist" / NAME / f"{NAME}.exe"
    if not exe.is_file():
        print(f"Build finished but {exe} was not produced.", file=sys.stderr)
        return 1
    print(f"\nBuilt {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
