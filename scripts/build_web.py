"""Rebuild the web editor runtime files in mdviewer/web/ from web-src/.

Run from anywhere:  .venv\\Scripts\\python scripts\\build_web.py
Needs Node.js >= 20 with npm on PATH. Outputs (all committed): editor.js, editor.css,
THIRD_PARTY.txt (esbuild, web-src/build.mjs) and qwebchannel.js (copied from PySide6).
Normal development, tests and packaging use the committed files; run this only after
changing web-src/, then run scripts/check_web.py.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_SRC = ROOT / "web-src"
WEB_OUT = ROOT / "mdviewer" / "web"
OUTPUTS = ("editor.js", "editor.css", "qwebchannel.js", "THIRD_PARTY.txt")
QWEBCHANNEL_RESOURCE = ":/qtwebchannel/qwebchannel.js"


def copy_qwebchannel() -> None:
    """Ship Qt's client unmodified next to the bundle, so CSP script-src 'self' covers it."""
    from PySide6 import QtWebChannel  # noqa: F401  registers the :/qtwebchannel resources
    from PySide6.QtCore import QFile, QIODevice

    resource = QFile(QWEBCHANNEL_RESOURCE)
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"cannot read {QWEBCHANNEL_RESOURCE} from PySide6")
    try:
        (WEB_OUT / "qwebchannel.js").write_bytes(bytes(resource.readAll()))
    finally:
        resource.close()


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found. Install Node.js 20 or later and retry.", file=sys.stderr)
        return 1
    for args in (["ci"], ["run", "build"]):
        print("Running: npm", " ".join(args))
        result = subprocess.run([npm, *args], cwd=WEB_SRC)
        if result.returncode != 0:
            return result.returncode
    copy_qwebchannel()
    missing = [name for name in OUTPUTS if not (WEB_OUT / name).is_file()]
    if missing:
        print(f"Build finished but did not produce: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"\nBuilt {WEB_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
